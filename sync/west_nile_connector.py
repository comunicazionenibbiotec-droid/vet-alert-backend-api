from __future__ import annotations
import csv, io, os, urllib.request
from datetime import datetime
from typing import Any, Dict, List, Tuple

WEST_NILE_SOURCE_KEY = "ISS_IZS_WNV"
WEST_NILE_COLOR = "#F59E0B"
WEST_NILE_DEFAULT_URL = "https://www.epicentro.iss.it/westNile/bollettino"

PROVINCE_CENTERS = {
    "torino": ("Piemonte", "Torino", "Torino", 45.0703, 7.6869),
    "novara": ("Piemonte", "Novara", "Novara", 45.4469, 8.6222),
    "pavia": ("Lombardia", "Pavia", "Pavia", 45.1847, 9.1582),
    "lodi": ("Lombardia", "Lodi", "Lodi", 45.3097, 9.5037),
    "cremona": ("Lombardia", "Cremona", "Cremona", 45.1332, 10.0227),
    "mantova": ("Lombardia", "Mantova", "Mantova", 45.1564, 10.7914),
    "verona": ("Veneto", "Verona", "Verona", 45.4384, 10.9916),
    "venezia": ("Veneto", "Venezia", "Venezia", 45.4408, 12.3155),
    "padova": ("Veneto", "Padova", "Padova", 45.4064, 11.8768),
    "rovigo": ("Veneto", "Rovigo", "Rovigo", 45.0707, 11.7902),
    "modena": ("Emilia-Romagna", "Modena", "Modena", 44.6471, 10.9252),
    "parma": ("Emilia-Romagna", "Parma", "Parma", 44.8015, 10.3279),
    "piacenza": ("Emilia-Romagna", "Piacenza", "Piacenza", 45.0526, 9.6934),
    "reggio emilia": ("Emilia-Romagna", "Reggio Emilia", "Reggio Emilia", 44.6976, 10.6302),
    "ferrara": ("Emilia-Romagna", "Ferrara", "Ferrara", 44.8381, 11.6198),
    "forli-cesena": ("Emilia-Romagna", "Forli-Cesena", "Forli-Cesena", 44.1391, 12.2431),
    "forlì-cesena": ("Emilia-Romagna", "Forli-Cesena", "Forli-Cesena", 44.1391, 12.2431),
    "latina": ("Lazio", "Latina", "Latina", 41.4676, 12.9037),
    "roma": ("Lazio", "Roma", "Roma", 41.9028, 12.4964),
    "lecce": ("Puglia", "Lecce", "Lecce", 40.3515, 18.1750),
    "oristano": ("Sardegna", "Oristano", "Oristano", 39.9062, 8.5884),
}

def _norm(s: Any) -> str:
    return str(s or "").strip().lower()

def _date(s: Any) -> str:
    if not s: return ""
    raw=str(s).strip()
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y"):
        try: return datetime.strptime(raw[:10],fmt).date().isoformat()
        except Exception: pass
    return raw[:10]

def _int(v: Any, default=1) -> int:
    try:
        if v in (None, ""): return default
        return int(float(str(v).replace(",",".")))
    except Exception:
        return default

def _read_text_from_url(url: str) -> str:
    with urllib.request.urlopen(url, timeout=int(os.getenv("WEST_NILE_TIMEOUT_SECONDS","60"))) as r:
        return r.read().decode("utf-8-sig")

def _read_rows(path_or_url: str) -> List[Dict[str,Any]]:
    if str(path_or_url).startswith(("http://","https://")):
        text=_read_text_from_url(path_or_url)
        return list(csv.DictReader(io.StringIO(text)))
    if not os.path.exists(path_or_url): return []
    with open(path_or_url,newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def _read_existing_layers(path: str) -> List[Dict[str,Any]]:
    if not os.path.exists(path): return []
    with open(path,newline="",encoding="utf-8-sig") as f: return list(csv.DictReader(f))

def _write_layers(path: str, rows: List[Dict[str,Any]]):
    fields=["external_id","category","source","label","scientific_name","data_type","count","period_start","period_end","country","region","province","location","lat","lon","radius_km","color","url_source","notes"]
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

def normalize_west_nile_row(row: Dict[str,Any]) -> Dict[str,Any] | None:
    province_raw=row.get("province") or row.get("provincia") or row.get("location") or row.get("area") or ""
    key=_norm(province_raw)
    region=row.get("region") or row.get("regione") or ""
    location=row.get("location") or province_raw
    province=row.get("province") or row.get("provincia") or province_raw
    lat=row.get("lat") or row.get("latitude")
    lon=row.get("lon") or row.get("longitude")
    if (not lat or not lon) and key in PROVINCE_CENTERS:
        reg,prov,loc,clat,clon=PROVINCE_CENTERS[key]
        region=region or reg; province=province or prov; location=location or loc; lat=clat; lon=clon
    try:
        lat=float(lat); lon=float(lon)
    except Exception:
        return None
    evidence=row.get("evidence_type") or row.get("ambito") or row.get("evidence") or row.get("data_type") or "surveillance_evidence"
    virus=row.get("virus") or "West Nile / Usutu surveillance"
    first=_date(row.get("first_positive_date") or row.get("data_prima_positivita") or row.get("period_start") or row.get("date"))
    end=_date(row.get("period_end") or row.get("updated_at") or row.get("date") or first)
    count=_int(row.get("count") or row.get("evidence_count") or row.get("numero") or 1, 1)
    safe=(province or location or "area").upper().replace(" ","-").replace("/","-")
    ext=row.get("external_id") or f"WNV-IT-{safe}-{first or 'NO-DATE'}"
    source_url=row.get("url_source") or row.get("source_url") or WEST_NILE_DEFAULT_URL
    notes=row.get("notes") or "Integrated West Nile / Usutu surveillance context from official/curated bulletins; territorial context only, not an individual clinical diagnosis."
    return {
        "external_id":ext,
        "category":"west_nile",
        "source":WEST_NILE_SOURCE_KEY,
        "label":virus,
        "scientific_name":"West Nile virus / Usutu virus",
        "data_type":evidence,
        "count":count,
        "period_start":first,
        "period_end":end,
        "country":"Italy",
        "region":region,
        "province":province,
        "location":location,
        "lat":lat,
        "lon":lon,
        "radius_km":row.get("radius_km") or 40,
        "color":WEST_NILE_COLOR,
        "url_source":source_url,
        "notes":notes,
    }

def sync_west_nile_layers(territorial_csv_path: str, west_nile_csv_path: str | None=None) -> Dict[str,Any]:
    source_path=os.getenv("WEST_NILE_REMOTE_CSV_URL") or west_nile_csv_path or os.getenv("WEST_NILE_CSV_PATH","data/territorial_layers/west_nile_surveillance.csv")
    rows=_read_rows(source_path)
    layers=[]
    for row in rows:
        n=normalize_west_nile_row(row)
        if n: layers.append(n)
    existing=_read_existing_layers(territorial_csv_path)
    non_wnv=[r for r in existing if str(r.get("source","")).upper()!=WEST_NILE_SOURCE_KEY]
    old_ids={r.get("external_id") for r in existing if str(r.get("source","")).upper()==WEST_NILE_SOURCE_KEY}
    new_ids={r.get("external_id") for r in layers}
    _write_layers(territorial_csv_path, non_wnv+layers)
    return {"status":"success","source":WEST_NILE_SOURCE_KEY,"records_read":len(rows),"rows_inserted":len(new_ids-old_ids),"rows_updated":len(new_ids & old_ids),"rows_total":len(layers),"source_path":source_path,"message":f"West Nile territorial layers rebuilt: {len(layers)} aggregate rows"}

def west_nile_csv_status(path: str) -> Dict[str,Any]:
    rows=_read_rows(os.getenv("WEST_NILE_REMOTE_CSV_URL") or path)
    valid=sum(1 for r in rows if normalize_west_nile_row(r))
    return {"path":os.getenv("WEST_NILE_REMOTE_CSV_URL") or path,"exists": bool(rows),"rows":len(rows),"valid_rows":valid}
