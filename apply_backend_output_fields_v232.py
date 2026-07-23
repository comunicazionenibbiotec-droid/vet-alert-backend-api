#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import py_compile, re
MAIN = Path('main.py')
if not MAIN.exists(): raise SystemExit('main.py not found. Run from backend root.')
backup = Path(f"main.before_output_fields_v232_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.py")
text = MAIN.read_text(encoding='utf-8')
backup.write_text(text, encoding='utf-8')
Path('scripts').mkdir(exist_ok=True)
src = Path(__file__).resolve().parent/'scripts'/'normalize_territorial_layers_radius_v232.py'
(Path('scripts')/'normalize_territorial_layers_radius_v232.py').write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
helper = r'''
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
'''
if 'def _v232_decorate_layers' not in text:
    marker='@app.get("/territorial-layers/status")'
    if marker not in text: marker='@app.get("/territorial-layers")'
    text = text.replace(marker, helper+'\n'+marker, 1)
# Patch get_territorial_layers function robustly: insert before first return dict inside that function.
route = '@app.get("/territorial-layers")'
pos = text.find(route)
if pos == -1: raise SystemExit('Could not find /territorial-layers route')
next_app = text.find('\n@app.', pos+1)
if next_app == -1: next_app = len(text)
block = text[pos:next_app]
if '_v232_decorate_layers(out)' not in block:
    idx = block.rfind('return {')
    if idx == -1: raise SystemExit('Could not find return dict inside /territorial-layers route')
    block = block[:idx] + 'out=_v232_decorate_layers(out)\n    ' + block[idx:]
    text = text[:pos] + block + text[next_app:]
# Patch export JSON similarly.
text = text.replace('if format.lower()=="json": return {"count":len(layers),"layers":layers}', 'if format.lower()=="json":\n        layers=_v232_decorate_layers(layers)\n        return {"count":len(layers),"layers":layers}')
text = text.replace('layers=_decorate_territorial_output(layers)', 'layers=_v232_decorate_layers(layers)')
# Patch or add normalize endpoint to call v232 script.
text = text.replace('scripts/normalize_territorial_layers_radius_v231.py', 'scripts/normalize_territorial_layers_radius_v232.py')
text = text.replace('scripts/normalize_territorial_layers_radius_v230.py', 'scripts/normalize_territorial_layers_radius_v232.py')
# Ensure endpoint exists if prior patch was not present.
if '/sync/territorial-layers/normalize-radius/run' not in text:
    endpoint='''\n@app.post("/sync/territorial-layers/normalize-radius/run")\ndef run_territorial_radius_normalization(x_sync_token:str|None=Header(default=None)):\n    require_sync_token(x_sync_token)\n    started=now_iso()\n    try:\n        p=subprocess.run([sys.executable,"scripts/normalize_territorial_layers_radius_v232.py"],capture_output=True,text=True,timeout=int(os.getenv("TERRITORIAL_NORMALIZE_TIMEOUT_SECONDS","300")))\n        if p.returncode!=0:\n            log_sync("TERRITORIAL_RADIUS_NORMALIZE","error",(p.stderr or p.stdout)[-1000:],0,0,0,started)\n            raise HTTPException(status_code=500, detail=(p.stderr or p.stdout)[-4000:])\n        try: result=json.loads(p.stdout)\n        except Exception: result={"stdout":p.stdout[-4000:]}\n        log_sync("TERRITORIAL_RADIUS_NORMALIZE","success","Territorial radius and output fields normalized",int(result.get("rows",0) or 0),0,int(result.get("changed",0) or 0),started)\n        return result\n    except HTTPException:\n        raise\n    except Exception as e:\n        log_sync("TERRITORIAL_RADIUS_NORMALIZE","error",str(e),0,0,0,started)\n        raise HTTPException(status_code=500, detail=str(e))\n'''
    text = text.replace('@app.get("/territorial-layers/status")', endpoint+'\n@app.get("/territorial-layers/status")', 1)
MAIN.write_text(text, encoding='utf-8')
try:
    py_compile.compile(str(MAIN), doraise=True)
    py_compile.compile('scripts/normalize_territorial_layers_radius_v232.py', doraise=True)
except Exception as e:
    MAIN.write_text(backup.read_text(encoding='utf-8'), encoding='utf-8')
    raise SystemExit(f'Patch failed; restored {backup}: {e}')
print(f'OK applied output fields v232. Backup: {backup}')
