#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import py_compile
MAIN = Path('main.py')
if not MAIN.exists():
    raise SystemExit('main.py not found. Run from backend root.')
backup = Path(f"main.before_pilot_municipal_layers_v239_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.py")
text = MAIN.read_text(encoding='utf-8')
backup.write_text(text, encoding='utf-8')
Path('scripts').mkdir(exist_ok=True)
src = Path(__file__).resolve().parent / 'scripts' / 'build_pilot_municipal_vector_layers_v239.py'
(Path('scripts') / 'build_pilot_municipal_vector_layers_v239.py').write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
endpoint = r'''
@app.post("/sync/territorial-layers/pilot-municipal-layers/run")
def run_pilot_municipal_vector_layers(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    try:
        p=subprocess.run([sys.executable,"scripts/build_pilot_municipal_vector_layers_v239.py"],capture_output=True,text=True,timeout=int(os.getenv("PILOT_MUNICIPAL_LAYER_TIMEOUT_SECONDS","300")))
        if p.returncode!=0:
            log_sync("PILOT_MUNICIPAL_VECTOR_LAYERS","error",(p.stderr or p.stdout)[-1000:],0,0,0,started)
            raise HTTPException(status_code=500, detail=(p.stderr or p.stdout)[-4000:])
        try: result=json.loads(p.stdout)
        except Exception: result={"stdout":p.stdout[-4000:]}
        log_sync("PILOT_MUNICIPAL_VECTOR_LAYERS","success","Pilot municipal vector context layers built",int(result.get("inserted",0) or 0)+int(result.get("updated",0) or 0),int(result.get("inserted",0) or 0),int(result.get("updated",0) or 0),started)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_sync("PILOT_MUNICIPAL_VECTOR_LAYERS","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))
'''
if '/sync/territorial-layers/pilot-municipal-layers/run' not in text:
    marker = '@app.get("/territorial-layers/status")'
    if marker not in text:
        marker = '@app.post("/sync/territorial-layers/normalize-radius/run")'
    text = text.replace(marker, endpoint + '\n' + marker, 1)
MAIN.write_text(text, encoding='utf-8')
try:
    py_compile.compile(str(MAIN), doraise=True)
    py_compile.compile('scripts/build_pilot_municipal_vector_layers_v239.py', doraise=True)
except Exception as e:
    MAIN.write_text(backup.read_text(encoding='utf-8'), encoding='utf-8')
    raise SystemExit(f'Patch failed; restored {backup}: {e}')
print(f'OK applied pilot municipal vector layers v239. Backup: {backup}')
print('New endpoint: /sync/territorial-layers/pilot-municipal-layers/run')
