#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import py_compile
MAIN = Path('main.py')
if not MAIN.exists():
    raise SystemExit('main.py not found. Run from backend root.')
backup = Path(f"main.before_piem_liguria_genus_v235_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.py")
text = MAIN.read_text(encoding='utf-8')
backup.write_text(text, encoding='utf-8')
Path('scripts').mkdir(exist_ok=True)
src = Path(__file__).resolve().parent / 'scripts' / 'import_gbif_piem_liguria_genus_province_v235.py'
(Path('scripts') / 'import_gbif_piem_liguria_genus_province_v235.py').write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
endpoint = r'''
@app.post("/sync/territorial-layers/piemonte-liguria-genus/run")
def run_piem_liguria_genus_vector_import(x_sync_token:str|None=Header(default=None)):
    require_sync_token(x_sync_token)
    started=now_iso()
    try:
        p=subprocess.run([sys.executable,"scripts/import_gbif_piem_liguria_genus_province_v235.py"],capture_output=True,text=True,timeout=int(os.getenv("GENUS_IMPORT_TIMEOUT_SECONDS","3600")))
        if p.returncode!=0:
            log_sync("GBIF_PIEMONTE_LIGURIA_GENUS_VECTORS","error",(p.stderr or p.stdout)[-1000:],0,0,0,started)
            raise HTTPException(status_code=500, detail=(p.stderr or p.stdout)[-4000:])
        try: result=json.loads(p.stdout)
        except Exception: result={"stdout":p.stdout[-4000:]}
        log_sync("GBIF_PIEMONTE_LIGURIA_GENUS_VECTORS","success","Piemonte/Liguria genus/province vector occurrences imported",int(result.get("candidate_rows",0) or 0),int(result.get("inserted",0) or 0),int(result.get("updated",0) or 0),started)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_sync("GBIF_PIEMONTE_LIGURIA_GENUS_VECTORS","error",str(e),0,0,0,started)
        raise HTTPException(status_code=500, detail=str(e))
'''
if '/sync/territorial-layers/piemonte-liguria-genus/run' not in text:
    marker = '@app.get("/territorial-layers/status")'
    if marker not in text:
        marker = '@app.post("/sync/territorial-layers/piemonte-liguria/run")'
    text = text.replace(marker, endpoint + '\n' + marker, 1)
MAIN.write_text(text, encoding='utf-8')
try:
    py_compile.compile(str(MAIN), doraise=True)
    py_compile.compile('scripts/import_gbif_piem_liguria_genus_province_v235.py', doraise=True)
except Exception as e:
    MAIN.write_text(backup.read_text(encoding='utf-8'), encoding='utf-8')
    raise SystemExit(f'Patch failed; restored {backup}: {e}')
print(f'OK applied Piemonte/Liguria genus/province importer v235. Backup: {backup}')
print('New endpoint: /sync/territorial-layers/piemonte-liguria-genus/run')
