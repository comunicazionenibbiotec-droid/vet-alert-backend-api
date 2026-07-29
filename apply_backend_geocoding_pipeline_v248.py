#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import py_compile, shutil

MAIN = Path('main.py')
if not MAIN.exists():
    raise SystemExit('main.py not found. Run from backend root.')
Path('scripts').mkdir(exist_ok=True)
src = Path(__file__).resolve().parent / 'scripts' / 'run_geocoding_corrections_v248.py'
dst = Path('scripts/run_geocoding_corrections_v248.py')
if src.resolve() != dst.resolve():
    shutil.copyfile(src, dst)
py_compile.compile(str(dst), doraise=True)

text = MAIN.read_text(encoding='utf-8')
if '/sync/geocoding-corrections/run' not in text:
    backup = Path(f"main.before_geocoding_pipeline_v248_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.py")
    backup.write_text(text, encoding='utf-8')
    endpoint = r'''
@app.post("/sync/geocoding-corrections/run")
def run_geocoding_corrections_pipeline(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    try:
        p=subprocess.run([sys.executable,"scripts/run_geocoding_corrections_v248.py"],capture_output=True,text=True,timeout=int(os.getenv("GEOCODING_CORRECTIONS_TIMEOUT_SECONDS","4200")))
        if p.returncode!=0:
            log_sync("GEOCODING_CORRECTIONS","error",(p.stderr or p.stdout)[-1000:],0,0,0,started)
            raise HTTPException(status_code=500, detail=(p.stderr or p.stdout)[-4000:])
        try: result=json.loads(p.stdout)
        except Exception: result={"stdout":p.stdout[-4000:]}
        log_sync("GEOCODING_CORRECTIONS","success","Geocoding corrections pipeline completed",0,0,0,started)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_sync("GEOCODING_CORRECTIONS","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))
'''
    marker='@app.get("/territorial-layers/status")'
    if marker not in text:
        marker='@app.get("/sync/territorial-layers/status")'
    if marker not in text:
        raise SystemExit('Could not find insertion marker in main.py')
    text = text.replace(marker, endpoint + '\n' + marker, 1)
    MAIN.write_text(text, encoding='utf-8')
    try:
        py_compile.compile(str(MAIN), doraise=True)
    except Exception as e:
        MAIN.write_text(backup.read_text(encoding='utf-8'), encoding='utf-8')
        raise SystemExit(f'Patch failed; restored {backup}: {e}')
    print(f'OK: installed geocoding corrections endpoint. Backup: {backup}')
else:
    print('OK: endpoint already present; script refreshed.')
print('New endpoint: POST /sync/geocoding-corrections/run')
