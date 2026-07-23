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
app=FastAPI(title="vet.ector Veterinary Alert API", version="2.3.5-data-sources-status-v170")
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


# --- v6 FastAPI/SQLite vector surveillance endpoints ---
LEISHMANIASIS_VECTOR_SPECIES = [
    {
        "id": "phlebotomus_perniciosus",
        "scientific_name": "Phlebotomus perniciosus",
        "common_group": "sand_fly",
        "pathogen_focus": "Leishmania infantum",
        "is_leishmaniasis_vector": 1,
        "vector_status": "known_or_primary_vector",
        "priority": 1,
        "notes": "High priority for the leishmaniasis pilot in Italy.",
        "source": "ECDC VectorNet / GBIF / literature",
        "source_url": "https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps",
    },
    {
        "id": "phlebotomus_perfiliewi",
        "scientific_name": "Phlebotomus perfiliewi",
        "common_group": "sand_fly",
        "pathogen_focus": "Leishmania infantum",
        "is_leishmaniasis_vector": 1,
        "vector_status": "known_or_suspected_vector",
        "priority": 2,
        "notes": "Priority sand fly species included in ECDC phlebotomine maps.",
        "source": "ECDC VectorNet",
        "source_url": "https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps",
    },
    {
        "id": "phlebotomus_neglectus",
        "scientific_name": "Phlebotomus neglectus",
        "common_group": "sand_fly",
        "pathogen_focus": "Leishmania infantum",
        "is_leishmaniasis_vector": 1,
        "vector_status": "known_or_suspected_vector",
        "priority": 3,
        "notes": "Priority sand fly species for leishmaniasis context.",
        "source": "ECDC VectorNet / literature",
        "source_url": "https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps",
    },
    {
        "id": "phlebotomus_ariasi",
        "scientific_name": "Phlebotomus ariasi",
        "common_group": "sand_fly",
        "pathogen_focus": "Leishmania infantum",
        "is_leishmaniasis_vector": 1,
        "vector_status": "known_or_suspected_vector",
        "priority": 4,
        "notes": "Priority sand fly species included in ECDC phlebotomine maps.",
        "source": "ECDC VectorNet",
        "source_url": "https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps",
    },
    {
        "id": "phlebotomus_mascitii",
        "scientific_name": "Phlebotomus mascitii",
        "common_group": "sand_fly",
        "pathogen_focus": "Leishmania infantum",
        "is_leishmaniasis_vector": 1,
        "vector_status": "possible_vector_or_presence_indicator",
        "priority": 5,
        "notes": "Use as context layer until expert veterinary validation.",
        "source": "ECDC VectorNet",
        "source_url": "https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps",
    },
    {
        "id": "phlebotomus_papatasi",
        "scientific_name": "Phlebotomus papatasi",
        "common_group": "sand_fly",
        "pathogen_focus": "Leishmania spp. / phleboviruses",
        "is_leishmaniasis_vector": 1,
        "vector_status": "vector_relevance_mediterranean",
        "priority": 6,
        "notes": "Relevant for Mediterranean vector surveillance context.",
        "source": "ECDC VectorNet",
        "source_url": "https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps",
    },
    {
        "id": "phlebotomus_sergenti",
        "scientific_name": "Phlebotomus sergenti",
        "common_group": "sand_fly",
        "pathogen_focus": "Leishmania tropica",
        "is_leishmaniasis_vector": 1,
        "vector_status": "vector_relevance_mediterranean",
        "priority": 7,
        "notes": "Monitor for broader leishmaniasis context.",
        "source": "ECDC VectorNet",
        "source_url": "https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps",
    },
    {
        "id": "phlebotomus_tobbi",
        "scientific_name": "Phlebotomus tobbi",
        "common_group": "sand_fly",
        "pathogen_focus": "Leishmania infantum",
        "is_leishmaniasis_vector": 1,
        "vector_status": "vector_relevance_mediterranean",
        "priority": 8,
        "notes": "Monitor for wider Mediterranean context.",
        "source": "ECDC VectorNet",
        "source_url": "https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps",
    },
]

def init_vector_surveillance_db():
    with connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS vector_species_catalog(
            id TEXT PRIMARY KEY,
            scientific_name TEXT NOT NULL,
            common_group TEXT NOT NULL,
            pathogen_focus TEXT,
            is_leishmaniasis_vector INTEGER DEFAULT 0,
            vector_status TEXT,
            priority INTEGER DEFAULT 100,
            notes TEXT,
            source TEXT,
            source_url TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS vector_occurrences(
            id TEXT PRIMARY KEY,
            scientific_name TEXT NOT NULL,
            common_group TEXT,
            pathogen_focus TEXT,
            occurrence_status TEXT,
            event_date TEXT,
            year INTEGER,
            country TEXT DEFAULT 'Italy',
            region TEXT,
            province TEXT,
            municipality TEXT,
            locality TEXT,
            lat REAL,
            lon REAL,
            coordinate_uncertainty_m REAL,
            source TEXT,
            source_dataset TEXT,
            source_url TEXT,
            license TEXT,
            confidence_score INTEGER DEFAULT 70,
            raw_payload TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vector_occurrences_species ON vector_occurrences(scientific_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vector_occurrences_focus ON vector_occurrences(pathogen_focus)")
        conn.commit()

def seed_leishmaniasis_vector_species():
    with connect() as conn:
        for row in LEISHMANIASIS_VECTOR_SPECIES:
            conn.execute("""INSERT INTO vector_species_catalog(
                id, scientific_name, common_group, pathogen_focus,
                is_leishmaniasis_vector, vector_status, priority,
                notes, source, source_url, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                scientific_name=excluded.scientific_name,
                common_group=excluded.common_group,
                pathogen_focus=excluded.pathogen_focus,
                is_leishmaniasis_vector=excluded.is_leishmaniasis_vector,
                vector_status=excluded.vector_status,
                priority=excluded.priority,
                notes=excluded.notes,
                source=excluded.source,
                source_url=excluded.source_url,
                updated_at=CURRENT_TIMESTAMP""", (
                row["id"], row["scientific_name"], row["common_group"], row["pathogen_focus"],
                row["is_leishmaniasis_vector"], row["vector_status"], row["priority"],
                row["notes"], row["source"], row["source_url"]
            ))
        conn.commit()

def _vector_occurrence_to_public(row, distance_km=None):
    out = {
        "id": row.get("id"),
        "scientific_name": row.get("scientific_name"),
        "common_group": row.get("common_group"),
        "pathogen_focus": row.get("pathogen_focus"),
        "occurrence_status": row.get("occurrence_status"),
        "event_date": row.get("event_date"),
        "year": row.get("year"),
        "country": row.get("country"),
        "region": row.get("region"),
        "province": row.get("province"),
        "municipality": row.get("municipality"),
        "locality": row.get("locality"),
        "lat": row.get("lat"),
        "lon": row.get("lon"),
        "coordinate_uncertainty_m": row.get("coordinate_uncertainty_m"),
        "source": row.get("source"),
        "source_dataset": row.get("source_dataset"),
        "source_url": row.get("source_url"),
        "license": row.get("license"),
        "confidence_score": row.get("confidence_score"),
    }
    if distance_km is not None:
        out["distance_km"] = round(distance_km, 2)
    return out

def _layer_matches_vector_filters(layer, species="all", focus="all", leishmaniasis=False):
    species_l = str(species or "all").lower().strip()
    focus_l = str(focus or "all").lower().strip()
    hay = " ".join(str(layer.get(k, "")) for k in ["label", "scientific_name", "data_type", "notes", "source", "display_source"]).lower()
    if species_l and species_l != "all":
        if species_l not in str(layer.get("scientific_name") or layer.get("label") or "").lower():
            return False
    if focus_l and focus_l != "all" and focus_l not in hay:
        return False
    if leishmaniasis and "leish" not in hay and "phlebotomus" not in hay:
        return False
    return True
# --- end v6 vector endpoints support ---


# --- v7 VectorNet/GBIF occurrence sync for SQLite backend ---
VECTORNET_GBIF_API = os.getenv("VECTORNET_GBIF_API", "https://api.gbif.org/v1/occurrence/search")
VECTORNET_PUBLISHER_KEY = os.getenv("VECTORNET_PUBLISHER_KEY", "8f9f9814-a595-4bc3-8631-776ba3c9c62e")
VECTORNET_COUNTRY = os.getenv("VECTORNET_COUNTRY", "IT")
VECTORNET_LIMIT_PER_SPECIES = int(os.getenv("VECTORNET_LIMIT_PER_SPECIES", "200"))
VECTORNET_MAX_PAGES_PER_SPECIES = int(os.getenv("VECTORNET_MAX_PAGES_PER_SPECIES", "2"))
VECTORNET_SYNC_INTERVAL_HOURS = int(os.getenv("VECTORNET_SYNC_INTERVAL_HOURS", "168"))
VECTORNET_DEFAULT_SPECIES = ["Phlebotomus perniciosus","Phlebotomus perfiliewi","Phlebotomus neglectus","Phlebotomus ariasi","Phlebotomus mascitii","Phlebotomus papatasi","Phlebotomus sergenti","Phlebotomus tobbi"]

def _stable_vector_id(*parts):
    import hashlib
    return hashlib.sha1("|".join(str(p or "").lower().strip() for p in parts).encode("utf-8")).hexdigest()[:32]

def _gbif_get_json(params):
    import urllib.parse, urllib.request
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(VECTORNET_GBIF_API + "?" + query, headers={"User-Agent":"vetector-fastapi-vectornet-sync/7.0"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _vector_group_for_species(scientific_name:str):
    s=str(scientific_name or "").lower()
    if s.startswith("phlebotomus"): return "sand_fly"
    if "culex" in s or "aedes" in s: return "mosquito"
    if "ixodes" in s: return "tick"
    return "vector"

def _vector_focus_for_species(scientific_name:str):
    s=str(scientific_name or "").lower()
    if s.startswith("phlebotomus"):
        if "sergenti" in s: return "Leishmania tropica / leishmaniasis vector"
        return "Leishmania infantum / leishmaniasis vector"
    return None

def upsert_vector_occurrence(row):
    init_vector_surveillance_db()
    with connect() as conn:
        existing=conn.execute("SELECT id FROM vector_occurrences WHERE id=?", (row["id"],)).fetchone()
        conn.execute("""INSERT INTO vector_occurrences(
            id, scientific_name, common_group, pathogen_focus, occurrence_status,
            event_date, year, country, region, province, municipality, locality,
            lat, lon, coordinate_uncertainty_m, source, source_dataset, source_url,
            license, confidence_score, raw_payload, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            scientific_name=excluded.scientific_name,
            common_group=excluded.common_group,
            pathogen_focus=excluded.pathogen_focus,
            occurrence_status=excluded.occurrence_status,
            event_date=excluded.event_date,
            year=excluded.year,
            country=excluded.country,
            region=excluded.region,
            province=excluded.province,
            municipality=excluded.municipality,
            locality=excluded.locality,
            lat=excluded.lat,
            lon=excluded.lon,
            coordinate_uncertainty_m=excluded.coordinate_uncertainty_m,
            source=excluded.source,
            source_dataset=excluded.source_dataset,
            source_url=excluded.source_url,
            license=excluded.license,
            confidence_score=excluded.confidence_score,
            raw_payload=excluded.raw_payload,
            updated_at=CURRENT_TIMESTAMP""", (
            row.get("id"), row.get("scientific_name"), row.get("common_group"), row.get("pathogen_focus"), row.get("occurrence_status"),
            row.get("event_date"), row.get("year"), row.get("country"), row.get("region"), row.get("province"), row.get("municipality"), row.get("locality"),
            row.get("lat"), row.get("lon"), row.get("coordinate_uncertainty_m"), row.get("source"), row.get("source_dataset"), row.get("source_url"),
            row.get("license"), row.get("confidence_score"), row.get("raw_payload")
        ))
        conn.commit()
    return "updated" if existing else "inserted"

def _normalize_gbif_vector_occurrence(item, requested_species):
    lat=item.get("decimalLatitude"); lon=item.get("decimalLongitude")
    if lat is None or lon is None: return None
    scientific=item.get("scientificName") or requested_species
    gbif_id=item.get("key") or item.get("gbifID") or item.get("occurrenceID")
    return {
        "id":"gbif-vector-" + _stable_vector_id(gbif_id, scientific, lat, lon),
        "scientific_name":scientific,
        "common_group":_vector_group_for_species(scientific),
        "pathogen_focus":_vector_focus_for_species(scientific),
        "occurrence_status":item.get("occurrenceStatus") or "PRESENT",
        "event_date":str(item.get("eventDate") or "")[:10] or None,
        "year":item.get("year"),
        "country":item.get("country") or "Italy",
        "region":item.get("stateProvince"),
        "province":item.get("county"),
        "municipality":item.get("municipality"),
        "locality":item.get("locality"),
        "lat":float(lat),
        "lon":float(lon),
        "coordinate_uncertainty_m":item.get("coordinateUncertaintyInMeters"),
        "source":"VectorNet / GBIF",
        "source_dataset":item.get("datasetName") or item.get("datasetKey"),
        "source_url":"https://www.gbif.org/occurrence/" + str(gbif_id) if gbif_id else "https://www.gbif.org/",
        "license":item.get("license"),
        "confidence_score":90 if str(scientific).lower().startswith("phlebotomus") else 75,
        "raw_payload":json.dumps(item, ensure_ascii=False),
    }

def sync_vectornet_gbif_occurrences(species_list=None, limit_per_species=None, max_pages=None):
    init_vector_surveillance_db(); seed_leishmaniasis_vector_species()
    species_list = species_list or [s.strip() for s in os.getenv("VECTORNET_SPECIES", ",".join(VECTORNET_DEFAULT_SPECIES)).split(",") if s.strip()]
    limit_per_species = int(limit_per_species or VECTORNET_LIMIT_PER_SPECIES)
    max_pages = int(max_pages or VECTORNET_MAX_PAGES_PER_SPECIES)
    started=now_iso(); fetched=inserted=updated=skipped=0
    try:
        for species in species_list:
            offset=0; pages=0
            while offset < limit_per_species and pages < max_pages:
                page_limit=min(300, limit_per_species-offset)
                params={"country":VECTORNET_COUNTRY,"scientificName":species,"hasCoordinate":"true","limit":page_limit,"offset":offset}
                if VECTORNET_PUBLISHER_KEY: params["publishingOrg"] = VECTORNET_PUBLISHER_KEY
                payload=_gbif_get_json(params)
                batch=payload.get("results", [])
                fetched += len(batch)
                if not batch: break
                for item in batch:
                    row=_normalize_gbif_vector_occurrence(item, species)
                    if not row:
                        skipped += 1; continue
                    status=upsert_vector_occurrence(row)
                    inserted += status=="inserted"; updated += status=="updated"
                offset += len(batch); pages += 1
                if payload.get("endOfRecords"): break
        log_sync("VECTORNET_GBIF_OCCURRENCES", "success", "VectorNet/GBIF occurrence sync completed", fetched, inserted, updated, started)
        return {"status":"success","source":"VECTORNET_GBIF_OCCURRENCES","species":species_list,"fetched":fetched,"inserted":inserted,"updated":updated,"skipped":skipped}
    except Exception as e:
        log_sync("VECTORNET_GBIF_OCCURRENCES", "error", str(e), fetched, inserted, updated, started)
        raise
# --- end v7 VectorNet/GBIF sync ---

@app.on_event("startup")
def startup():
    init_db(); init_vector_surveillance_db(); seed_leishmaniasis_vector_species(); sync_seed_data(); sync_official_events(); sync_wahis_events(); sync_adis_events(); sync_izs_benv_events(); sync_myvbdmap_events()
    if AUTO_POPULATE_DEMO_365: populate_demo_365(DEMO_365_COUNT)
    if ENABLE_SCHEDULER and not scheduler.running:
        scheduler.add_job(sync_official_events,"interval",hours=SYNC_INTERVAL_HOURS,id="official_sync",replace_existing=True); scheduler.add_job(sync_wahis_events,"interval",hours=SYNC_INTERVAL_HOURS,id="wahis_csv_sync",replace_existing=True); scheduler.add_job(sync_adis_events,"interval",hours=SYNC_INTERVAL_HOURS,id="adis_csv_sync",replace_existing=True); scheduler.add_job(sync_izs_benv_events,"interval",hours=SYNC_INTERVAL_HOURS,id="izs_benv_csv_sync",replace_existing=True); scheduler.add_job(sync_myvbdmap_events,"interval",hours=SYNC_INTERVAL_HOURS,id="myvbdmap_csv_sync",replace_existing=True); scheduler.add_job(sync_vectornet_gbif_occurrences,"interval",hours=VECTORNET_SYNC_INTERVAL_HOURS,id="vectornet_gbif_occurrences_sync",replace_existing=True); scheduler.start()
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


# --- v8: merge real vector occurrence data into /territorial-layers ---
def _vector_occurrence_layer(row, distance_km=None):
    scientific = row.get("scientific_name") or "Vector occurrence"
    focus = row.get("pathogen_focus") or ""
    leish = "leish" in f"{scientific} {focus}".lower() or str(scientific).lower().startswith("phlebotomus")
    uncertainty = row.get("coordinate_uncertainty_m")
    try:
        radius_km = max(5, min(25, float(uncertainty) / 1000.0)) if uncertainty is not None else 8
    except Exception:
        radius_km = 8
    return {
        "id": "vector-occurrence-layer-" + str(row.get("id")),
        "external_id": row.get("id"),
        "category": "vectors",
        "label": scientific,
        "scientific_name": scientific,
        "data_type": "Vector occurrence / leishmaniasis vector" if leish else "Vector occurrence",
        "count": 1,
        "count_label": "occurrence record",
        "period": row.get("event_date") or str(row.get("year") or "n/d"),
        "period_start": row.get("event_date"),
        "period_end": row.get("event_date"),
        "country": row.get("country") or "Italy",
        "region": row.get("region") or "",
        "province": row.get("province") or "",
        "location": row.get("locality") or row.get("municipality") or row.get("province") or row.get("region") or "",
        "lat": row.get("lat"),
        "lon": row.get("lon"),
        "radius_km": radius_km,
        "aggregation_level": "occurrence_point",
        "source": row.get("source") or "VectorNet / GBIF",
        "display_source": row.get("source") or "VectorNet / GBIF",
        "url_source": row.get("source_url") or "https://www.vectornetdata.org/",
        "notes": "Real vector occurrence from VectorNet/GBIF; context data, not a disease diagnosis." + (" High-priority leishmaniasis vector." if leish else ""),
        "distance_km": None if distance_km is None else round(distance_km, 2),
        "confidence_score": row.get("confidence_score"),
    }

def vector_occurrence_layers_for_area(lat=None, lon=None, radius_km=100, species="all", focus="all", leishmaniasis=False, source=None, limit=1500):
    init_vector_surveillance_db()
    species_l = str(species or "all").lower().strip()
    focus_l = str(focus or "all").lower().strip()
    source_l = str(source or "").lower().strip()
    with connect() as conn:
        try:
            rows = [dict(r) for r in conn.execute("SELECT * FROM vector_occurrences ORDER BY COALESCE(event_date,'') DESC, COALESCE(year,0) DESC LIMIT ?", (limit,)).fetchall()]
        except Exception:
            rows = []
    out=[]
    for row in rows:
        if row.get("lat") is None or row.get("lon") is None: continue
        hay = f"{row.get('scientific_name','')} {row.get('pathogen_focus','')} {row.get('common_group','')} {row.get('source','')}".lower()
        if species_l and species_l != "all" and species_l not in str(row.get("scientific_name","")).lower(): continue
        if focus_l and focus_l != "all" and focus_l not in hay: continue
        if leishmaniasis and "leish" not in hay and "phlebotomus" not in hay: continue
        if source_l and source_l != "all" and source_l not in hay: continue
        distance=None
        if lat is not None and lon is not None:
            distance = haversine_km(float(lat), float(lon), float(row["lat"]), float(row["lon"]))
            # include occurrence if point is inside selected radius plus its uncertainty radius
            try:
                uncertainty_km = max(0, float(row.get("coordinate_uncertainty_m") or 0) / 1000.0)
            except Exception:
                uncertainty_km = 0
            if distance > float(radius_km) + min(25, uncertainty_km): continue
        out.append(_vector_occurrence_layer(row, distance))
    return out
# --- end v8 real vector layers ---


# --- v219 minimal: backend-owned UI grouping for territorial map layers ---
UI_GROUP_LABELS = {
    "sand_flies": "Flebotomi",
    "ticks": "Zecche",
    "mosquitoes_other_vectors": "Zanzare / altri vettori",
    "parasites": "Parassiti",
    "west_nile": "West Nile",
}

def _vetector_ui_text(row):
    keys = [
        "category", "label", "scientific_name", "common_group", "pathogen_focus",
        "data_type", "type", "source", "display_source", "notes", "note"
    ]
    return " ".join(str(row.get(k, "")) for k in keys if row.get(k) is not None).lower()

def vetector_ui_group(row):
    category = str(row.get("category") or "").lower().strip()
    text = _vetector_ui_text(row)

    if category == "west_nile" or "west nile" in text or "usutu" in text:
        return "west_nile"

    if (
        category in {"parasites", "parasite"}
        or "giardia" in text or "toxocara" in text or "ancylostoma" in text
        or "dirofilaria" in text or "echinococcus" in text
        or "parasite" in text or "parassit" in text
    ):
        return "parasites"

    if (
        "phlebotomus" in text or "phlebotominae" in text or "phlebotomine" in text
        or "sand fly" in text or "sandfly" in text or "sand_fly" in text
        or "flebotom" in text
        or ((category in {"vectors", "vector"}) and (
            "leishmania" in text or "leishmaniosi" in text or "leishmaniasis" in text or "leish" in text
        ))
    ):
        return "sand_flies"

    if (
        "ixodes" in text or "dermacentor" in text or "hyalomma" in text
        or "rhipicephalus" in text or "ornithodoros" in text or "amblyomma" in text
        or "tick" in text or "zecc" in text
    ):
        return "ticks"

    if (
        category in {"vectors", "vector"}
        or "aedes" in text or "culex" in text or "anopheles" in text
        or "culicoides" in text or "mosquito" in text or "zanzar" in text or "midge" in text
    ):
        return "mosquitoes_other_vectors"

    # Safe fallback: keep unknown territorial records visible as other vectors.
    return "mosquitoes_other_vectors"

def vetector_localization_precision(row):
    def has_value(*keys):
        return any(str(row.get(k) or "").strip() for k in keys)

    lat = row.get("lat")
    lon = row.get("lon")
    try:
        if lat is not None and lon is not None and str(lat) != "" and str(lon) != "":
            float(lat)
            float(lon)
            return "coordinate / puntuale"
    except Exception:
        pass

    if has_value("municipality", "comune", "city", "location", "locality", "area_label", "area"):
        return "comunale"
    if has_value("province"):
        return "provinciale"
    if has_value("region"):
        return "regionale"
    return "territoriale"

def vetector_display_radius_km(precision):
    return 10 if precision in {"coordinate / puntuale", "comunale"} else 25

def apply_ui_group(row):
    out = dict(row)
    group = vetector_ui_group(out)
    precision = vetector_localization_precision(out)
    out["ui_group"] = group
    out["ui_group_label"] = UI_GROUP_LABELS.get(group, group)
    out["subcategory"] = group
    out["localization_precision"] = precision
    out["display_radius_km"] = vetector_display_radius_km(precision)
    return out

def apply_ui_groups(rows):
    return [apply_ui_group(r) for r in (rows or [])]

def ui_group_counts(rows):
    stats = {}
    for r in rows or []:
        g = r.get("ui_group") or vetector_ui_group(r)
        stats[g] = stats.get(g, 0) + 1
    return stats
# --- end v219 minimal UI grouping ---


@app.post("/sync/territorial-layers/real-events/run")
def run_real_events_territorial_sync(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    try:
        timeout=int(os.getenv("REAL_EVENTS_IMPORT_TIMEOUT_SECONDS","1200"))
        p=subprocess.run([sys.executable,"scripts/import_gbif_real_vector_events_v230.py"],capture_output=True,text=True,timeout=timeout)
        if p.returncode!=0:
            log_sync("REAL_GBIF_VECTOR_EVENTS","error",(p.stderr or p.stdout)[-1000:],0,0,0,started)
            raise HTTPException(status_code=500, detail=(p.stderr or p.stdout)[-4000:])
        try: result=json.loads(p.stdout)
        except Exception: result={"stdout":p.stdout[-4000:]}
        log_sync("REAL_GBIF_VECTOR_EVENTS","success","Real GBIF vector events imported",int(result.get("candidate_rows",0) or 0),int(result.get("inserted",0) or 0),int(result.get("updated",0) or 0),started)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_sync("REAL_GBIF_VECTOR_EVENTS","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync/territorial-layers/normalize-radius/run")
def run_territorial_radius_normalization(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    try:
        p=subprocess.run([sys.executable,"scripts/normalize_territorial_layers_radius_v232.py"],capture_output=True,text=True,timeout=int(os.getenv("TERRITORIAL_NORMALIZE_TIMEOUT_SECONDS","300")))
        if p.returncode!=0:
            log_sync("TERRITORIAL_RADIUS_NORMALIZE","error",(p.stderr or p.stdout)[-1000:],0,0,0,started)
            raise HTTPException(status_code=500, detail=(p.stderr or p.stdout)[-4000:])
        try: result=json.loads(p.stdout)
        except Exception: result={"stdout":p.stdout[-4000:]}
        log_sync("TERRITORIAL_RADIUS_NORMALIZE","success","Territorial radius, cases and ui_group normalized",int(result.get("rows",0) or 0),0,int(result.get("changed",0) or 0),started)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_sync("TERRITORIAL_RADIUS_NORMALIZE","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))

def _territorial_output_precision(row):
    explicit=" ".join(str(row.get(k,"") or "").lower() for k in ["localization_precision","aggregation_level","precision","area_level"])
    if "region" in explicit: return "regionale"
    if "prov" in explicit: return "provinciale"
    if "comun" in explicit or "municip" in explicit: return "comunale"
    if "point" in explicit or "coord" in explicit: return "coordinate / puntuale"
    try:
        if row.get("lat") not in (None,"") and row.get("lon") not in (None,""):
            float(row.get("lat")); float(row.get("lon")); return "coordinate / puntuale"
    except Exception: pass
    if any(str(row.get(k,"") or "").strip() for k in ["municipality","comune","city","locality","location"]): return "comunale"
    if str(row.get("province","") or "").strip(): return "provinciale"
    if str(row.get("region","") or "").strip(): return "regionale"
    return "territoriale"
def _territorial_output_group(row):
    t=" ".join(str(row.get(k,"") or "") for k in ["category","label","scientific_name","data_type","source","notes","note"]).lower()
    cat=str(row.get("category","") or "").lower()
    if cat=="west_nile" or "west nile" in t or "usutu" in t: return "west_nile"
    if cat in ("parasites","parasite") or any(x in t for x in ["giardia","toxocara","ancylostoma","dirofilaria","echinococcus","parasite","parassit"]): return "parasites"
    if any(x in t for x in ["phlebotomus","phlebotominae","phlebotomine","sand fly","sandfly","flebotom","leish"]): return "sand_flies"
    if any(x in t for x in ["ixodes","dermacentor","hyalomma","rhipicephalus","ornithodoros","amblyomma","tick","zecc"]): return "ticks"
    return "mosquitoes_other_vectors" if cat in ("vectors","vector") else cat or "mosquitoes_other_vectors"
def _decorate_territorial_output(rows):
    labels={"sand_flies":"Flebotomi","ticks":"Zecche","mosquitoes_other_vectors":"Zanzare / altri vettori","parasites":"Parassiti","west_nile":"West Nile"}
    out=[]
    for r in rows or []:
        x=dict(r); g=x.get("ui_group") or x.get("subcategory") or _territorial_output_group(x); p=x.get("localization_precision") or _territorial_output_precision(x); rad=10 if p in ("coordinate / puntuale","comunale") else 25
        x["ui_group"]=g; x["ui_group_label"]=x.get("ui_group_label") or labels.get(g,g); x["subcategory"]=x.get("subcategory") or g; x["localization_precision"]=p; x["display_radius_km"]=rad; x["radius_km"]=rad
        out.append(x)
    return out
# --- end v230 territorial output normalization ---


# --- v231 territorial output normalization: municipal vectors/parasites = 10 km, provincial/regional = 25 km ---
def _territorial_output_has_municipality(row):
    return any(str(row.get(k,"") or "").strip() for k in ["municipality","comune","city","locality","location"])
def _territorial_output_group(row):
    explicit=str(row.get("ui_group") or row.get("subcategory") or "").strip()
    if explicit in {"sand_flies","ticks","mosquitoes_other_vectors","parasites","west_nile"}: return explicit
    t=" ".join(str(row.get(k,"") or "") for k in ["category","label","scientific_name","data_type","source","display_source","notes","note"]).lower()
    cat=str(row.get("category","") or "").lower()
    if cat=="west_nile" or "west nile" in t or "usutu" in t: return "west_nile"
    if cat in ("parasites","parasite") or any(x in t for x in ["giardia","toxocara","ancylostoma","dirofilaria","echinococcus","parasite","parassit"]): return "parasites"
    if any(x in t for x in ["phlebotomus","phlebotominae","phlebotomine","sand fly","sandfly","flebotom","leish"]): return "sand_flies"
    if any(x in t for x in ["ixodes","dermacentor","hyalomma","rhipicephalus","ornithodoros","amblyomma","tick","zecc"]): return "ticks"
    return "mosquitoes_other_vectors" if cat in ("vectors","vector") else cat or "mosquitoes_other_vectors"
def _territorial_output_precision(row, group=None):
    group = group or _territorial_output_group(row)
    explicit=" ".join(str(row.get(k,"") or "").lower() for k in ["localization_precision","aggregation_level","precision","area_level","data_type"])
    if any(x in explicit for x in ["occurrence_point","real precise","point occurrence","coordinate / puntuale"]): return "coordinate / puntuale"
    if group in ("sand_flies","ticks","mosquitoes_other_vectors","parasites") and _territorial_output_has_municipality(row): return "comunale"
    if "region" in explicit: return "regionale"
    if "prov" in explicit: return "provinciale"
    if "comun" in explicit or "municip" in explicit: return "comunale"
    if _territorial_output_has_municipality(row): return "comunale"
    if str(row.get("province","") or "").strip(): return "provinciale"
    if str(row.get("region","") or "").strip(): return "regionale"
    return "coordinate / puntuale" if row.get("lat") not in (None,"") and row.get("lon") not in (None,"") else "territoriale"
def _territorial_output_count(row):
    raw=row.get("count") or row.get("case_count") or row.get("value") or 1
    try:
        n=int(float(str(raw).replace(",",".")))
        return max(n,1)
    except Exception: return 1
def _decorate_territorial_output(rows):
    labels={"sand_flies":"Flebotomi","ticks":"Zecche","mosquitoes_other_vectors":"Zanzare / altri vettori","parasites":"Parassiti","west_nile":"West Nile"}
    out=[]
    for r in rows or []:
        x=dict(r); g=_territorial_output_group(x); p=_territorial_output_precision(x,g); rad=10 if p in ("coordinate / puntuale","comunale") else 25; n=_territorial_output_count(x)
        x["ui_group"]=g; x["ui_group_label"]=x.get("ui_group_label") or labels.get(g,g); x["subcategory"]=x.get("subcategory") or g
        x["localization_precision"]=p; x["display_radius_km"]=rad; x["radius_km"]=rad; x["count"]=n; x["case_count"]=n
        out.append(x)
    return out
# --- end v231 territorial output normalization ---


# --- v232 forced territorial output fields ---
def _v232_has_location(row):
    return any(str(row.get(k,"") or "").strip() for k in ["municipality","comune","city","locality","location"])
def _v232_group(row):
    labels={"sand_flies","ticks","mosquitoes_other_vectors","parasites","west_nile"}
    explicit=str(row.get("ui_group") or row.get("subcategory") or "").strip()
    if explicit in labels: return explicit
    t=" ".join(str(row.get(k,"") or "") for k in ["category","label","scientific_name","data_type","source","display_source","notes","note"]).lower()
    cat=str(row.get("category","") or "").lower()
    if cat=="west_nile" or "west nile" in t or "wnv" in t or "usutu" in t: return "west_nile"
    if cat in ("parasites","parasite") or any(x in t for x in ["giardia","toxocara","ancylostoma","dirofilaria","echinococcus","parasite","parassit"]): return "parasites"
    if any(x in t for x in ["phlebotomus","phlebotominae","phlebotomine","sand fly","sandfly","flebotom","leish"]): return "sand_flies"
    if any(x in t for x in ["ixodes","dermacentor","hyalomma","rhipicephalus","ornithodoros","amblyomma","tick","zecc"]): return "ticks"
    if cat in ("vectors","vector"): return "mosquitoes_other_vectors"
    return cat or "mosquitoes_other_vectors"
def _v232_precision(row, g=None):
    g = g or _v232_group(row)
    expl=" ".join(str(row.get(k,"") or "").lower() for k in ["localization_precision","aggregation_level","precision","area_level","data_type","count_label"])
    if any(x in expl for x in ["occurrence_point","real precise","point occurrence","coordinate / puntuale"]): return "coordinate / puntuale"
    if g == "west_nile":
        if "region" in expl or (str(row.get("region","") or "").strip() and not str(row.get("province","") or "").strip()): return "regionale"
        return "provinciale"
    if g in ("sand_flies","ticks","mosquitoes_other_vectors","parasites") and _v232_has_location(row): return "comunale"
    if "region" in expl: return "regionale"
    if "prov" in expl: return "provinciale"
    if "comun" in expl or "municip" in expl: return "comunale"
    if _v232_has_location(row): return "comunale"
    if str(row.get("province","") or "").strip(): return "provinciale"
    if str(row.get("region","") or "").strip(): return "regionale"
    return "territoriale"
def _v232_count(row):
    raw=row.get("count") or row.get("case_count") or row.get("value") or 1
    try: return max(1,int(float(str(raw).replace(",","."))))
    except Exception: return 1
def _v232_decorate_layers(rows):
    labels={"sand_flies":"Flebotomi","ticks":"Zecche","mosquitoes_other_vectors":"Zanzare / altri vettori","parasites":"Parassiti","west_nile":"West Nile"}
    out=[]
    for r in rows or []:
        x=dict(r); g=_v232_group(x); p=_v232_precision(x,g); rad=10 if p in ("coordinate / puntuale","comunale") else 25; n=_v232_count(x)
        x["ui_group"]=g; x["ui_group_label"]=labels.get(g,g); x["subcategory"]=g
        x["localization_precision"]=p; x["display_radius_km"]=rad; x["radius_km"]=rad; x["count"]=n; x["case_count"]=n
        out.append(x)
    return out
# --- end v232 forced territorial output fields ---


@app.post("/sync/territorial-layers/piemonte-liguria/run")
def run_piem_liguria_vector_import(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    try:
        p=subprocess.run([sys.executable,"scripts/import_gbif_piem_liguria_vectors_v234.py"],capture_output=True,text=True,timeout=int(os.getenv("REGION_IMPORT_TIMEOUT_SECONDS","2400")))
        if p.returncode!=0:
            log_sync("GBIF_PIEMONTE_LIGURIA_VECTORS","error",(p.stderr or p.stdout)[-1000:],0,0,0,started)
            raise HTTPException(status_code=500, detail=(p.stderr or p.stdout)[-4000:])
        try: result=json.loads(p.stdout)
        except Exception: result={"stdout":p.stdout[-4000:]}
        log_sync("GBIF_PIEMONTE_LIGURIA_VECTORS","success","Piemonte/Liguria vector occurrences imported",int(result.get("candidate_rows",0) or 0),int(result.get("inserted",0) or 0),int(result.get("updated",0) or 0),started)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_sync("GBIF_PIEMONTE_LIGURIA_VECTORS","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/territorial-layers/status")
def get_territorial_layers_public_status():
    status_path="data/territorial_layers/refresh_status.json"
    status=load_json(status_path) if os.path.exists(status_path) else {}
    csv_status=territorial_layers_csv_status(TERRITORIAL_LAYERS_CSV_PATH)
    return {"status":"ok","csv":csv_status,"refresh":status}

@app.get("/territorial-layers")
def get_territorial_layers(lat:float|None=Query(None),lon:float|None=Query(None),radius_km:float=Query(100,ge=1,le=2000),category:str=Query("all"),days:int=Query(365,ge=1,le=3650),source:str|None=Query(None),species:str=Query("all"),focus:str=Query("all"),leishmaniasis:bool=Query(False),include_vector_occurrences:bool=Query(True)):
    layers=load_territorial_layers(TERRITORIAL_LAYERS_CSV_PATH)
    out=filter_territorial_layers(layers, lat=lat, lon=lon, radius_km=radius_km, category=category, days=days, source=source, distance_fn=haversine_km, parse_date_fn=parse_date)
    out=[layer for layer in out if _layer_matches_vector_filters(layer, species=species, focus=focus, leishmaniasis=leishmaniasis)]
    vector_count = 0
    if include_vector_occurrences and str(category or "all").lower() in ("all", "vectors"):
        vector_layers = vector_occurrence_layers_for_area(lat=lat, lon=lon, radius_km=radius_km, species=species, focus=focus, leishmaniasis=leishmaniasis, source=source)
        out.extend(vector_layers)
        vector_count = len(vector_layers)
    out=_v232_decorate_layers(out)
    return {"count":len(out),"layers":out,"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days,"species":species,"focus":focus,"leishmaniasis":leishmaniasis,"vector_occurrence_layers":vector_count,"include_vector_occurrences":include_vector_occurrences}

@app.get("/territorial-layers/vector-occurrences/status")
def get_territorial_vector_occurrence_layer_status():
    init_vector_surveillance_db()
    with connect() as conn:
        total=conn.execute("SELECT COUNT(*) AS c FROM vector_occurrences").fetchone()["c"]
        leish=conn.execute("SELECT COUNT(*) AS c FROM vector_occurrences WHERE LOWER(COALESCE(scientific_name,'') || ' ' || COALESCE(pathogen_focus,'')) LIKE '%leish%' OR LOWER(COALESCE(scientific_name,'')) LIKE 'phlebotomus%'").fetchone()["c"]
        by_species=[dict(r) for r in conn.execute("SELECT scientific_name, COUNT(*) AS count FROM vector_occurrences GROUP BY scientific_name ORDER BY count DESC").fetchall()]
    return {"status":"ok","total_occurrences":total,"leishmaniasis_relevant_occurrences":leish,"by_species":by_species}


@app.get("/territorial-layers/ui-groups/status")
def get_territorial_layers_ui_groups_status(lat:float|None=Query(None), lon:float|None=Query(None), radius_km:float=Query(100,ge=1,le=2000), category:str=Query("all"), days:int=Query(365,ge=1,le=3650), source:str|None=Query(None)):
    layers = load_territorial_layers(TERRITORIAL_LAYERS_CSV_PATH)
    out = filter_territorial_layers(layers, lat=lat, lon=lon, radius_km=radius_km, category=category, days=days, source=source, distance_fn=haversine_km, parse_date_fn=parse_date)
    out = apply_ui_groups(out)
    return {"status":"ok", "count":len(out), "ui_group_counts":ui_group_counts(out), "sample":out[:10]}

@app.get("/territorial-layers/export")
def export_territorial_layers(category:str=Query("all"),format:str=Query("csv")):
    layers=filter_territorial_layers(load_territorial_layers(TERRITORIAL_LAYERS_CSV_PATH), category=category, distance_fn=haversine_km, parse_date_fn=parse_date)
    if format.lower()=="json":
        layers=apply_ui_groups(layers)
        return {"count":len(layers),"layers":layers,"ui_group_counts":ui_group_counts(layers)}
    fields=["id","external_id","category","source","display_source","label","scientific_name","data_type","count","period_start","period_end","country","region","province","location","lat","lon","radius_km","color","url_source","notes","ui_group","ui_group_label","subcategory","localization_precision","display_radius_km"]
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



def _safe_read_json_file(path: str, default: Any = None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

@app.get("/data-sources/status")
def get_data_sources_status():
    """Return a unified status snapshot for vet.ector data sources.

    The JSON is generated by scripts/build_data_sources_status.py during GitHub Actions.
    If the file is not present, the endpoint returns a lightweight live fallback.
    """
    status_path = os.getenv("DATA_SOURCES_STATUS_PATH", "data/status/data_sources_status.json")
    status = _safe_read_json_file(status_path, default=None)
    if isinstance(status, dict):
        status["status_file"] = status_path
        return status

    fallback = {
        "generated_at": now_iso(),
        "status": "fallback",
        "message": "data/status/data_sources_status.json not found; returning live fallback counts.",
        "official_events": {},
        "territorial_layers": territorial_layers_csv_status(TERRITORIAL_LAYERS_CSV_PATH),
        "backend": {
            "version": app.version,
            "sync_interval_hours": SYNC_INTERVAL_HOURS,
            "scheduler_enabled": ENABLE_SCHEDULER,
        },
    }
    try:
        with connect() as conn:
            fallback["official_events"]["database_official_events"] = conn.execute("SELECT COUNT(*) AS c FROM official_events").fetchone()["c"]
            fallback["official_events"]["database_user_events"] = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
    except Exception as e:
        fallback["database_error"] = str(e)
    return fallback

@app.get("/data-sources/status/export")
def export_data_sources_status(format: str = Query("json")):
    status_path = os.getenv("DATA_SOURCES_STATUS_PATH", "data/status/data_sources_status.json")
    csv_path = os.getenv("DATA_SOURCES_STATUS_CSV_PATH", "data/status/data_sources_status.csv")
    if format.lower() == "csv":
        if not os.path.exists(csv_path):
            raise HTTPException(status_code=404, detail="data_sources_status.csv not found")
        with open(csv_path, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content=content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition":"attachment; filename=data_sources_status.csv"})
    status = _safe_read_json_file(status_path, default=None)
    if not isinstance(status, dict):
        raise HTTPException(status_code=404, detail="data_sources_status.json not found")
    return status

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



@app.post("/sync/vectornet-gbif-occurrences/run")
def run_vectornet_gbif_occurrence_sync(x_sync_token:str|None=Header(default=None), limit_per_species:int=Query(200,ge=1,le=2000), max_pages:int=Query(2,ge=1,le=20)):
    require_sync_token(x_sync_token)
    try:
        return sync_vectornet_gbif_occurrences(limit_per_species=limit_per_species, max_pages=max_pages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sync/vectornet-gbif-occurrences/status")
def get_vectornet_gbif_occurrence_status():
    init_vector_surveillance_db()
    with connect() as conn:
        row=conn.execute("SELECT * FROM sync_log WHERE source='VECTORNET_GBIF_OCCURRENCES' ORDER BY id DESC LIMIT 1").fetchone()
        total=conn.execute("SELECT COUNT(*) AS c FROM vector_occurrences").fetchone()["c"]
        by_species=[dict(r) for r in conn.execute("SELECT scientific_name, COUNT(*) AS count FROM vector_occurrences GROUP BY scientific_name ORDER BY count DESC").fetchall()]
    return {"status":"never_run" if row is None else "ok", "last_sync": None if row is None else dict(row), "total_occurrences": total, "by_species": by_species}

@app.get("/vector-species")
def get_vector_species(leishmaniasis:bool=Query(False), group:str=Query("all"), focus:str=Query("all"), limit:int=Query(200,ge=1,le=1000)):
    init_vector_surveillance_db()
    seed_leishmaniasis_vector_species()
    group_l=str(group or "all").lower().strip()
    focus_l=str(focus or "all").lower().strip()
    where=[]; params=[]
    if leishmaniasis:
        where.append("is_leishmaniasis_vector=1")
    if group_l and group_l!="all":
        where.append("LOWER(common_group)=?"); params.append(group_l)
    if focus_l and focus_l!="all":
        where.append("LOWER(COALESCE(pathogen_focus,'')) LIKE ?"); params.append(f"%{focus_l}%")
    sql="SELECT * FROM vector_species_catalog"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY priority ASC, scientific_name ASC LIMIT ?"; params.append(limit)
    with connect() as conn:
        rows=[dict(r) for r in conn.execute(sql, params).fetchall()]
    for r in rows:
        r["is_leishmaniasis_vector"] = bool(r.get("is_leishmaniasis_vector"))
    return {"query":{"leishmaniasis":leishmaniasis,"group":group,"focus":focus,"limit":limit},"count":len(rows),"species":rows}

@app.get("/vector-occurrences")
def get_vector_occurrences(lat:float|None=Query(None), lon:float|None=Query(None), radius_km:float=Query(100,ge=1,le=2000), species:str=Query("all"), group:str=Query("all"), focus:str=Query("all"), leishmaniasis:bool=Query(False), limit:int=Query(1000,ge=1,le=5000)):
    init_vector_surveillance_db()
    species_l=str(species or "all").lower().strip()
    group_l=str(group or "all").lower().strip()
    focus_l=str(focus or "all").lower().strip()
    with connect() as conn:
        rows=[dict(r) for r in conn.execute("SELECT * FROM vector_occurrences ORDER BY COALESCE(event_date,'' ) DESC, COALESCE(year,0) DESC").fetchall()]
    out=[]
    for row in rows:
        if species_l and species_l!="all" and species_l not in str(row.get("scientific_name","")).lower(): continue
        if group_l and group_l!="all" and group_l != str(row.get("common_group","")).lower(): continue
        hay=f"{row.get('scientific_name','')} {row.get('pathogen_focus','')} {row.get('common_group','')}".lower()
        if focus_l and focus_l!="all" and focus_l not in hay: continue
        if leishmaniasis and "leish" not in hay and "phlebotomus" not in hay: continue
        distance=None
        if lat is not None and lon is not None:
            if row.get("lat") is None or row.get("lon") is None: continue
            distance=haversine_km(lat, lon, float(row["lat"]), float(row["lon"]))
            if distance > radius_km: continue
        out.append(_vector_occurrence_to_public(row, distance))
        if len(out) >= limit: break
    return {"query":{"lat":lat,"lon":lon,"radius_km":radius_km,"species":species,"group":group,"focus":focus,"leishmaniasis":leishmaniasis,"limit":limit},"count":len(out),"occurrences":out}

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
