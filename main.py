from __future__ import annotations
import csv, io, json, math, os, random, sqlite3, re, subprocess, sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sync.official_connector import OfficialDemoConnector
from sync.wahis_csv_connector import WahisCsvConnector
from sync.adis_csv_connector import AdisCsvConnector
from sync.izs_benv_csv_connector import IzsBenvCsvConnector
from sync.myvbdmap_csv_connector import MyVbdMapCsvConnector
from sync.normalizer import normalize_official_event
from sync.deduplicator import deduplicate_public_events
from sync.event_enrichment import enrich_public_events
from sync.source_schema import REQUIRED_COLUMNS, OPTIONAL_COLUMNS, read_csv_text, validate_rows
from sync.bdn_connector import BdnDensityConnector, normalize_density_row
from sync.efsa_risk_connector import EfsaRiskLayerConnector, normalize_risk_layer
from sync.risk_summary import summarize_area_risk
from sync.territorial_layers_connector import load_territorial_layers, filter_territorial_layers, territorial_layers_csv_status
from sync.mosquito_alert_connector import sync_mosquito_alert_layers
from sync.vectornet_gbif_connector import sync_vectornet_gbif_layers
from sync.west_nile_connector import sync_west_nile_layers, west_nile_csv_status

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
TERRITORIAL_LAYERS_CSV_PATH=os.getenv("TERRITORIAL_LAYERS_CSV_PATH","data/territorial_layers/territorial_layers.csv")
WEST_NILE_CSV_PATH=os.getenv("WEST_NILE_CSV_PATH","data/territorial_layers/west_nile_surveillance.csv")
app=FastAPI(title="vet.ector Veterinary Alert API", version="2.3.4-territorial-automation-v143")
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

def get_bdn_density_items():
    connector = BdnDensityConnector()
    return [normalize_density_row(r) for r in connector.fetch()]

def get_efsa_risk_layers():
    connector = EfsaRiskLayerConnector()
    return [normalize_risk_layer(r) for r in connector.fetch()]

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
def sync_izs_benv_events():
    c=IzsBenvCsvConnector(); return _sync_rows(c.source_name,c.fetch(),"IZS_BENV")

def sync_myvbdmap_events():
    c=MyVbdMapCsvConnector(); started=now_iso(); ins=upd=skip=0; rows=c.fetch()
    for row in rows:
        try:
            row["source"] = row.get("source") or "MYVBDMAP"
            row["source_type"] = row.get("source_type") or "sentinel"
            row["report_type"] = row.get("report_type") or "veterinary_sentinel"
            row["diagnosis_status"] = row.get("diagnosis_status") or "Dato sentinella"
            r=upsert_event(row); ins+=r=="inserted"; upd+=r=="updated"
        except Exception as e:
            skip+=1; print("Skipped MyVBDMap sentinel event", e)
    log_sync(c.source_name,"success",f"{c.source_name} sync completed; skipped={skip}",len(rows),ins,upd,started)
    return {"status":"success","source":c.source_name,"received":len(rows),"inserted":ins,"updated":upd,"skipped":skip}
def sync_wahis_csv_text(csv_text, source_name="WAHIS_CSV_UPLOAD"):
    return _sync_rows(source_name,WahisCsvConnector.parse_csv_text(csv_text),"WAHIS")
def sync_adis_csv_text(csv_text, source_name="ADIS_CSV_UPLOAD"):
    return _sync_rows(source_name,AdisCsvConnector.parse_csv_text(csv_text),"ADIS")
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
    init_db(); sync_seed_data(); sync_official_events(); sync_wahis_events(); sync_adis_events(); sync_izs_benv_events(); sync_myvbdmap_events()
    if AUTO_POPULATE_DEMO_365: populate_demo_365(DEMO_365_COUNT)
    if ENABLE_SCHEDULER and not scheduler.running:
        scheduler.add_job(sync_official_events,"interval",hours=SYNC_INTERVAL_HOURS,id="official_sync",replace_existing=True); scheduler.add_job(sync_wahis_events,"interval",hours=SYNC_INTERVAL_HOURS,id="wahis_csv_sync",replace_existing=True); scheduler.add_job(sync_adis_events,"interval",hours=SYNC_INTERVAL_HOURS,id="adis_csv_sync",replace_existing=True); scheduler.add_job(sync_izs_benv_events,"interval",hours=SYNC_INTERVAL_HOURS,id="izs_benv_csv_sync",replace_existing=True); scheduler.add_job(sync_myvbdmap_events,"interval",hours=SYNC_INTERVAL_HOURS,id="myvbdmap_csv_sync",replace_existing=True); scheduler.start()
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
@app.post("/sync/adis/upload")
async def upload_adis_csv(request:Request,x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token); body=await request.body(); return sync_adis_csv_text(body.decode("utf-8-sig"),source_name="ADIS_CSV_UPLOAD")
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
@app.post("/sync/izs-benv/run")
def run_izs_benv_sync(): return sync_izs_benv_events()

@app.get("/sync/izs-benv/status")
def get_izs_benv_status():
    with connect() as conn: row=conn.execute("SELECT * FROM sync_log WHERE source LIKE 'IZS_BENV%' ORDER BY id DESC LIMIT 1").fetchone()
    return {"status":"never_run" if row is None else "ok", "last_sync": None if row is None else dict(row)}

@app.post("/sync/myvbdmap/run")
def run_myvbdmap_sync(): return sync_myvbdmap_events()

@app.get("/sync/myvbdmap/status")
def get_myvbdmap_status():
    with connect() as conn: row=conn.execute("SELECT * FROM sync_log WHERE source LIKE 'MYVBDMAP%' ORDER BY id DESC LIMIT 1").fetchone()
    return {"status":"never_run" if row is None else "ok", "last_sync": None if row is None else dict(row)}
@app.post("/sync/all/run")
def run_all_syncs(): return {"seed": sync_seed_data(),"official_demo": sync_official_events(),"wahis": sync_wahis_events(),"adis": sync_adis_events(),"izs_benv": sync_izs_benv_events(),"myvbdmap": sync_myvbdmap_events()}
@app.get("/sync/sources/schema")
def get_sync_sources_schema():
    return {"required_columns": sorted(REQUIRED_COLUMNS), "optional_columns": sorted(OPTIONAL_COLUMNS), "sources": ["WAHIS", "ADIS", "IZS_BENV", "MYVBDMAP"]}
@app.post("/sync/csv/validate")
async def validate_source_csv(request:Request,x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token); body=await request.body(); rows=read_csv_text(body.decode("utf-8-sig")); valid, errors=validate_rows(rows); return {"received":len(rows),"valid":len(valid),"errors":errors[:50],"error_count":len(errors)}
@app.get("/sync/remote-config")
def get_sync_remote_config():
    def configured(name):
        value=os.getenv(name,"").strip()
        return {"configured": bool(value), "url_preview": (value[:60]+"...") if len(value)>60 else value}
    return {
        "sync_interval_hours": SYNC_INTERVAL_HOURS,
        "scheduler_enabled": ENABLE_SCHEDULER,
        "wahis_remote_csv_url": configured("WAHIS_REMOTE_CSV_URL"),
        "adis_remote_csv_url": configured("ADIS_REMOTE_CSV_URL"),
        "source_remote_strict": os.getenv("SOURCE_REMOTE_STRICT","false").lower()=="true",
        "save_source_snapshots": os.getenv("SAVE_SOURCE_SNAPSHOTS","false").lower()=="true",
        "download_timeout_seconds": int(os.getenv("SOURCE_DOWNLOAD_TIMEOUT_SECONDS","30")),
        "fallback_order": ["remote_csv_url", "local_csv_file", "template_csv_file"]
    }
@app.get("/sync/status")
def get_sync_status():
    sources=["seed_data","OFFICIAL_DEMO","WAHIS_CSV","WAHIS_CSV_UPLOAD","ADIS_CSV","IZS_BENV_CSV","MYVBDMAP_CSV","demo_365","TERRITORIAL_LAYERS","MOSQUITO_ALERT_TERRITORIAL","VECTORNET_GBIF_TERRITORIAL","ISS_IZS_WNV_TERRITORIAL","TERRITORIAL_LAYERS_ALL"]
    out={}
    with connect() as conn:
        for source in sources:
            row=conn.execute("SELECT * FROM sync_log WHERE source=? ORDER BY id DESC LIMIT 1",(source,)).fetchone()
            out[source]=None if row is None else dict(row)
    return {"version":app.version,"sync_interval_hours":SYNC_INTERVAL_HOURS,"sources":out}
@app.get("/risk/livestock-density")
def get_livestock_density(country:str=Query("Italy"), species:str=Query("all"), region:str|None=Query(None), province:str|None=Query(None)):
    data=get_bdn_density_items()
    country_l=str(country or "").lower().strip()
    species_l=str(species or "all").lower().strip()
    region_l=str(region or "").lower().strip()
    province_l=str(province or "").lower().strip()
    out=[]
    for row in data:
        if country_l and str(row.get("country","")).lower()!=country_l: continue
        if species_l and species_l!="all" and species_l not in str(row.get("species","")).lower(): continue
        if region_l and region_l not in str(row.get("region","")).lower(): continue
        if province_l and province_l not in str(row.get("province","")).lower(): continue
        out.append(row)
    return {"count":len(out),"items":out}

@app.get("/risk/efsa-layers")
def get_efsa_layers(species:str=Query("all"), disease:str|None=Query(None)):
    data=get_efsa_risk_layers()
    species_l=str(species or "all").lower().strip()
    disease_l=str(disease or "").lower().strip()
    out=[]
    for row in data:
        if disease_l and disease_l not in f"{row.get('disease','')} {row.get('disease_key','')}".lower(): continue
        if species_l and species_l!="all":
            if not any(species_l in str(sp).lower() for sp in row.get("species",[])): continue
        out.append(row)
    return {"count":len(out),"items":out}

@app.get("/risk/area-summary")
def get_area_summary(lat:float=Query(...), lon:float=Query(...), radius_km:float=Query(50,ge=1,le=2000), days:int=Query(180,ge=1,le=3650), animal_filter:str=Query("all")):
    events_response=get_events(lat=lat, lon=lon, radius_km=radius_km, days=days, animal_filter=animal_filter, disease=None, include_official=True, include_user=True)
    events=events_response.get("events",[])
    density=get_bdn_density_items()
    layers=get_efsa_risk_layers()
    return summarize_area_risk(events,density,layers,species=animal_filter)



@app.post("/sync/territorial-layers/all/run")
def run_all_territorial_layers_sync(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    try:
        p=subprocess.run([sys.executable,"scripts/refresh_territorial_layers_all.py"],capture_output=True,text=True,timeout=int(os.getenv("TERRITORIAL_REFRESH_TIMEOUT_SECONDS","600")))
        if p.returncode!=0:
            log_sync("TERRITORIAL_LAYERS_ALL","error",(p.stderr or p.stdout)[-1000:],0,0,0,started)
            raise HTTPException(status_code=500, detail=(p.stderr or p.stdout)[-4000:])
        status_path="data/territorial_layers/refresh_status.json"
        status=load_json(status_path) if os.path.exists(status_path) else {"stdout":p.stdout[-4000:]}
        received=int(status.get("validation",{}).get("rows",0) or 0)
        log_sync("TERRITORIAL_LAYERS_ALL","success","All territorial layers refreshed",received,0,0,started)
        return {"status":"success","refresh":status}
    except HTTPException:
        raise
    except Exception as e:
        log_sync("TERRITORIAL_LAYERS_ALL","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/territorial-layers/status")
def get_territorial_layers_public_status():
    status_path="data/territorial_layers/refresh_status.json"
    status=load_json(status_path) if os.path.exists(status_path) else {}
    csv_status=territorial_layers_csv_status(TERRITORIAL_LAYERS_CSV_PATH)
    return {"status":"ok","csv":csv_status,"refresh":status}

@app.get("/territorial-layers")
def get_territorial_layers(lat:float|None=Query(None),lon:float|None=Query(None),radius_km:float=Query(100,ge=1,le=2000),category:str=Query("all"),days:int=Query(365,ge=1,le=3650),source:str|None=Query(None)):
    layers=load_territorial_layers(TERRITORIAL_LAYERS_CSV_PATH)
    out=filter_territorial_layers(layers, lat=lat, lon=lon, radius_km=radius_km, category=category, days=days, source=source, distance_fn=haversine_km, parse_date_fn=parse_date)
    return {"count":len(out),"layers":out,"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days}

@app.get("/territorial-layers/export")
def export_territorial_layers(category:str=Query("all"),format:str=Query("csv")):
    layers=filter_territorial_layers(load_territorial_layers(TERRITORIAL_LAYERS_CSV_PATH), category=category, distance_fn=haversine_km, parse_date_fn=parse_date)
    if format.lower()=="json": return {"count":len(layers),"layers":layers}
    fields=["id","external_id","category","source","display_source","label","scientific_name","data_type","count","period_start","period_end","country","region","province","location","lat","lon","radius_km","color","url_source","notes"]
    output=io.StringIO(); writer=csv.DictWriter(output, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(layers); output.seek(0)
    return Response(content=output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition":"attachment; filename=vetector_territorial_layers.csv"})

@app.post("/sync/territorial-layers/run")
def run_territorial_layers_sync(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    status=territorial_layers_csv_status(TERRITORIAL_LAYERS_CSV_PATH)
    state="success" if status.get("exists") else "missing"
    message="Territorial layers CSV validated" if status.get("exists") else "Territorial layers CSV missing"
    log_sync("TERRITORIAL_LAYERS",state,message,status.get("rows",0),0,0,started)
    return {"status":state,"message":message,"csv":status}


@app.post("/sync/territorial-layers/mosquito-alert/run")
def run_mosquito_alert_territorial_sync(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    try:
        result=sync_mosquito_alert_layers(TERRITORIAL_LAYERS_CSV_PATH)
        log_sync("MOSQUITO_ALERT_TERRITORIAL","success",result.get("message","Mosquito Alert territorial sync completed"),result.get("records_read",0),result.get("rows_inserted",0),result.get("rows_updated",0),started)
        return result
    except Exception as e:
        log_sync("MOSQUITO_ALERT_TERRITORIAL","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync/territorial-layers/vectornet-gbif/run")
def run_vectornet_gbif_territorial_sync(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    try:
        result=sync_vectornet_gbif_layers(TERRITORIAL_LAYERS_CSV_PATH)
        log_sync("VECTORNET_GBIF_TERRITORIAL","success",result.get("message","VectorNet/GBIF territorial sync completed"),result.get("records_read",0),result.get("rows_inserted",0),result.get("rows_updated",0),started)
        return result
    except Exception as e:
        log_sync("VECTORNET_GBIF_TERRITORIAL","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync/territorial-layers/west-nile/run")
def run_west_nile_territorial_sync(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    try:
        result=sync_west_nile_layers(TERRITORIAL_LAYERS_CSV_PATH, WEST_NILE_CSV_PATH)
        log_sync("ISS_IZS_WNV_TERRITORIAL","success",result.get("message","West Nile territorial sync completed"),result.get("records_read",0),result.get("rows_inserted",0),result.get("rows_updated",0),started)
        return result
    except Exception as e:
        log_sync("ISS_IZS_WNV_TERRITORIAL","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sync/territorial-layers/west-nile/status")
def get_west_nile_territorial_status():
    with connect() as conn: row=conn.execute("SELECT * FROM sync_log WHERE source='ISS_IZS_WNV_TERRITORIAL' ORDER BY id DESC LIMIT 1").fetchone()
    return {"status":"never_run" if row is None else "ok", "csv": west_nile_csv_status(WEST_NILE_CSV_PATH), "last_sync": None if row is None else dict(row)}

@app.get("/sync/territorial-layers/status")
def get_territorial_layers_status():
    with connect() as conn: row=conn.execute("SELECT * FROM sync_log WHERE source='TERRITORIAL_LAYERS' ORDER BY id DESC LIMIT 1").fetchone()
    return {"status":"never_run" if row is None else "ok", "csv": territorial_layers_csv_status(TERRITORIAL_LAYERS_CSV_PATH), "last_sync": None if row is None else dict(row)}

@app.get("/sources/registry")
def get_sources_registry():
    return {
        "event_sources":[
            {"key":"WAHIS","type":"official","role":"global official animal disease events"},
            {"key":"ADIS","type":"official","role":"EU official animal disease events"},
            {"key":"IZS_BENV","type":"official","role":"Italian BENV/IZS official veterinary outbreak events"},
            {"key":"MYVBDMAP","type":"sentinel","role":"veterinary sentinel data for canine vector-borne diseases"},
            {"key":"user_report","type":"user","role":"suspect reports from platform users"},
            {"key":"rapid_test","type":"user","role":"rapid test positive reports"},
            {"key":"veterinarian","type":"professional","role":"veterinarian validated reports"},
            {"key":"Demo 365 giorni","type":"demo","role":"temporary prototype data"}
        ],
        "context_sources":[
            {"key":"BDN","type":"risk_context","role":"Italian livestock density/exposure context"},
            {"key":"EFSA","type":"risk_context","role":"risk/trend/scientific context, not point events"},
            {"key":"MOSQUITO_ALERT","type":"territorial_layer","role":"validated mosquito observations and breeding-site context"},
            {"key":"VECTORNET","type":"territorial_layer","role":"validated vector occurrence data from ECDC/EFSA/GBIF"},
            {"key":"ESCCAP","type":"territorial_layer","role":"aggregate parasite positive-test context for screened pets"},
            {"key":"ISS_IZS_WNV","type":"territorial_layer","role":"West Nile / Usutu integrated surveillance context"}
        ]
    }
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
