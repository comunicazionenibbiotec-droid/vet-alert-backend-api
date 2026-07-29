#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import py_compile, shutil

MAIN = Path('main.py')
if not MAIN.exists():
    raise SystemExit('main.py not found. Run from backend root.')
Path('scripts').mkdir(exist_ok=True)
src = Path(__file__).resolve().parent / 'scripts' / 'run_safe_refresh_pipeline_v249.py'
dst = Path('scripts/run_safe_refresh_pipeline_v249.py')
if src.resolve() != dst.resolve():
    shutil.copyfile(src, dst)
py_compile.compile(str(dst), doraise=True)

text = MAIN.read_text(encoding='utf-8')
if '/sync/safe-refresh/run' not in text:
    backup = Path(f"main.before_safe_refresh_v249_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.py")
    backup.write_text(text, encoding='utf-8')
    endpoint = r'''
def _run_local_script_json(script_args, timeout_seconds, sync_source, started_at):
    p=subprocess.run([sys.executable]+script_args,capture_output=True,text=True,timeout=timeout_seconds)
    if p.returncode!=0:
        log_sync(sync_source,"error",(p.stderr or p.stdout)[-1000:],0,0,0,started_at)
        raise HTTPException(status_code=500, detail=(p.stderr or p.stdout)[-4000:])
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"stdout":p.stdout[-4000:]}

@app.post("/sync/safe-refresh/run")
def run_safe_refresh_pipeline(mode:str=Query("light"), x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    mode=(mode or "light").strip().lower()
    if mode not in {"light","territorial","heavy","full"}:
        raise HTTPException(status_code=400, detail="mode must be one of: light, territorial, heavy, full")
    result={"status":"success","mode":mode,"started_at":started,"steps":{}}
    try:
        # 1) Refresh/generate territorial files when requested.
        if mode in {"territorial","full"}:
            result["steps"]["vectornet_gbif"] = sync_vectornet_gbif_layers(TERRITORIAL_LAYERS_CSV_PATH)
            result["steps"]["mosquito_alert"] = sync_mosquito_alert_layers(TERRITORIAL_LAYERS_CSV_PATH)
            result["steps"]["west_nile"] = sync_west_nile_layers(TERRITORIAL_LAYERS_CSV_PATH, WEST_NILE_CSV_PATH)
        if mode in {"heavy","full"}:
            # Heavy imports are run only if scripts are present. They are long, so keep them manual-controlled via mode.
            heavy_steps=[]
            for script_name, timeout_env, default_timeout in [
                ("scripts/import_gbif_piem_liguria_vectors_v234.py", "REGION_IMPORT_TIMEOUT_SECONDS", "2400"),
                ("scripts/import_gbif_piem_liguria_genus_province_v235.py", "GENUS_IMPORT_TIMEOUT_SECONDS", "3600"),
                ("scripts/import_real_city_vector_occurrences_v240.py", "REAL_CITY_IMPORT_TIMEOUT_SECONDS", "3600"),
            ]:
                if os.path.exists(script_name):
                    heavy_steps.append(_run_local_script_json([script_name], int(os.getenv(timeout_env, default_timeout)), "SAFE_REFRESH_HEAVY", started))
            result["steps"]["heavy_imports"] = heavy_steps
        # 2) File-based geocoding corrections and territorial normalization.
        result["steps"]["geocoding_corrections"] = _run_local_script_json(["scripts/run_safe_refresh_pipeline_v249.py", mode], int(os.getenv("SAFE_REFRESH_LOCAL_TIMEOUT_SECONDS","4200")), "SAFE_REFRESH_GEOCODING", started)
        # 3) Reload official CSVs into SQLite after corrected coordinates.
        if mode in {"light","full"}:
            result["steps"]["adis"] = sync_adis_events()
            result["steps"]["wahis"] = sync_wahis_events()
            result["steps"]["izs_benv"] = sync_izs_benv_events()
            result["steps"]["official_demo"] = sync_official_events()
        result["finished_at"] = now_iso()
        log_sync("SAFE_REFRESH_PIPELINE","success",f"Safe refresh completed mode={mode}",0,0,0,started)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_sync("SAFE_REFRESH_PIPELINE","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))
'''
    marker='@app.get("/sync/status")'
    if marker not in text:
        marker='@app.get("/risk/livestock-density")'
    if marker not in text:
        raise SystemExit('Could not find insertion marker in main.py')
    text = text.replace(marker, endpoint + '\n' + marker, 1)
    MAIN.write_text(text, encoding='utf-8')
    try:
        py_compile.compile(str(MAIN), doraise=True)
    except Exception as e:
        MAIN.write_text(backup.read_text(encoding='utf-8'), encoding='utf-8')
        raise SystemExit(f'Patch failed; restored {backup}: {e}')
    print(f'OK: installed safe refresh endpoint. Backup: {backup}')
else:
    print('OK: safe refresh endpoint already present; script refreshed.')
print('New endpoint: POST /sync/safe-refresh/run?mode=light|territorial|heavy|full')
