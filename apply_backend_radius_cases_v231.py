#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import py_compile, re

MAIN = Path('main.py')
if not MAIN.exists():
    raise SystemExit('main.py not found. Run from backend root.')
backup = Path(f"main.before_radius_cases_v231_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.py")
text = MAIN.read_text(encoding='utf-8')
backup.write_text(text, encoding='utf-8')
Path('scripts').mkdir(exist_ok=True)
source = Path(__file__).resolve().parent/'scripts'/'normalize_territorial_layers_radius_v231.py'
(Path('scripts')/'normalize_territorial_layers_radius_v231.py').write_text(source.read_text(encoding='utf-8'), encoding='utf-8')

endpoint = r'''
@app.post("/sync/territorial-layers/normalize-radius/run")
def run_territorial_radius_normalization(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    try:
        p=subprocess.run([sys.executable,"scripts/normalize_territorial_layers_radius_v231.py"],capture_output=True,text=True,timeout=int(os.getenv("TERRITORIAL_NORMALIZE_TIMEOUT_SECONDS","300")))
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
'''
# Replace any existing normalize-radius endpoint block, otherwise insert it.
pattern = r'@app\.post\("/sync/territorial-layers/normalize-radius/run"\)\ndef run_territorial_radius_normalization\(.*?\n(?=@app\.|def |\Z)'
text, n = re.subn(pattern, endpoint+'\n', text, count=1, flags=re.S)
if n == 0:
    marker = '@app.get("/territorial-layers/status")'
    if marker not in text:
        marker = '@app.post("/sync/territorial-layers/run")'
    text = text.replace(marker, endpoint+'\n'+marker, 1)

helpers = r'''
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
'''
# Replace older helper block if present.
helper_pattern = r'# --- v2\d+ territorial output normalization.*?# --- end v2\d+ territorial output normalization ---\n'
text, hn = re.subn(helper_pattern, helpers+'\n', text, count=1, flags=re.S)
if hn == 0:
    text = text.replace('@app.get("/territorial-layers/status")', helpers+'\n@app.get("/territorial-layers/status")', 1)
# Ensure /territorial-layers response decorates output.
if 'out=_decorate_territorial_output(out)' not in text:
    text = text.replace('return {"count":len(out),"layers":out,"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days}', 'out=_decorate_territorial_output(out)\n    return {"count":len(out),"layers":out,"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days}')
# Ensure json export decorates output.
text = text.replace('if format.lower()=="json": return {"count":len(layers),"layers":layers}', 'if format.lower()=="json":\n        layers=_decorate_territorial_output(layers)\n        return {"count":len(layers),"layers":layers}')
# Ensure export has fields.
text = text.replace('"color","url_source","notes"]', '"color","url_source","notes","ui_group","ui_group_label","subcategory","localization_precision","display_radius_km","case_count"]')
MAIN.write_text(text, encoding='utf-8')
try:
    py_compile.compile(str(MAIN), doraise=True)
    py_compile.compile('scripts/normalize_territorial_layers_radius_v231.py', doraise=True)
except Exception as e:
    MAIN.write_text(backup.read_text(encoding='utf-8'), encoding='utf-8')
    raise SystemExit(f'Patch failed; restored {backup}: {e}')
print(f'OK applied radius/cases v231. Backup: {backup}')
print('Endpoint updated: /sync/territorial-layers/normalize-radius/run')
