#!/usr/bin/env python3
"""Install precise vector occurrence importer and sync endpoint into vet.ector FastAPI backend."""
from pathlib import Path
from datetime import datetime
import py_compile

MAIN = Path("main.py")
if not MAIN.exists():
    raise SystemExit("main.py not found. Run from backend root.")
SCRIPTS = Path("scripts")
SCRIPTS.mkdir(exist_ok=True)
source_script = Path(__file__).resolve().parent / "scripts" / "import_precise_vector_occurrences_v220.py"
target_script = SCRIPTS / "import_precise_vector_occurrences_v220.py"
target_script.write_text(source_script.read_text(encoding="utf-8"), encoding="utf-8")

text = MAIN.read_text(encoding="utf-8")
backup = Path(f"main.before_precise_vectors_v220_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.py")
backup.write_text(text, encoding="utf-8")

endpoint = r'''
@app.post("/sync/territorial-layers/precise-vectors/run")
def run_precise_vector_territorial_sync(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    try:
        timeout=int(os.getenv("PRECISE_VECTOR_IMPORT_TIMEOUT_SECONDS","900"))
        p=subprocess.run([sys.executable,"scripts/import_precise_vector_occurrences_v220.py"],capture_output=True,text=True,timeout=timeout)
        if p.returncode!=0:
            log_sync("PRECISE_VECTOR_OCCURRENCES","error",(p.stderr or p.stdout)[-1000:],0,0,0,started)
            raise HTTPException(status_code=500, detail=(p.stderr or p.stdout)[-4000:])
        try:
            result=json.loads(p.stdout)
        except Exception:
            result={"stdout":p.stdout[-4000:]}
        log_sync("PRECISE_VECTOR_OCCURRENCES","success","Precise vector occurrence import completed",int(result.get("new_candidate_rows",0) or 0),int(result.get("inserted",0) or 0),int(result.get("updated",0) or 0),started)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_sync("PRECISE_VECTOR_OCCURRENCES","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))
'''
if '/sync/territorial-layers/precise-vectors/run' not in text:
    marker='@app.post("/sync/territorial-layers/vectornet-gbif/run")'
    if marker in text:
        text = text.replace(marker, endpoint + "\n" + marker, 1)
    else:
        marker='@app.get("/territorial-layers/export")'
        if marker in text:
            text = text.replace(marker, endpoint + "\n" + marker, 1)
        else:
            text += "\n" + endpoint + "\n"

MAIN.write_text(text, encoding="utf-8")
try:
    py_compile.compile(str(MAIN), doraise=True)
    py_compile.compile(str(target_script), doraise=True)
except Exception as e:
    MAIN.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    raise SystemExit(f"Patch failed; restored {backup}: {e}")
print(f"Installed precise vector importer. main.py backup: {backup}; script: {target_script}")
