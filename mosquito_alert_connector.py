from __future__ import annotations
import csv, math, os, time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Tuple
try:
    import requests
except Exception:  # pragma: no cover
    requests = None

GBIF_OCCURRENCE_URL = os.getenv("GBIF_OCCURRENCE_URL", "https://api.gbif.org/v1/occurrence/search")
VECTORNET_DATASET_KEYS = [x.strip() for x in os.getenv("VECTORNET_GBIF_DATASET_KEYS", "4abd984b-122c-44a0-8c92-b37e2f5299b1,e497586a-1bdf-4f69-90eb-645d615762c8").split(",") if x.strip()]
VECTORNET_GBIF_LIMIT = int(os.getenv("VECTORNET_GBIF_LIMIT", "300"))
VECTORNET_GBIF_MAX_RECORDS = int(os.getenv("VECTORNET_GBIF_MAX_RECORDS", "4000"))
VECTORNET_DAYS = int(os.getenv("VECTORNET_DAYS", "3650"))
VECTORNET_MIN_COUNT = int(os.getenv("VECTORNET_MIN_COUNT", "1"))
VECTORNET_TIMEOUT_SECONDS = int(os.getenv("VECTORNET_TIMEOUT_SECONDS", "60"))

# Common vector groups/species relevant to veterinary and One Health context.
VECTOR_KEYWORDS = {
    "Ixodes ricinus": ["ixodes ricinus"],
    "Rhipicephalus sanguineus": ["rhipicephalus sanguineus"],
    "Dermacentor reticulatus": ["dermacentor reticulatus"],
    "Phlebotomus perniciosus": ["phlebotomus perniciosus"],
    "Phlebotomus spp.": ["phlebotomus", "phlebotominae"],
    "Culicoides imicola": ["culicoides imicola"],
    "Culicoides spp.": ["culicoides", "ceratopogonidae"],
    "Culex pipiens": ["culex pipiens"],
    "Aedes albopictus": ["aedes albopictus"],
    "Aedes japonicus": ["aedes japonicus"],
    "Aedes koreicus": ["aedes koreicus"],
}
FAMILY_FALLBACK = {
    "ixodidae": "Ticks / Ixodidae",
    "culicidae": "Mosquitoes / Culicidae",
    "psychodidae": "Sand flies / Psychodidae",
    "ceratopogonidae": "Biting midges / Ceratopogonidae",
}

ITALY_CENTERS=[
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

def haversine_km(lat1,lon1,lat2,lon2):
    R=6371.0
    dlat=math.radians(lat2-lat1); dlon=math.radians(lon2-lon1)
    rlat1=math.radians(lat1); rlat2=math.radians(lat2)
    a=math.sin(dlat/2)**2+math.cos(rlat1)*math.cos(rlat2)*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(a))

def nearest_center(lat,lon):
    best=None
    for name,region,province,clat,clon in ITALY_CENTERS:
        d=haversine_km(lat,lon,clat,clon)
        if best is None or d<best[0]: best=(d,name,region,province,clat,clon)
    return best

def parse_date(v):
    if not v: return None
    try: return datetime.fromisoformat(str(v).replace("Z","+00:00")[:10]).date()
    except Exception: pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try: return datetime.strptime(str(v)[:10],fmt).date()
        except Exception: pass
    return None

def vector_label(record: Dict[str,Any]) -> str|None:
    text=" ".join(str(record.get(k) or "") for k in ("scientificName","acceptedScientificName","species","genus","family","order","higherClassification")).lower()
    for label,keys in VECTOR_KEYWORDS.items():
        if any(k in text for k in keys): return label
    fam=str(record.get("family") or "").lower()
    return FAMILY_FALLBACK.get(fam)

def occurrence_date(record: Dict[str,Any]):
    for k in ("eventDate","dateIdentified","modified","lastInterpreted"):
        d=parse_date(record.get(k))
        if d: return d
    y=record.get("year")
    try: return datetime(int(y),1,1).date() if y else None
    except Exception: return None

def occurrence_coords(record: Dict[str,Any]):
    try:
        lat=float(record.get("decimalLatitude")); lon=float(record.get("decimalLongitude"))
        return lat,lon
    except Exception:
        return None

def gbif_fetch_records() -> Iterable[Dict[str,Any]]:
    if requests is None: raise RuntimeError("requests not available")
    total=0
    seen_keys=set()
    for dataset_key in VECTORNET_DATASET_KEYS:
        offset=0
        while total < VECTORNET_GBIF_MAX_RECORDS:
            params={"datasetKey":dataset_key,"country":"IT","hasCoordinate":"true","limit":VECTORNET_GBIF_LIMIT,"offset":offset}
            r=requests.get(GBIF_OCCURRENCE_URL,params=params,timeout=VECTORNET_TIMEOUT_SECONDS)
            r.raise_for_status()
            payload=r.json()
            results=payload.get("results") or []
            if not results: break
            for rec in results:
                key=rec.get("key")
                if key in seen_keys: continue
                seen_keys.add(key); total+=1
                yield rec
                if total >= VECTORNET_GBIF_MAX_RECORDS: break
            if payload.get("endOfRecords") or len(results)<VECTORNET_GBIF_LIMIT: break
            offset += VECTORNET_GBIF_LIMIT
            time.sleep(float(os.getenv("VECTORNET_GBIF_SLEEP_SECONDS","0.1")))

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
    cutoff=datetime.now(timezone.utc).date()-timedelta(days=VECTORNET_DAYS)
    groups={}
    read=0
    for rec in records:
        read+=1
        label=vector_label(rec)
        if not label: continue
        c=occurrence_coords(rec)
        if not c: continue
        lat,lon=c
        d=occurrence_date(rec)
        if d and d<cutoff: continue
        near=nearest_center(lat,lon)
        if not near: continue
        dist,name,region,province,clat,clon=near
        key=(label,name)
        g=groups.setdefault(key,{"count":0,"dates":[],"region":region,"province":province,"location":name,"lat":clat,"lon":clon})
        g["count"]+=1
        if d: g["dates"].append(d)
    rows=[]
    for (label,location),g in groups.items():
        if g["count"] < VECTORNET_MIN_COUNT: continue
        dates=sorted(g["dates"])
        start=dates[0].isoformat() if dates else ""
        end=dates[-1].isoformat() if dates else ""
        safe_label=label.upper().replace(" ","-").replace("/","-")
        ext=f"VECTORNET-GBIF-IT-{location.upper().replace(' ','-')}-{safe_label}"
        rows.append({
            "external_id":ext,
            "category":"vectors",
            "source":"VECTORNET",
            "label":label,
            "scientific_name":label,
            "data_type":"vector_occurrence",
            "count":g["count"],
            "period_start":start,
            "period_end":end,
            "country":"Italy",
            "region":g["region"],
            "province":g["province"],
            "location":g["location"],
            "lat":g["lat"],
            "lon":g["lon"],
            "radius_km":50,
            "color":"#7C3AED",
            "url_source":"https://www.gbif.org/dataset/4abd984b-122c-44a0-8c92-b37e2f5299b1",
            "notes":"Aggregated VectorNet/GBIF occurrence context; presence of vectors does not indicate pathogen circulation or animal disease."
        })
    return rows,read

def sync_vectornet_gbif_layers(csv_path: str) -> Dict[str,Any]:
    layers,read=build_layers(gbif_fetch_records())
    existing=read_existing_csv(csv_path)
    non_vectornet=[r for r in existing if str(r.get("source","")).upper()!="VECTORNET"]
    old_ids={r.get("external_id") for r in existing if str(r.get("source","")).upper()=="VECTORNET"}
    new_ids={r.get("external_id") for r in layers}
    write_csv(csv_path, non_vectornet+layers)
    return {"status":"success","source":"VECTORNET","records_read":read,"rows_inserted":len(new_ids-old_ids),"rows_updated":len(new_ids & old_ids),"rows_total":len(layers),"message":f"VectorNet/GBIF layers rebuilt: {len(layers)} aggregate rows"}
