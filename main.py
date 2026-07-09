from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sync.official_connector import OfficialDemoConnector
from sync.wahis_csv_connector import WahisCsvConnector
from sync.normalizer import normalize_official_event

DB_PATH = os.getenv("DB_PATH", "vet_alert.db")
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"
SYNC_INTERVAL_HOURS = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))
WAHIS_SYNC_TOKEN = os.getenv("WAHIS_SYNC_TOKEN", "")
EARTH_RADIUS_KM = 6371.0

app = FastAPI(title="vet.ector Veterinary Alert API", version="1.3.0-wahis-autosync-24h")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = BackgroundScheduler()


class UserReport(BaseModel):
    disease: str
    diagnosis_status: str = "Sospetto"
    species: str = "Animale"
    animal_group: str = "unknown"
    observation_date: str | None = None
    lat: float
    lon: float
    location: str = ""
    region: str = ""
    country: str = "Italy"
    source: str = "user_report"
    report_type: str = "user_suspect"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE,
                disease TEXT NOT NULL,
                diagnosis_status TEXT,
                species TEXT,
                animal_group TEXT,
                observation_date TEXT,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                location TEXT,
                region TEXT,
                country TEXT DEFAULT 'Italy',
                source TEXT,
                source_type TEXT DEFAULT 'user',
                report_type TEXT DEFAULT 'user_suspect',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS official_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL,
                source_type TEXT DEFAULT 'official',
                report_type TEXT DEFAULT 'official_confirmed',
                disease TEXT NOT NULL,
                disease_it TEXT,
                diagnosis_status TEXT DEFAULT 'Confermato',
                species TEXT,
                animal_group TEXT,
                observation_date TEXT,
                report_date TEXT,
                country TEXT DEFAULT 'Italy',
                region TEXT,
                location TEXT,
                lat REAL,
                lon REAL,
                url_source TEXT,
                notes TEXT,
                raw_payload TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS veterinarians (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE,
                name TEXT NOT NULL,
                type TEXT,
                availability TEXT,
                phone TEXT,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                city TEXT,
                region TEXT,
                services TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                records_received INTEGER DEFAULT 0,
                records_inserted INTEGER DEFAULT 0,
                records_updated INTEGER DEFAULT 0,
                started_at TEXT,
                finished_at TEXT
            )
        """)
        conn.commit()


def load_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def log_sync(source: str, status: str, message: str, received: int, inserted: int, updated: int, started_at: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sync_log (source, status, message, records_received, records_inserted,
            records_updated, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source, status, message, received, inserted, updated, started_at, now_iso()),
        )
        conn.commit()


def upsert_event(row: Dict[str, Any]) -> str:
    external_id = row.get("external_id") or f"EVENT-{datetime.now(timezone.utc).timestamp()}"
    with connect() as conn:
        existing = conn.execute("SELECT id FROM events WHERE external_id = ?", (external_id,)).fetchone()
        conn.execute(
            """
            INSERT INTO events (external_id,disease,diagnosis_status,species,animal_group,observation_date,lat,lon,location,region,country,source,source_type,report_type,updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(external_id) DO UPDATE SET disease=excluded.disease, diagnosis_status=excluded.diagnosis_status,
            species=excluded.species, animal_group=excluded.animal_group, observation_date=excluded.observation_date,
            lat=excluded.lat, lon=excluded.lon, location=excluded.location, region=excluded.region, country=excluded.country,
            source=excluded.source, source_type=excluded.source_type, report_type=excluded.report_type, updated_at=CURRENT_TIMESTAMP
            """,
            (
                external_id, row.get("disease"), row.get("diagnosis_status", "Sospetto"), row.get("species", ""),
                row.get("animal_group", "unknown"), row.get("observation_date", ""), float(row.get("lat")),
                float(row.get("lon")), row.get("location", ""), row.get("region", ""), row.get("country", "Italy"),
                row.get("source", "user_report"), row.get("source_type", "user"), row.get("report_type", "user_suspect"),
            ),
        )
        conn.commit()
    return "updated" if existing else "inserted"


def upsert_veterinarian(row: Dict[str, Any]) -> str:
    external_id = row.get("external_id") or row.get("id") or row.get("name")
    with connect() as conn:
        existing = conn.execute("SELECT id FROM veterinarians WHERE external_id = ?", (external_id,)).fetchone()
        conn.execute(
            """
            INSERT INTO veterinarians (external_id,name,type,availability,phone,lat,lon,city,region,services,updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(external_id) DO UPDATE SET name=excluded.name,type=excluded.type,availability=excluded.availability,
            phone=excluded.phone,lat=excluded.lat,lon=excluded.lon,city=excluded.city,region=excluded.region,services=excluded.services,updated_at=CURRENT_TIMESTAMP
            """,
            (
                external_id, row.get("name"), row.get("type", "Veterinario"), row.get("availability", ""),
                row.get("phone", ""), float(row.get("lat")), float(row.get("lon")), row.get("city", ""),
                row.get("region", ""), json.dumps(row.get("services", []), ensure_ascii=False),
            ),
        )
        conn.commit()
    return "updated" if existing else "inserted"


def upsert_official_event(row: Dict[str, Any]) -> str:
    if not row.get("external_id"):
        row["external_id"] = f"{row.get('source','OFFICIAL')}-{row.get('disease','disease')}-{row.get('observation_date','date')}-{row.get('location','location')}"
    if row.get("lat") is None or row.get("lon") is None:
        raise ValueError(f"Official event {row.get('external_id')} missing lat/lon")
    with connect() as conn:
        existing = conn.execute("SELECT id FROM official_events WHERE external_id = ?", (row["external_id"],)).fetchone()
        conn.execute(
            """
            INSERT INTO official_events (external_id,source,source_type,report_type,disease,disease_it,diagnosis_status,species,animal_group,observation_date,report_date,country,region,location,lat,lon,url_source,notes,raw_payload,updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(external_id) DO UPDATE SET source=excluded.source, source_type=excluded.source_type, report_type=excluded.report_type,
            disease=excluded.disease, disease_it=excluded.disease_it, diagnosis_status=excluded.diagnosis_status, species=excluded.species,
            animal_group=excluded.animal_group, observation_date=excluded.observation_date, report_date=excluded.report_date, country=excluded.country,
            region=excluded.region, location=excluded.location, lat=excluded.lat, lon=excluded.lon, url_source=excluded.url_source,
            notes=excluded.notes, raw_payload=excluded.raw_payload, updated_at=CURRENT_TIMESTAMP
            """,
            (
                row["external_id"], row.get("source", "OFFICIAL_UNKNOWN"), row.get("source_type", "official"),
                row.get("report_type", "official_confirmed"), row.get("disease", ""), row.get("disease_it", ""),
                row.get("diagnosis_status", "Confermato"), row.get("species", ""), row.get("animal_group", "unknown"),
                row.get("observation_date", ""), row.get("report_date", ""), row.get("country", "Italy"),
                row.get("region", ""), row.get("location", ""), float(row.get("lat")), float(row.get("lon")),
                row.get("url_source", ""), row.get("notes", ""), json.dumps(row.get("raw_payload", {}), ensure_ascii=False),
            ),
        )
        conn.commit()
    return "updated" if existing else "inserted"


def sync_seed_data() -> Dict[str, Any]:
    started_at = now_iso(); inserted = updated = 0
    try:
        for row in load_json("data/source_events.json"):
            r = upsert_event(row); inserted += r == "inserted"; updated += r == "updated"
        for row in load_json("data/source_veterinarians.json"):
            upsert_veterinarian(row)
        log_sync("seed_data", "success", "Seed data sync completed", inserted + updated, inserted, updated, started_at)
        return {"status": "success", "inserted": inserted, "updated": updated}
    except Exception as exc:
        log_sync("seed_data", "error", str(exc), 0, inserted, updated, started_at); raise


def _sync_rows(source_name: str, raw_rows: List[Dict[str, Any]], default_source: str) -> Dict[str, Any]:
    started_at = now_iso(); inserted = updated = skipped = 0
    for raw in raw_rows:
        normalized = normalize_official_event(raw, default_source=default_source)
        try:
            r = upsert_official_event(normalized); inserted += r == "inserted"; updated += r == "updated"
        except Exception as row_exc:
            skipped += 1
            print(f"Skipped official event: {row_exc}")
    log_sync(source_name, "success", f"{source_name} sync completed; skipped={skipped}", len(raw_rows), inserted, updated, started_at)
    return {"status": "success", "source": source_name, "received": len(raw_rows), "inserted": inserted, "updated": updated, "skipped": skipped}


def sync_official_events() -> Dict[str, Any]:
    connector = OfficialDemoConnector()
    return _sync_rows(connector.source_name, connector.fetch(), "OFFICIAL_DEMO")


def sync_wahis_events() -> Dict[str, Any]:
    connector = WahisCsvConnector()
    return _sync_rows(connector.source_name, connector.fetch(), "WAHIS_CSV")


def sync_wahis_csv_text(csv_text: str, source_name: str = "WAHIS_CSV_UPLOAD") -> Dict[str, Any]:
    rows = WahisCsvConnector.parse_csv_text(csv_text)
    return _sync_rows(source_name, rows, "WAHIS")


def require_sync_token(token_header: str | None) -> None:
    if not WAHIS_SYNC_TOKEN:
        return
    if token_header != WAHIS_SYNC_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing sync token")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
    rlat1 = math.radians(lat1); rlat2 = math.radians(lat2)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def parse_date(value: str | None):
    if not value: return None
    try: return datetime.fromisoformat(str(value)[:10]).date()
    except Exception: return None


def matches_animal_filter(row: Dict[str, Any], animal_filter: str) -> bool:
    if animal_filter in ("", "all", None): return True
    text = f"{row.get('species','')} {row.get('animal_group','')} {row.get('disease','')} {row.get('disease_it','')}".lower()
    filters = {
        "companion": ["dog", "cat", "cane", "gatto", "companion"],
        "dogs": ["dog", "cane"],
        "cats": ["cat", "gatto"],
        "farm": ["bovine", "bovino", "swine", "suino", "poultry", "avicoli", "ovine", "ovino"],
        "bovine": ["bovine", "bovino", "cattle"],
        "swine": ["swine", "suino", "cinghiale", "pig"],
        "poultry": ["poultry", "avicoli", "volatile", "avian"],
        "equine": ["equine", "equini", "horse", "cavallo"],
    }
    return any(term in text for term in filters.get(animal_filter, []))


def compute_risk_score(status: str, distance_km: float, observation_date: str | None) -> float:
    s = (status or "").lower()
    status_score = 1.0 if "conferm" in s or "confirm" in s else 0.65 if "sosp" in s or "suspect" in s else 0.4
    obs = parse_date(observation_date)
    days_old = max(0, (datetime.now(timezone.utc).date() - obs).days) if obs else 15
    distance_score = max(0.0, 1.0 - min(distance_km, 100.0) / 100.0)
    recency_score = max(0.0, 1.0 - min(days_old, 30.0) / 30.0)
    return round((0.45 * status_score + 0.30 * distance_score + 0.25 * recency_score) * 100, 1)


def row_to_public_event(row: Dict[str, Any], distance_km: float) -> Dict[str, Any]:
    disease_it = row.get("disease_it") or row.get("disease")
    status = row.get("diagnosis_status") or "Confermato"
    return {
        "id": row.get("external_id") or row.get("id"),
        "external_id": row.get("external_id"),
        "disease": disease_it,
        "disease_original": row.get("disease"),
        "diagnosis_status": status,
        "species": row.get("species"),
        "animal_group": row.get("animal_group"),
        "observation_date": row.get("observation_date"),
        "report_date": row.get("report_date") or row.get("observation_date"),
        "lat": row.get("lat"),
        "lon": row.get("lon"),
        "location": row.get("location"),
        "region": row.get("region"),
        "country": row.get("country"),
        "source": row.get("source"),
        "source_type": row.get("source_type"),
        "report_type": row.get("report_type"),
        "url_source": row.get("url_source", ""),
        "distance_km": round(distance_km, 2),
        "risk_score": compute_risk_score(status, distance_km, row.get("observation_date")),
    }


@app.on_event("startup")
def startup() -> None:
    init_db(); sync_seed_data(); sync_official_events(); sync_wahis_events()
    if ENABLE_SCHEDULER and not scheduler.running:
        scheduler.add_job(sync_official_events, "interval", hours=SYNC_INTERVAL_HOURS, id="official_sync", replace_existing=True)
        scheduler.add_job(sync_wahis_events, "interval", hours=SYNC_INTERVAL_HOURS, id="wahis_csv_sync", replace_existing=True)
        scheduler.start()


@app.on_event("shutdown")
def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "time": now_iso(), "version": app.version, "sync_interval_hours": SYNC_INTERVAL_HOURS}


@app.get("/cities")
def get_cities() -> Dict[str, Any]:
    return {"cities": load_json("data/source_cities.json")}


@app.get("/sync/log")
def get_sync_log(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return {"logs": [dict(r) for r in rows]}


@app.post("/sync/run")
def run_seed_sync() -> Dict[str, Any]: return sync_seed_data()


@app.post("/sync/official/run")
def run_official_sync() -> Dict[str, Any]: return sync_official_events()


@app.post("/sync/wahis/run")
def run_wahis_sync() -> Dict[str, Any]: return sync_wahis_events()


@app.post("/sync/wahis/upload")
async def upload_wahis_csv(request: Request, x_sync_token: str | None = Header(default=None)) -> Dict[str, Any]:
    require_sync_token(x_sync_token)
    body = await request.body()
    csv_text = body.decode("utf-8-sig")
    return sync_wahis_csv_text(csv_text, source_name="WAHIS_CSV_UPLOAD")


@app.get("/sync/wahis/status")
def get_wahis_status() -> Dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM sync_log WHERE source LIKE 'WAHIS%' ORDER BY id DESC LIMIT 1").fetchone()
    return {"status": "never_run" if row is None else "ok", "last_sync": None if row is None else dict(row)}


@app.get("/official-events")
def get_official_events(lat: float | None = Query(None), lon: float | None = Query(None), radius_km: float = Query(200, ge=1, le=2000), days: int = Query(365, ge=1, le=3650), animal_filter: str = Query("all"), source: str | None = Query(None)) -> Dict[str, Any]:
    with connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM official_events ORDER BY observation_date DESC").fetchall()]
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    out = []
    for row in rows:
        if source and row.get("source") != source: continue
        obs = parse_date(row.get("observation_date"))
        if obs and obs < cutoff: continue
        if not matches_animal_filter(row, animal_filter): continue
        distance = 0.0
        if lat is not None and lon is not None and row.get("lat") is not None and row.get("lon") is not None:
            distance = haversine_km(lat, lon, float(row["lat"]), float(row["lon"]))
            if distance > radius_km: continue
        out.append(row_to_public_event(row, distance))
    return {"count": len(out), "events": out}


@app.get("/events")
def get_events(lat: float = Query(...), lon: float = Query(...), radius_km: float = Query(50, ge=1, le=2000), days: int = Query(180, ge=1, le=3650), animal_filter: str = Query("all"), disease: str | None = Query(None), include_official: bool = Query(True), include_user: bool = Query(True)) -> Dict[str, Any]:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    disease_filter = disease.lower().strip() if disease else ""
    rows: List[Dict[str, Any]] = []
    with connect() as conn:
        if include_user: rows.extend([dict(r) for r in conn.execute("SELECT * FROM events").fetchall()])
        if include_official: rows.extend([dict(r) for r in conn.execute("SELECT * FROM official_events").fetchall()])
    out = []
    for row in rows:
        if row.get("lat") is None or row.get("lon") is None: continue
        obs = parse_date(row.get("observation_date"))
        if obs and obs < cutoff: continue
        if disease_filter:
            searchable = f"{row.get('disease','')} {row.get('disease_it','')} {row.get('species','')} {row.get('location','')}".lower()
            if disease_filter not in searchable: continue
        if not matches_animal_filter(row, animal_filter): continue
        distance = haversine_km(lat, lon, float(row["lat"]), float(row["lon"]))
        if distance > radius_km: continue
        out.append(row_to_public_event(row, distance))
    out.sort(key=lambda x: (-x.get("risk_score", 0), x.get("distance_km", 9999)))
    return {"count": len(out), "events": out}


@app.get("/veterinarians")
def get_veterinarians(lat: float = Query(...), lon: float = Query(...), radius_km: float = Query(50, ge=1, le=2000), animal_filter: str = Query("all")) -> Dict[str, Any]:
    with connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM veterinarians ORDER BY name ASC").fetchall()]
    out = []
    for row in rows:
        distance = haversine_km(lat, lon, float(row["lat"]), float(row["lon"]))
        if distance > radius_km: continue
        try: row["services"] = json.loads(row.get("services") or "[]")
        except Exception: row["services"] = []
        row["distance_km"] = round(distance, 2)
        out.append(row)
    out.sort(key=lambda x: x["distance_km"])
    return {"count": len(out), "veterinarians": out}


@app.post("/user-reports/suspect")
def create_user_suspect(report: UserReport) -> Dict[str, Any]:
    payload = report.model_dump(); payload["external_id"] = f"USER-SUSPECT-{int(datetime.now(timezone.utc).timestamp())}"; payload["diagnosis_status"] = "Sospetto"; payload["source_type"] = "user"; payload["report_type"] = "user_suspect"; payload["observation_date"] = payload.get("observation_date") or datetime.now(timezone.utc).date().isoformat(); result = upsert_event(payload); return {"status": result, "event": payload}


@app.post("/user-reports/positive")
def create_user_positive(report: UserReport) -> Dict[str, Any]:
    payload = report.model_dump(); payload["external_id"] = f"USER-POSITIVE-{int(datetime.now(timezone.utc).timestamp())}"; payload["diagnosis_status"] = "Segnalato da utente"; payload["source_type"] = "user"; payload["report_type"] = "user_positive"; payload["observation_date"] = payload.get("observation_date") or datetime.now(timezone.utc).date().isoformat(); result = upsert_event(payload); return {"status": result, "event": payload}
