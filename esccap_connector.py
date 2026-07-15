from __future__ import annotations
import csv, os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Callable

DEFAULT_REQUIRED = ["external_id","category","source","label","lat","lon"]
CATEGORY_COLORS = {"vectors":"#7C3AED","parasites":"#059669","west_nile":"#F59E0B"}
DISPLAY_SOURCES = {"MOSQUITO_ALERT":"Mosquito Alert","VECTORNET":"VectorNet / GBIF","ESCCAP":"ESCCAP","ISS_IZS_WNV":"ISS / IZS / CESME"}


def _float(value, default=None):
    try:
        if value in (None, ""): return default
        return float(value)
    except Exception:
        return default


def _int(value, default=0):
    try:
        if value in (None, ""): return default
        return int(float(value))
    except Exception:
        return default


def _date(value):
    if not value: return None
    try: return datetime.fromisoformat(str(value)[:10]).date()
    except Exception: return None


def normalize_territorial_layer(row: Dict[str, Any]) -> Dict[str, Any]:
    category=str(row.get("category") or "").strip().lower()
    source=str(row.get("source") or "").strip().upper()
    external_id=str(row.get("external_id") or row.get("id") or "").strip()
    item={
        "id": external_id,
        "external_id": external_id,
        "category": category,
        "source": source,
        "display_source": row.get("display_source") or DISPLAY_SOURCES.get(source, source or "Fonte non specificata"),
        "label": row.get("label") or row.get("scientific_name") or "Dato territoriale",
        "scientific_name": row.get("scientific_name") or "",
        "data_type": row.get("data_type") or "territorial_context",
        "count": _int(row.get("count"),0),
        "period_start": row.get("period_start") or "",
        "period_end": row.get("period_end") or "",
        "country": row.get("country") or "Italy",
        "region": row.get("region") or "",
        "province": row.get("province") or "",
        "location": row.get("location") or row.get("province") or row.get("region") or "",
        "lat": _float(row.get("lat")),
        "lon": _float(row.get("lon")),
        "radius_km": _float(row.get("radius_km"), 25.0),
        "color": row.get("color") or CATEGORY_COLORS.get(category,"#64748B"),
        "url_source": row.get("url_source") or "",
        "notes": row.get("notes") or "",
    }
    return item


def load_territorial_layers(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path): return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows=list(csv.DictReader(f))
    out=[]
    for raw in rows:
        item=normalize_territorial_layer(raw)
        if not item.get("external_id") or not item.get("category") or item.get("lat") is None or item.get("lon") is None:
            continue
        out.append(item)
    return out


def filter_territorial_layers(layers: List[Dict[str, Any]], lat=None, lon=None, radius_km=100, category="all", days=365, source=None, distance_fn: Callable|None=None, parse_date_fn: Callable|None=None) -> List[Dict[str, Any]]:
    category_l=str(category or "all").lower().strip()
    source_l=str(source or "").upper().strip()
    cutoff=None
    if days:
        cutoff=datetime.now(timezone.utc).date()-timedelta(days=int(days))
    out=[]
    for item in layers:
        if category_l not in ("", "all") and item.get("category") != category_l: continue
        if source_l and item.get("source") != source_l: continue
        if cutoff:
            end=(parse_date_fn or _date)(item.get("period_end")) or (parse_date_fn or _date)(item.get("period_start"))
            if end and end < cutoff: continue
        distance=None
        if lat is not None and lon is not None and distance_fn:
            distance=distance_fn(float(lat),float(lon),float(item["lat"]),float(item["lon"]))
            if distance > float(radius_km): continue
        enriched=dict(item)
        if distance is not None: enriched["distance_km"]=round(distance,2)
        out.append(enriched)
    out.sort(key=lambda x:(x.get("distance_km", 0), x.get("category",""), x.get("label","")))
    return out


def territorial_layers_csv_status(path: str) -> Dict[str, Any]:
    exists=os.path.exists(path)
    rows=load_territorial_layers(path) if exists else []
    categories={}
    sources={}
    for row in rows:
        categories[row.get("category")]=categories.get(row.get("category"),0)+1
        sources[row.get("source")]=sources.get(row.get("source"),0)+1
    return {"path":path,"exists":exists,"rows":len(rows),"categories":categories,"sources":sources}
