#!/usr/bin/env python3
"""
vet.ector backend minimal patch v219
Adds backend-owned UI grouping fields to territorial layers without changing coordinates,
category, radius_km, source, label, or any existing localization.

Run from the FastAPI backend root, next to main.py:
  python apply_backend_ui_groups_minimal_v219.py
"""
from pathlib import Path
from datetime import datetime
import py_compile

MAIN = Path('main.py')
if not MAIN.exists():
    raise SystemExit('ERROR: main.py not found. Run this script from the backend root directory.')

backup = Path(f"main.before_ui_groups_minimal_v219_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.py")
text = MAIN.read_text(encoding='utf-8')
backup.write_text(text, encoding='utf-8')

HELPERS = r'''
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
'''

DIAG = r'''
@app.get("/territorial-layers/ui-groups/status")
def get_territorial_layers_ui_groups_status(lat:float|None=Query(None), lon:float|None=Query(None), radius_km:float=Query(100,ge=1,le=2000), category:str=Query("all"), days:int=Query(365,ge=1,le=3650), source:str|None=Query(None)):
    layers = load_territorial_layers(TERRITORIAL_LAYERS_CSV_PATH)
    out = filter_territorial_layers(layers, lat=lat, lon=lon, radius_km=radius_km, category=category, days=days, source=source, distance_fn=haversine_km, parse_date_fn=parse_date)
    out = apply_ui_groups(out)
    return {"status":"ok", "count":len(out), "ui_group_counts":ui_group_counts(out), "sample":out[:10]}
'''

try:
    if 'def vetector_ui_group(' not in text:
        marker = '@app.get("/territorial-layers/status")' if '@app.get("/territorial-layers/status")' in text else '@app.get("/territorial-layers")'
        if marker not in text:
            raise RuntimeError('Could not find territorial-layers endpoint marker.')
        text = text.replace(marker, HELPERS + '\n' + marker, 1)

    # Patch the known stable /territorial-layers return shape.
    old_return = 'return {"count":len(out),"layers":out,"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days}'
    new_return = 'out=apply_ui_groups(out)\n    return {"count":len(out),"layers":out,"ui_group_counts":ui_group_counts(out),"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days}'
    if old_return in text and '"ui_group_counts":ui_group_counts(out)' not in text:
        text = text.replace(old_return, new_return, 1)

    # Patch JSON export if present.
    old_export = 'if format.lower()=="json": return {"count":len(layers),"layers":layers}'
    new_export = 'if format.lower()=="json":\n        layers=apply_ui_groups(layers)\n        return {"count":len(layers),"layers":layers,"ui_group_counts":ui_group_counts(layers)}'
    if old_export in text:
        text = text.replace(old_export, new_export, 1)

    # Add fields to CSV export field list if present.
    text = text.replace(
        '"color","url_source","notes"]',
        '"color","url_source","notes","ui_group","ui_group_label","subcategory","localization_precision","display_radius_km"]'
    )

    # Add diagnostic endpoint, without altering existing endpoint behavior.
    if '@app.get("/territorial-layers/ui-groups/status")' not in text:
        marker = '@app.get("/territorial-layers/export")'
        if marker in text:
            text = text.replace(marker, DIAG + '\n' + marker, 1)
        else:
            text += '\n' + DIAG + '\n'

    MAIN.write_text(text, encoding='utf-8')
    py_compile.compile(str(MAIN), doraise=True)
except Exception as e:
    MAIN.write_text(backup.read_text(encoding='utf-8'), encoding='utf-8')
    raise SystemExit(f'ERROR: patch failed; main.py restored from {backup}: {e}')

print(f'OK: minimal backend ui_group patch applied. Backup created: {backup}')
print('New endpoint: /territorial-layers/ui-groups/status')
print('No coordinates, lat/lon, category, label, source, or radius_km were changed.')
