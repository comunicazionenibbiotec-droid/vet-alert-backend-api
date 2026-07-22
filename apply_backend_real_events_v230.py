#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import py_compile, re
MAIN=Path('main.py')
if not MAIN.exists(): raise SystemExit('main.py not found. Run from backend root.')
backup=Path(f"main.before_real_events_v230_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.py")
text=MAIN.read_text(encoding='utf-8')
backup.write_text(text,encoding='utf-8')
Path('scripts').mkdir(exist_ok=True)
for src in ['import_gbif_real_vector_events_v230.py','normalize_territorial_layers_radius_v230.py']:
    p=Path(__file__).resolve().parent/'scripts'/src
    (Path('scripts')/src).write_text(p.read_text(encoding='utf-8'),encoding='utf-8')
endpoint=r'''
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
        p=subprocess.run([sys.executable,"scripts/normalize_territorial_layers_radius_v230.py"],capture_output=True,text=True,timeout=int(os.getenv("TERRITORIAL_NORMALIZE_TIMEOUT_SECONDS","300")))
        if p.returncode!=0:
            log_sync("TERRITORIAL_RADIUS_NORMALIZE","error",(p.stderr or p.stdout)[-1000:],0,0,0,started)
            raise HTTPException(status_code=500, detail=(p.stderr or p.stdout)[-4000:])
        try: result=json.loads(p.stdout)
        except Exception: result={"stdout":p.stdout[-4000:]}
        log_sync("TERRITORIAL_RADIUS_NORMALIZE","success","Territorial radius and ui_group normalized",int(result.get("rows",0) or 0),0,int(result.get("changed",0) or 0),started)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_sync("TERRITORIAL_RADIUS_NORMALIZE","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))
'''
if '/sync/territorial-layers/real-events/run' not in text:
    marker='@app.get("/territorial-layers/status")'
    if marker not in text: marker='@app.post("/sync/territorial-layers/run")'
    text=text.replace(marker,endpoint+'\n'+marker,1)
# Decorate API output without changing CSV if helper not present
helpers=r'''
# --- v230 territorial output normalization ---
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
'''
if 'def _decorate_territorial_output' not in text:
    text=text.replace('@app.get("/territorial-layers/status")',helpers+'\n@app.get("/territorial-layers/status")',1)
text=text.replace('return {"count":len(out),"layers":out,"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days}', 'out=_decorate_territorial_output(out)\n    return {"count":len(out),"layers":out,"source_file":TERRITORIAL_LAYERS_CSV_PATH,"category":category,"days":days}')
text=text.replace('if format.lower()=="json": return {"count":len(layers),"layers":layers}', 'if format.lower()=="json":\n        layers=_decorate_territorial_output(layers)\n        return {"count":len(layers),"layers":layers}')
# Expand export fields if present
text=text.replace('"color","url_source","notes"]','"color","url_source","notes","ui_group","ui_group_label","subcategory","localization_precision","display_radius_km"]')
MAIN.write_text(text,encoding='utf-8')
try:
    py_compile.compile(str(MAIN),doraise=True)
    py_compile.compile('scripts/import_gbif_real_vector_events_v230.py',doraise=True)
    py_compile.compile('scripts/normalize_territorial_layers_radius_v230.py',doraise=True)
except Exception as e:
    MAIN.write_text(backup.read_text(encoding='utf-8'),encoding='utf-8')
    raise SystemExit(f'Patch failed; restored {backup}: {e}')
print(f'OK applied real events v230. Backup: {backup}')
