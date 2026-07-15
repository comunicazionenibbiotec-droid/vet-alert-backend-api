from __future__ import annotations
import csv, io, json, math, os, tempfile, zipfile
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Tuple
try:
    import requests
except Exception:  # pragma: no cover
    requests = None

MOSQUITO_ALERT_DEFAULT_URL = os.getenv("MOSQUITO_ALERT_REPORTS_URL", "https://github.com/MosquitoAlert/Data/raw/master/all_reports.zip")
MOSQUITO_ALERT_DAYS = int(os.getenv("MOSQUITO_ALERT_DAYS", "730"))
MOSQUITO_ALERT_MIN_COUNT = int(os.getenv("MOSQUITO_ALERT_MIN_COUNT", "1"))

TARGET_SPECIES = {
    "aedes albopictus": "Aedes albopictus",
    "albopictus": "Aedes albopictus",
    "aedes aegypti": "Aedes aegypti",
    "aegypti": "Aedes aegypti",
    "aedes japonicus": "Aedes japonicus",
    "japonicus": "Aedes japonicus",
    "aedes koreicus": "Aedes koreicus",
    "koreicus": "Aedes koreicus",
    "culex pipiens": "Culex pipiens",
    "pipiens": "Culex pipiens",
}

ITALY_CENTERS = [
    ("Torino","Piemonte","Torino",45.0703,7.6869),
    ("Milano","Lombardia","Milano",45.4642,9.1900),
    ("Pavia","Lombardia","Pavia",45.1847,9.1582),
    ("Verona","Veneto","Verona",45.4384,10.9916),
    ("Bologna","Emilia-Romagna","Bologna",44.4949,11.3426),
    ("Ferrara","Emilia-Romagna","Ferrara",44.8381,11.6198),
    ("Roma","Lazio","Roma",41.9028,12.4964),
    ("Napoli","Campania","Napoli",40.8518,14.2681),
    ("Cagliari","Sardegna","Cagliari",39.2238,9.1217),
    ("Palermo","Sicilia","Palermo",38.1157,13.3615),
]

def haversine_km(lat1, lon1, lat2, lon2):
    R=6371.0
    dlat=math.radians(lat2-lat1); dlon=math.radians(lon2-lon1)
    rlat1=math.radians(lat1); rlat2=math.radians(lat2)
    a=math.sin(dlat/2)**2+math.cos(rlat1)*math.cos(rlat2)*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(a))

def nearest_center(lat, lon):
    best=None
    for name,region,province,clat,clon in ITALY_CENTERS:
        d=haversine_km(lat,lon,clat,clon)
        if best is None or d<best[0]: best=(d,name,region,province,clat,clon)
    return best

def parse_date(value):
    if not value: return None
    s=str(value)[:10]
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%Y/%m/%d"):
        try: return datetime.strptime(s,fmt).date()
        except Exception: pass
    try: return datetime.fromisoformat(str(value).replace("Z","+00:00")).date()
    except Exception: return None

def lower_text(*values):
    return " ".join(str(v or "") for v in values).lower()

def normalize_species(record):
    text=lower_text(record.get("species"), record.get("taxon"), record.get("taxon_name"), record.get("classification"), record.get("expert_validation_result"), record.get("category"), record.get("type"), record.get("note"))
    for key,name in TARGET_SPECIES.items():
        if key in text: return name
    return None

def recursive_records(obj):
    if isinstance(obj, list):
        for x in obj: yield from recursive_records(x)
    elif isinstance(obj, dict):
        if any(k in obj for k in ("lat","latitude","lon","lng","longitude","geometry")):
            yield obj
        for v in obj.values():
            if isinstance(v,(list,dict)): yield from recursive_records(v)

def coords(record):
    lat=record.get("lat") or record.get("latitude") or record.get("decimalLatitude")
    lon=record.get("lon") or record.get("lng") or record.get("longitude") or record.get("decimalLongitude")
    geom=record.get("geometry")
    if (lat is None or lon is None) and isinstance(geom,dict):
        c=geom.get("coordinates")
        if isinstance(c,(list,tuple)) and len(c)>=2:
            lon,lat=c[0],c[1]
    try: return float(lat), float(lon)
    except Exception: return None

def is_italy(lat, lon, record):
    txt=lower_text(record.get("country"),record.get("countryCode"),record.get("admin0"),record.get("country_name"))
    if "ital" in txt or txt.strip()=="it": return True
    # broad Italy bounding box incl. islands
    return 35.0 <= lat <= 47.5 and 6.0 <= lon <= 19.5

def record_date(record):
    for k in ("date","created_at","observation_date","report_date","eventDate","server_upload_time","creation_time"):
        d=parse_date(record.get(k))
        if d: return d
    return None

def download_zip(url: str) -> bytes:
    if requests is None: raise RuntimeError("requests not available")
    r=requests.get(url,timeout=int(os.getenv("MOSQUITO_ALERT_TIMEOUT_SECONDS","90")))
    r.raise_for_status()
    return r.content

def iter_json_records_from_zip(content: bytes):
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for name in z.namelist():
            l=name.lower()
            if not (l.endswith(".json") or l.endswith(".geojson")): continue
            try:
                data=json.loads(z.read(name).decode("utf-8"))
            except Exception:
                continue
            yield from recursive_records(data)

def read_existing_csv(path: str) -> List[Dict[str,Any]]:
    if not os.path.exists(path): return []
    with open(path,newline="",encoding="utf-8-sig") as f: return list(csv.DictReader(f))

def write_csv(path: str, rows: List[Dict[str,Any]]):
    fields=["external_id","category","source","label","scientific_name","data_type","count","period_start","period_end","country","region","province","location","lat","lon","radius_km","color","url_source","notes"]
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

def build_layers(records: Iterable[Dict[str,Any]]) -> Tuple[List[Dict[str,Any]],int]:
    cutoff=datetime.now(timezone.utc).date()-timedelta(days=MOSQUITO_ALERT_DAYS)
    groups={}
    read=0
    for rec in records:
        read+=1
        species=normalize_species(rec)
        if not species: continue
        c=coords(rec)
        if not c: continue
        lat,lon=c
        if not is_italy(lat,lon,rec): continue
        d=record_date(rec)
        if d and d<cutoff: continue
        near=nearest_center(lat,lon)
        if not near: continue
        dist,name,region,province,clat,clon=near
        key=(species,name)
        g=groups.setdefault(key,{"count":0,"dates":[],"region":region,"province":province,"location":name,"lat":clat,"lon":clon})
        g["count"]+=1
        if d: g["dates"].append(d)
    rows=[]
    for (species,location),g in groups.items():
        if g["count"] < MOSQUITO_ALERT_MIN_COUNT: continue
        dates=sorted(g["dates"])
        start=dates[0].isoformat() if dates else ""
        end=dates[-1].isoformat() if dates else ""
        safe_species=species.upper().replace(" ","-")
        ext=f"MOSQALERT-IT-{location.upper().replace(' ','-')}-{safe_species}"
        rows.append({
            "external_id":ext,
            "category":"vectors",
            "source":"MOSQUITO_ALERT",
            "label":species,
            "scientific_name":species,
            "data_type":"validated_observations",
            "count":g["count"],
            "period_start":start,
            "period_end":end,
            "country":"Italy",
            "region":g["region"],
            "province":g["province"],
            "location":g["location"],
            "lat":g["lat"],
            "lon":g["lon"],
            "radius_km":25,
            "color":"#7C3AED",
            "url_source":"https://github.com/MosquitoAlert/Data",
            "notes":"Aggregated Mosquito Alert observations validated/processed for territorial context; not evidence of disease circulation. Cite Mosquito Alert Community when reusing data."
        })
    return rows,read

def sync_mosquito_alert_layers(csv_path: str) -> Dict[str,Any]:
    url=os.getenv("MOSQUITO_ALERT_REPORTS_URL", MOSQUITO_ALERT_DEFAULT_URL)
    content=download_zip(url)
    records=list(iter_json_records_from_zip(content))
    layers,read=build_layers(records)
    existing=read_existing_csv(csv_path)
    non_mosq=[r for r in existing if str(r.get("source","")).upper()!="MOSQUITO_ALERT"]
    old_ids={r.get("external_id") for r in existing if str(r.get("source","")).upper()=="MOSQUITO_ALERT"}
    new_ids={r.get("external_id") for r in layers}
    write_csv(csv_path, non_mosq+layers)
    return {"status":"success","source":"MOSQUITO_ALERT","records_read":read,"rows_inserted":len(new_ids-old_ids),"rows_updated":len(new_ids & old_ids),"rows_total":len(layers),"message":f"Mosquito Alert layers rebuilt: {len(layers)} aggregate rows"}
