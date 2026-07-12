from __future__ import annotations
import csv, io, json, math, os, random, sqlite3, re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sync.official_connector import OfficialDemoConnector
from sync.wahis_csv_connector import WahisCsvConnector
from sync.adis_csv_connector import AdisCsvConnector
from sync.normalizer import normalize_official_event
from sync.deduplicator import deduplicate_public_events
from sync.event_enrichment import enrich_public_events

try:
    from sync.demo_control import (
        show_demo_events,
        auto_populate_demo_365,
        filter_demo_events,
        demo_status,
        purge_demo_events_sqlite,
    )
except Exception:
    def show_demo_events(): return True
    def auto_populate_demo_365(): return True
    def filter_demo_events(events): return list(events)
    def demo_status(): return {"show_demo_events": True, "auto_populate_demo_365": True}
    def purge_demo_events_sqlite(conn, table_name="events", older_than_days=None):
        return {"status": "disabled", "deleted": 0}

DB_PATH=os.getenv("DB_PATH","vet_alert.db")
ENABLE_SCHEDULER=os.getenv("ENABLE_SCHEDULER","true").lower()=="true"
SYNC_INTERVAL_HOURS=int(os.getenv("SYNC_INTERVAL_HOURS","24"))
WAHIS_SYNC_TOKEN=os.getenv("WAHIS_SYNC_TOKEN","")
AUTO_POPULATE_DEMO_365=auto_populate_demo_365()
SHOW_DEMO_EVENTS=show_demo_events()
DEMO_365_COUNT=int(os.getenv("DEMO_365_COUNT","280"))
EARTH_RADIUS_KM=6371.0
app=FastAPI(title="vet.ector Veterinary Alert API", version="1.6.0-source-normalization-v89")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
scheduler=BackgroundScheduler()

class UserReport(BaseModel):
    disease:str; diagnosis_status:str="Sospetto"; species:str="Animale"; animal_group:str="unknown"; observation_date:str|None=None; lat:float; lon:float; location:str=""; region:str=""; country:str="Italy"; source:str="user_report"; report_type:str="user_suspect"

def now_iso(): return datetime.now(timezone.utc).isoformat()
def connect():
    conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row; return conn

def init_db():
    with connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,external_id TEXT UNIQUE,disease TEXT NOT NULL,diagnosis_status TEXT,species TEXT,animal_group TEXT,observation_date TEXT,lat REAL NOT NULL,lon REAL NOT NULL,location TEXT,region TEXT,country TEXT DEFAULT 'Italy',source TEXT,source_type TEXT DEFAULT 'user',report_type TEXT DEFAULT 'user_suspect',updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS official_events(id INTEGER PRIMARY KEY AUTOINCREMENT,external_id TEXT UNIQUE NOT NULL,source TEXT NOT NULL,source_type TEXT DEFAULT 'official',report_type TEXT DEFAULT 'official_confirmed',disease TEXT NOT NULL,disease_it TEXT,diagnosis_status TEXT DEFAULT 'Confermato',species TEXT,animal_group TEXT,observation_date TEXT,report_date TEXT,country TEXT DEFAULT 'Italy',region TEXT,location TEXT,lat REAL,lon REAL,url_source TEXT,notes TEXT,raw_payload TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS veterinarians(id INTEGER PRIMARY KEY AUTOINCREMENT,external_id TEXT UNIQUE,name TEXT NOT NULL,type TEXT,availability TEXT,phone TEXT,lat REAL NOT NULL,lon REAL NOT NULL,city TEXT,region TEXT,services TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS sync_log(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL,status TEXT NOT NULL,message TEXT,records_received INTEGER DEFAULT 0,records_inserted INTEGER DEFAULT 0,records_updated INTEGER DEFAULT 0,started_at TEXT,finished_at TEXT)""")
        conn.commit()

def load_json(path):
    try:
        with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except Exception: return []

def log_sync(source,status,message,received,inserted,updated,started_at):
    with connect() as conn:
        conn.execute("INSERT INTO sync_log(source,status,message,records_received,records_inserted,records_updated,started_at,finished_at) VALUES (?,?,?,?,?,?,?,?)",(source,status,message,received,inserted,updated,started_at,now_iso())); conn.commit()

def upsert_event(row):
    external_id=row.get("external_id") or f"EVENT-{datetime.now(timezone.utc).timestamp()}"
    with connect() as conn:
        existing=conn.execute("SELECT id FROM events WHERE external_id=?",(external_id,)).fetchone()
        conn.execute("""INSERT INTO events(external_id,disease,diagnosis_status,species,animal_group,observation_date,lat,lon,location,region,country,source,source_type,report_type,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(external_id) DO UPDATE SET disease=excluded.disease,diagnosis_status=excluded.diagnosis_status,species=excluded.species,animal_group=excluded.animal_group,observation_date=excluded.observation_date,lat=excluded.lat,lon=excluded.lon,location=excluded.location,region=excluded.region,country=excluded.country,source=excluded.source,source_type=excluded.source_type,report_type=excluded.report_type,updated_at=CURRENT_TIMESTAMP""",(external_id,row.get("disease"),row.get("diagnosis_status","Sospetto"),row.get("species",""),row.get("animal_group","unknown"),row.get("observation_date",""),float(row.get("lat")),float(row.get("lon")),row.get("location",""),row.get("region",""),row.get("country","Italy"),row.get("source","user_report"),row.get("source_type","user"),row.get("report_type","user_suspect")))
        conn.commit()
    return "updated" if existing else "inserted"

def upsert_veterinarian(row):
    external_id=row.get("external_id") or row.get("id") or row.get("name")
    with connect() as conn:
        existing=conn.execute("SELECT id FROM veterinarians WHERE external_id=?",(external_id,)).fetchone()
        conn.execute("""INSERT INTO veterinarians(external_id,name,type,availability,phone,lat,lon,city,region,services,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(external_id) DO UPDATE SET name=excluded.name,type=excluded.type,availability=excluded.availability,phone=excluded.phone,lat=excluded.lat,lon=excluded.lon,city=excluded.city,region=excluded.region,services=excluded.services,updated_at=CURRENT_TIMESTAMP""",(external_id,row.get("name"),row.get("type","Veterinario"),row.get("availability",""),row.get("phone",""),float(row.get("lat")),float(row.get("lon")),row.get("city",""),row.get("region",""),json.dumps(row.get("services",[]),ensure_ascii=False)))
        conn.commit()
    return "updated" if existing else "inserted"

def upsert_official_event(row):
    if not row.get("external_id"): row["external_id"]=f"{row.get('source','OFFICIAL')}-{row.get('disease','disease')}-{row.get('observation_date','date')}-{row.get('location','location')}"
    if row.get("lat") is None or row.get("lon") is None: raise ValueError(f"Official event {row.get('external_id')} missing lat/lon")
    with connect() as conn:
        existing=conn.execute("SELECT id FROM official_events WHERE external_id=?",(row["external_id"],)).fetchone()
        conn.execute("""INSERT INTO official_events(external_id,source,source_type,report_type,disease,disease_it,diagnosis_status,species,animal_group,observation_date,report_date,country,region,location,lat,lon,url_source,notes,raw_payload,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(external_id) DO UPDATE SET source=excluded.source,source_type=excluded.source_type,report_type=excluded.report_type,disease=excluded.disease,disease_it=excluded.disease_it,diagnosis_status=excluded.diagnosis_status,species=excluded.species,animal_group=excluded.animal_group,observation_date=excluded.observation_date,report_date=excluded.report_date,country=excluded.country,region=excluded.region,location=excluded.location,lat=excluded.lat,lon=excluded.lon,url_source=excluded.url_source,notes=excluded.notes,raw_payload=excluded.raw_payload,updated_at=CURRENT_TIMESTAMP""",(row["external_id"],row.get("source","OFFICIAL_UNKNOWN"),row.get("source_type","official"),row.get("report_type","official_confirmed"),row.get("disease",""),row.get("disease_it",""),row.get("diagnosis_status","Confermato"),row.get("species",""),row.get("animal_group","unknown"),row.get("observation_date",""),row.get("report_date",""),row.get("country","Italy"),row.get("region",""),row.get("location",""),float(row.get("lat")),float(row.get("lon")),row.get("url_source",""),row.get("notes",""),json.dumps(row.get("raw_payload",{}),ensure_ascii=False)))
        conn.commit()
    return "updated" if existing else "inserted"

def _sync_rows(source_name, rows, default_source):
    started=now_iso(); ins=upd=skip=0
    for raw in rows:
        n=normalize_official_event(raw, default_source=default_source)
        try:
            r=upsert_official_event(n); ins+=r=="inserted"; upd+=r=="updated"
        except Exception as e:
            skip+=1; print("Skipped official event",e)
    log_sync(source_name,"success",f"{source_name} sync completed; skipped={skip}",len(rows),ins,upd,started)
    return {"status":"success","source":source_name,"received":len(rows),"inserted":ins,"updated":upd,"skipped":skip}

def sync_seed_data():
    started=now_iso(); ins=upd=0
    for row in load_json("data/source_events.json"):
        r=upsert_event(row); ins+=r=="inserted"; upd+=r=="updated"
    for row in load_json("data/source_veterinarians.json"): upsert_veterinarian(row)
    log_sync("seed_data","success","Seed data sync completed",ins+upd,ins,upd,started); return {"status":"success","inserted":ins,"updated":upd}

def sync_official_events():
    c=OfficialDemoConnector(); return _sync_rows(c.source_name,c.fetch(),"OFFICIAL_DEMO")
def sync_wahis_events():
    c=WahisCsvConnector(); return _sync_rows(c.source_name,c.fetch(),"WAHIS_CSV")
def sync_adis_events():
    c=AdisCsvConnector(); return _sync_rows(c.source_name,c.fetch(),"ADIS")
def sync_wahis_csv_text(csv_text, source_name="WAHIS_CSV_UPLOAD"):
    return _sync_rows(source_name,WahisCsvConnector.parse_csv_text(csv_text),"WAHIS")
def require_sync_token(token):
    if WAHIS_SYNC_TOKEN and token != WAHIS_SYNC_TOKEN: raise HTTPException(status_code=401, detail="Invalid or missing sync token")
def haversine_km(lat1,lon1,lat2,lon2):
    dlat=math.radians(lat2-lat1); dlon=math.radians(lon2-lon1); rlat1=math.radians(lat1); rlat2=math.radians(lat2); a=math.sin(dlat/2)**2+math.cos(rlat1)*math.cos(rlat2)*math.sin(dlon/2)**2; return 2*EARTH_RADIUS_KM*math.asin(math.sqrt(a))
def parse_date(value):
    if not value: return None
    try: return datetime.fromisoformat(str(value)[:10]).date()
    except Exception: return None

def matches_animal_filter(row, animal_filter):
    if animal_filter in ("", "all", None): return True
    animal_filter = str(animal_filter).lower().strip()
    animal_group = str(row.get("animal_group", "")).lower().strip()
    species = str(row.get("species", "")).lower().strip()
    text = f"""
    {row.get('species', '')}
    {row.get('animal_group', '')}
    {row.get('disease', '')}
    {row.get('disease_it', '')}
    """.lower()
    filters = {
        "companion": ["dog","cane","canine","cat","gatto","feline"],
        "livestock": ["bovine","bovino","bovini","cattle","swine","suino","suini","pig","pigs","cinghiale","cinghiali","ovine","ovino","ovini","sheep","pecora","pecore","equine","equino","equini","horse","horses","cavallo","cavalli","caprine","caprino","caprini","goat","goats","capra","capre","poultry","avicoli","volatile","volatili","avian","bird","birds","pollo","polli","gallina","galline"],
        "dog": ["dog","cane","canine"],
        "cat": ["cat","gatto","feline"],
        "bovine": ["bovine","bovino","bovini","cattle","cow","cows"],
        "swine": ["swine","suino","suini","pig","pigs","cinghiale","cinghiali","wild boar"],
        "ovine": ["ovine","ovino","ovini","sheep","pecora","pecore"],
        "equine": ["equine","equino","equini","horse","horses","cavallo","cavalli"],
        "caprine": ["caprine","caprino","caprini","goat","goats","capra","capre"],
        "poultry": ["poultry","avicoli","volatile","volatili","avian","bird","birds","pollo","polli","gallina","galline"],
        "dogs": ["dog","cane","canine"],
        "cats": ["cat","gatto","feline"],
        "farm": ["bovine","bovino","bovini","cattle","swine","suino","suini","pig","pigs","cinghiale","cinghiali","ovine","ovino","ovini","sheep","pecora","pecore","equine","equino","equini","horse","horses","cavallo","cavalli","caprine","caprino","caprini","goat","goats","capra","capre","poultry","avicoli","volatile","volatili","avian","bird","birds"],
    }
    terms = filters.get(animal_filter, [])
    if not terms: return True
    if animal_group in terms or species in terms: return True
    for term in terms:
        pattern = r"(?<![a-zA-Z])" + re.escape(term) + r"(?![a-zA-Z])"
        if re.search(pattern, text): return True
    return False

def compute_risk_score(status,distance_km,observation_date):
    s=(status or "").lower(); status_score=1.0 if "conferm" in s or "confirm" in s else 0.65 if "sosp" in s or "suspect" in s else .4; obs=parse_date(observation_date); days_old=max(0,(datetime.now(timezone.utc).date()-obs).days) if obs else 15; distance_score=max(0,1-min(distance_km,100)/100); recency_score=max(0,1-min(days_old,30)/30); return round((.45*status_score+.30*distance_score+.25*recency_score)*100,1)
def row_to_public_event(row,distance_km):
    disease_it=row.get("disease_it") or row.get("disease"); status=row.get("diagnosis_status") or "Confermato"
    return {"id":row.get("external_id") or row.get("id"),"external_id":row.get("external_id"),"disease":disease_it,"disease_original":row.get("disease"),"diagnosis_status":status,"species":row.get("species"),"animal_group":row.get("animal_group"),"observation_date":row.get("observation_date"),"report_date":row.get("report_date") or row.get("observation_date"),"lat":row.get("lat"),"lon":row.get("lon"),"location":row.get("location"),"region":row.get("region"),"country":row.get("country"),"source":row.get("source"),"source_type":row.get("source_type"),"report_type":row.get("report_type"),"url_source":row.get("url_source",""),"distance_km":round(distance_km,2),"risk_score":compute_risk_score(status,distance_km,row.get("observation_date"))}
def all_event_rows():
    with connect() as conn:
        rows=[dict(r) for r in conn.execute("SELECT * FROM events").fetchall()]
        rows.extend([dict(r) for r in conn.execute("SELECT * FROM official_events").fetchall()])
    return rows
def filtered_rows_for_export(days=365, animal_filter="all"):
    cutoff=datetime.now(timezone.utc).date()-timedelta(days=days); out=[]
    for row in all_event_rows():
        obs=parse_date(row.get("observation_date"))
        if obs and obs < cutoff: continue
        if not matches_animal_filter(row,animal_filter): continue
        out.append(row_to_public_event(row,0.0))
    out.sort(key=lambda x: x.get("observation_date") or "", reverse=True); return out

def populate_demo_365(count=280):
    cities=load_json("data/source_cities.json"); random.seed(42); disease_pool=[("Giardiasi","Gatto","companion"),("Parvovirosi canina","Cane","companion"),("Leptospirosi","Cane","companion"),("Tosse infettiva canina","Cane","companion"),("Mastite bovina","Bovino","bovine"),("Sindrome respiratoria bovina","Bovino","bovine"),("Peste suina africana","Cinghiale","swine"),("Influenza aviaria ad alta patogenicita","Avicoli","poultry"),("West Nile fever","Equini","equine"),("Bluetongue","Ovino","ovine"),("Peste dei piccoli ruminanti","Caprino","caprine"),("Mastite ovina/caprina","Caprino","caprine"),("Coccidiosi ovina/caprina","Ovino","ovine")]
    today=datetime.now(timezone.utc).date(); ins=upd=0
    for i in range(count):
        c=random.choice(cities); d,species,grp=random.choice(disease_pool); days_ago=random.randint(0,364); status=random.choices(["Sospetto","Segnalato da utente","Confermato"],[.55,.30,.15])[0]; lat=float(c['lat'])+(random.random()-.5)*.35; lon=float(c['lon'])+(random.random()-.5)*.35
        row={"external_id":f"DEMO365-{i:04d}","disease":d,"diagnosis_status":status,"species":species,"animal_group":grp,"observation_date":(today-timedelta(days=days_ago)).isoformat(),"lat":lat,"lon":lon,"location":c['name'],"region":"Demo Italia","country":"Italy","source":"Demo 365 giorni","source_type":"user","report_type":"user_suspect"}
        r=upsert_event(row); ins+=r=="inserted"; upd+=r=="updated"
    log_sync("demo_365","success",f"Demo 365 populated count={count}",count,ins,upd,now_iso()); return {"status":"success","inserted":ins,"updated":upd,"count":count}

@app.on_event("startup")
def startup():
    init_db(); sync_seed_data(); sync_official_events(); sync_wahis_events(); sync_adis_events()
    if AUTO_POPULATE_DEMO_365: populate_demo_365(DEMO_365_COUNT)
    if ENABLE_SCHEDULER and not scheduler.running:
        scheduler.add_job(sync_official_events,"interval",hours=SYNC_INTERVAL_HOURS,id="official_sync",replace_existing=True); scheduler.add_job(sync_wahis_events,"interval",hours=SYNC_INTERVAL_HOURS,id="wahis_csv_sync",replace_existing=True); scheduler.add_job(sync_adis_events,"interval",hours=SYNC_INTERVAL_HOURS,id="adis_csv_sync",replace_existing=True); scheduler.start()
@app.on_event("shutdown")
def shutdown():
    if scheduler.running: scheduler.shutdown(wait=False)
@app.get("/health")
def health(): return {"status":"ok","time":now_iso(),"version":app.version,"sync_interval_hours":SYNC_INTERVAL_HOURS,"auto_populate_demo_365":AUTO_POPULATE_DEMO_365,"show_demo_events":SHOW_DEMO_EVENTS}
@app.get("/demo/status")
def get_demo_status(): return demo_status()
@app.get("/cities")
def get_cities(): return {"cities":load_json("data/source_cities.json")}
@app.get("/sync/log")
def get_sync_log(limit:int=Query(50,ge=1,le=200)):
    with connect() as conn: rows=conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
    return {"logs":[dict(r) for r in rows]}
@app.post("/sync/run")
def run_seed_sync(): return sync_seed_data()
@app.post("/sync/official/run")
def run_official_sync(): return sync_official_events()
@app.post("/sync/wahis/run")
def run_wahis_sync(): return sync_wahis_events()
@app.post("/sync/wahis/upload")
async def upload_wahis_csv(request:Request,x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token); body=await request.body(); return sync_wahis_csv_text(body.decode("utf-8-sig"),source_name="WAHIS_CSV_UPLOAD")
@app.get("/sync/wahis/status")
def get_wahis_status():
    with connect() as conn: row=conn.execute("SELECT * FROM sync_log WHERE source LIKE 'WAHIS%' ORDER BY id DESC LIMIT 1").fetchone()
    return {"status":"never_run" if row is None else "ok", "last_sync": None if row is None else dict(row)}
@app.post("/sync/adis/run")
def run_adis_sync(): return sync_adis_events()
@app.get("/sync/adis/status")
def get_adis_status():
    with connect() as conn: row=conn.execute("SELECT * FROM sync_log WHERE source LIKE 'ADIS%' ORDER BY id DESC LIMIT 1").fetchone()
    return {"status":"never_run" if row is None else "ok", "last_sync": None if row is None else dict(row)}
@app.post("/sync/all/run")
def run_all_syncs(): return {"seed": sync_seed_data(),"official_demo": sync_official_events(),"wahis": sync_wahis_events(),"adis": sync_adis_events()}
@app.get("/sync/status")
def get_sync_status():
    sources=["seed_data","OFFICIAL_DEMO","WAHIS_CSV","WAHIS_CSV_UPLOAD","ADIS_CSV","demo_365"]
    out={}
    with connect() as conn:
        for source in sources:
            row=conn.execute("SELECT * FROM sync_log WHERE source=? ORDER BY id DESC LIMIT 1",(source,)).fetchone()
            out[source]=None if row is None else dict(row)
    return {"version":app.version,"sync_interval_hours":SYNC_INTERVAL_HOURS,"sources":out}
@app.get("/risk/livestock-density")
def get_livestock_density(country:str=Query("Italy"), species:str=Query("all")):
    data=load_json("data/bdn/livestock_density_it.json")
    if not isinstance(data,list): return {"count":0,"items":[]}
    species_filter=str(species).lower().strip()
    if species_filter and species_filter != "all": data=[r for r in data if species_filter in str(r.get("species","")).lower()]
    return {"count":len(data),"items":data}
@app.post("/demo/populate-365")
def demo_populate_365(count:int=Query(280,ge=1,le=2000)): return populate_demo_365(count)
@app.post("/demo/purge")
def demo_purge(older_than_days: int | None = Query(None, ge=1, le=3650)):
    with connect() as conn: return purge_demo_events_sqlite(conn, table_name="events", older_than_days=older_than_days)

@app.get("/official-events")
def get_official_events(lat:float|None=Query(None),lon:float|None=Query(None),radius_km:float=Query(200,ge=1,le=2000),days:int=Query(365,ge=1,le=3650),animal_filter:str=Query("all"),source:str|None=Query(None)):
    with connect() as conn: rows=[dict(r) for r in conn.execute("SELECT * FROM official_events ORDER BY observation_date DESC").fetchall()]
    cutoff=datetime.now(timezone.utc).date()-timedelta(days=days); out=[]
    for row in rows:
        if source and row.get("source")!=source: continue
        obs=parse_date(row.get("observation_date"))
        if obs and obs<cutoff: continue
        if not matches_animal_filter(row,animal_filter): continue
        distance=0.0
        if lat is not None and lon is not None and row.get("lat") is not None and row.get("lon") is not None:
            distance=haversine_km(lat,lon,float(row["lat"]),float(row["lon"]))
            if distance>radius_km: continue
        out.append(row_to_public_event(row,distance))
    out=deduplicate_public_events(out)
    out=filter_demo_events(out)
    out=enrich_public_events(out)
    return {"count":len(out),"events":out}
@app.get("/events")
def get_events(lat:float=Query(...),lon:float=Query(...),radius_km:float=Query(50,ge=1,le=2000),days:int=Query(180,ge=1,le=3650),animal_filter:str=Query("all"),disease:str|None=Query(None),include_official:bool=Query(True),include_user:bool=Query(True)):
    cutoff=datetime.now(timezone.utc).date()-timedelta(days=days); disease_filter=disease.lower().strip() if disease else ""; rows=[]
    with connect() as conn:
        if include_user: rows.extend([dict(r) for r in conn.execute("SELECT * FROM events").fetchall()])
        if include_official: rows.extend([dict(r) for r in conn.execute("SELECT * FROM official_events").fetchall()])
    out=[]
    for row in rows:
        if row.get("lat") is None or row.get("lon") is None: continue
        obs=parse_date(row.get("observation_date"))
        if obs and obs<cutoff: continue
        if disease_filter and disease_filter not in f"{row.get('disease','')} {row.get('disease_it','')} {row.get('species','')} {row.get('location','')}".lower(): continue
        if not matches_animal_filter(row,animal_filter): continue
        distance=haversine_km(lat,lon,float(row["lat"]),float(row["lon"]))
        if distance>radius_km: continue
        out.append(row_to_public_event(row,distance))
    out=deduplicate_public_events(out)
    out=filter_demo_events(out)
    out=enrich_public_events(out)
    out.sort(key=lambda x:(-x.get("risk_score",0),x.get("distance_km",9999)))
    return {"count":len(out),"events":out}
@app.get("/events/export")
def export_events(days:int=Query(365,ge=1,le=3650),animal_filter:str=Query("all"),format:str=Query("csv")):
    rows=deduplicate_public_events(filtered_rows_for_export(days,animal_filter))
    rows=filter_demo_events(rows)
    rows=enrich_public_events(rows)
    if format.lower()=="json": return {"count":len(rows),"events":rows}
    fields=["id","external_id","disease","diagnosis_status","display_status","display_source","confidence_label","species","animal_group","observation_date","report_date","location","region","country","source","source_type","report_type","lat","lon","url_source"]
    output=io.StringIO(); writer=csv.DictWriter(output,fieldnames=fields,extrasaction="ignore"); writer.writeheader(); writer.writerows(rows); output.seek(0)
    headers={"Content-Disposition":f"attachment; filename=vetector_events_last_{days}_days.csv"}
    return Response(content=output.getvalue(),media_type="text/csv; charset=utf-8",headers=headers)
@app.get("/veterinarians")
def get_veterinarians(lat:float=Query(...),lon:float=Query(...),radius_km:float=Query(50,ge=1,le=2000),animal_filter:str=Query("all")):
    with connect() as conn: rows=[dict(r) for r in conn.execute("SELECT * FROM veterinarians ORDER BY name ASC").fetchall()]
    out=[]
    for row in rows:
        distance=haversine_km(lat,lon,float(row["lat"]),float(row["lon"]))
        if distance>radius_km: continue
        try: row["services"]=json.loads(row.get("services") or "[]")
        except Exception: row["services"]=[]
        row["distance_km"]=round(distance,2); out.append(row)
    out.sort(key=lambda x:x["distance_km"]); return {"count":len(out),"veterinarians":out}
@app.post("/user-reports/suspect")
def create_user_suspect(report:UserReport):
    payload=report.model_dump(); payload["external_id"]=f"USER-SUSPECT-{int(datetime.now(timezone.utc).timestamp())}"; payload["diagnosis_status"]="Sospetto"; payload["source_type"]="user"; payload["report_type"]="user_suspect"; payload["observation_date"]=payload.get("observation_date") or datetime.now(timezone.utc).date().isoformat(); r=upsert_event(payload); return {"status":r,"event":payload}
@app.post("/user-reports/positive")
def create_user_positive(report:UserReport):
    payload=report.model_dump(); payload["external_id"]=f"USER-POSITIVE-{int(datetime.now(timezone.utc).timestamp())}"; payload["diagnosis_status"]="Test rapido positivo"; payload["source_type"]="user"; payload["report_type"]="user_positive"; payload["source"]=payload.get("source") or "Leggi test rapido"; payload["observation_date"]=payload.get("observation_date") or datetime.now(timezone.utc).date().isoformat(); r=upsert_event(payload); return {"status":r,"event":payload}
