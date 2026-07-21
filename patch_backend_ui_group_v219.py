#!/usr/bin/env python3
"""
Patch vet.ector FastAPI backend main.py with backend-owned UI grouping for territorial layers.

Adds explicit fields to each layer/occurrence:
- ui_group: sand_flies | ticks | mosquitoes_other_vectors | parasites | west_nile
- ui_group_label: Flebotomi | Zecche | Zanzare / altri vettori | Parassiti | West Nile
- subcategory: same as ui_group
- localization_precision: coordinate / puntuale | comunale | provinciale | regionale | territoriale
- display_radius_km: 10 for coordinate/comune, 25 for province/region

Usage from backend root:
  python patch_backend_ui_group_v219.py

It creates a timestamped backup of main.py before modifying it.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import re
import py_compile
import sys

MAIN = Path("main.py")
if not MAIN.exists():
    raise SystemExit("main.py not found. Run this script from the FastAPI backend root.")

text = MAIN.read_text(encoding="utf-8")
backup = Path(f"main.before_ui_group_v219_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.py")
backup.write_text(text, encoding="utf-8")

HELPERS = r'''
# --- v219: backend-owned UI grouping for territorial map layers ---
UI_GROUP_LABELS = {
    "sand_flies": "Flebotomi",
    "ticks": "Zecche",
    "mosquitoes_other_vectors": "Zanzare / altri vettori",
    "parasites": "Parassiti",
    "west_nile": "West Nile",
}

def _ui_text(row):
    keys = [
        "category", "label", "scientific_name", "common_group", "pathogen_focus",
        "data_type", "type", "source", "display_source", "notes", "note"
    ]
    return " ".join(str(row.get(k, "")) for k in keys if row.get(k) is not None).lower()

def vetector_ui_group(row):
    """Return stable frontend group, owned by backend rather than inferred by the frontend."""
    category = str(row.get("category") or "").lower().strip()
    text = _ui_text(row)

    # West Nile first: this is a surveillance layer, not a generic mosquito layer.
    if category == "west_nile" or "west nile" in text or "usutu" in text:
        return "west_nile"

    # Parasites / parasite diagnostic context.
    if (
        category in {"parasites", "parasite"}
        or "giardia" in text or "toxocara" in text or "ancylostoma" in text
        or "dirofilaria" in text or "echinococcus" in text
        or "parasite" in text or "parassit" in text
    ):
        return "parasites"

    # Sand flies / leishmaniasis pilot.
    if (
        "phlebotomus" in text or "phlebotominae" in text or "phlebotomine" in text
        or "sand fly" in text or "sandfly" in text or "sand_fly" in text
        or "flebotom" in text
        or ((category in {"vectors", "vector"}) and (
            "leishmania" in text or "leishmaniosi" in text or "leishmaniasis" in text or "leish" in text
        ))
    ):
        return "sand_flies"

    # Ticks.
    if (
        "ixodes" in text or "dermacentor" in text or "hyalomma" in text
        or "rhipicephalus" in text or "ornithodoros" in text or "amblyomma" in text
        or "tick" in text or "zecc" in text
    ):
        return "ticks"

    # All remaining vector records, including mosquitoes and biting midges.
    if (
        category in {"vectors", "vector"}
        or "aedes" in text or "culex" in text or "anopheles" in text
        or "culicoides" in text or "mosquito" in text or "zanzar" in text or "midge" in text
    ):
        return "mosquitoes_other_vectors"

    # Safe fallback: preserve visibility under generic vectors rather than dropping records.
    return "mosquitoes_other_vectors"

def vetector_localization_precision(row):
    def has_value(*keys):
        return any(str(row.get(k) or "").strip() for k in keys)
    lat = row.get("lat")
    lon = row.get("lon")
    try:
        if lat is not None and lon is not None and str(lat) != "" and str(lon) != "":
            float(lat); float(lon)
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
    # Keep old radius_km untouched for data compatibility, but expose display radius explicitly.
    return out

def apply_ui_groups(rows):
    return [apply_ui_group(r) for r in (rows or [])]

def ui_group_counts(rows):
    stats = {}
    for r in rows or []:
        g = r.get("ui_group") or vetector_ui_group(r)
        stats[g] = stats.get(g, 0) + 1
    return stats
# --- end v219 UI grouping ---
'''

if "def vetector_ui_group(" not in text:
    marker = '@app.get("/territorial-layers/status")'
    if marker not in text:
        marker = '@app.get("/territorial-layers")'
    if marker not in text:
        raise SystemExit("Could not find territorial-layers endpoint marker.")
    text = text.replace(marker, HELPERS + "\n" + marker, 1)

# Patch territorial-layers endpoint response. This covers older and newer versions where `out` is the layer list.
text = text.replace(
    'return {"count":len(out),"layers":out,"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days}',
    'out=apply_ui_groups(out)\n    return {"count":len(out),"layers":out,"ui_group_counts":ui_group_counts(out),"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days}'
)
text = text.replace(
    'return {"count":len(out),"layers":out,"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days,"species":species,"focus":focus,"leishmaniasis":leishmaniasis}',
    'out=apply_ui_groups(out)\n    return {"count":len(out),"layers":out,"ui_group_counts":ui_group_counts(out),"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days,"species":species,"focus":focus,"leishmaniasis":leishmaniasis}'
)
text = text.replace(
    'return {"count":len(out),"layers":out,"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days,"species":species,"focus":focus,"leishmaniasis":leishmaniasis,"vector_occurrence_layers":vector_count,"include_vector_occurrences":include_vector_occurrences}',
    'out=apply_ui_groups(out)\n    return {"count":len(out),"layers":out,"ui_group_counts":ui_group_counts(out),"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days,"species":species,"focus":focus,"leishmaniasis":leishmaniasis,"vector_occurrence_layers":vector_count,"include_vector_occurrences":include_vector_occurrences}'
)

# Patch export json response if present.
text = text.replace(
    'if format.lower()=="json": return {"count":len(layers),"layers":layers}',
    'if format.lower()=="json":\n        layers=apply_ui_groups(layers)\n        return {"count":len(layers),"layers":layers,"ui_group_counts":ui_group_counts(layers)}'
)

# Add extra export fields if field list exists.
text = text.replace(
    '"color","url_source","notes"]',
    '"color","url_source","notes","ui_group","ui_group_label","subcategory","localization_precision","display_radius_km"]'
)

# Patch vector-occurrences endpoint if it returns an `out` list.
# This is intentionally conservative and idempotent.
text = text.replace(
    'return {"query":{"lat":lat,"lon":lon,"radius_km":radius_km,"species":species,"group":group,"focus":focus,"leishmaniasis":leishmaniasis,"limit":limit},"count":len(out),"occurrences":out}',
    'out=apply_ui_groups(out)\n    return {"query":{"lat":lat,"lon":lon,"radius_km":radius_km,"species":species,"group":group,"focus":focus,"leishmaniasis":leishmaniasis,"limit":limit},"count":len(out),"ui_group_counts":ui_group_counts(out),"occurrences":out}'
)
text = text.replace(
    'return {"query":{"lat":lat,"lon":lon,"radius_km":radiusKm,"species":species,"focus":focus,"group":group,"leishmaniasis":leishOnly,"limit":limit},"occurrences":out}',
    'out=apply_ui_groups(out)\n    return {"query":{"lat":lat,"lon":lon,"radius_km":radiusKm,"species":species,"focus":focus,"group":group,"leishmaniasis":leishOnly,"limit":limit},"count":len(out),"ui_group_counts":ui_group_counts(out),"occurrences":out}'
)

# Add a dedicated diagnostic endpoint.
DIAG = r'''
@app.get("/territorial-layers/ui-groups/status")
def get_territorial_layers_ui_groups_status(lat:float|None=Query(None), lon:float|None=Query(None), radius_km:float=Query(100,ge=1,le=2000), category:str=Query("all"), days:int=Query(365,ge=1,le=3650)):
    layers = load_territorial_layers(TERRITORIAL_LAYERS_CSV_PATH)
    out = filter_territorial_layers(layers, lat=lat, lon=lon, radius_km=radius_km, category=category, days=days, distance_fn=haversine_km, parse_date_fn=parse_date)
    out = apply_ui_groups(out)
    return {"status":"ok", "count":len(out), "ui_group_counts":ui_group_counts(out), "sample":out[:10]}
'''
if '@app.get("/territorial-layers/ui-groups/status")' not in text:
    marker = '@app.get("/territorial-layers/export")'
    if marker in text:
        text = text.replace(marker, DIAG + "\n" + marker, 1)
    else:
        text += "\n" + DIAG + "\n"

MAIN.write_text(text, encoding="utf-8")
try:
    py_compile.compile(str(MAIN), doraise=True)
except Exception as e:
    # restore backup on syntax failure
    MAIN.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    raise SystemExit(f"Patch failed; restored backup {backup}: {e}")

print(f"Patched main.py successfully. Backup: {backup}")
