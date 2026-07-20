#!/usr/bin/env python3
from __future__ import annotations
import csv, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path.cwd()
STATUS_DIR = ROOT / "data" / "status"
REPORT_JSON = STATUS_DIR / "full_refresh_report.json"
REPORT_CSV = STATUS_DIR / "full_refresh_report.csv"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_bool(name: str, default: bool=True) -> bool:
    val=os.environ.get(name)
    if val is None: return default
    return val.strip().lower() in {"1","true","yes","on"}


def run_step(name: str, command: List[str], critical: bool=False, skip_if_missing: str|None=None) -> Dict[str, Any]:
    step={"name":name,"command":" ".join(command),"critical":critical,"started_at":now_iso()}
    if skip_if_missing and not (ROOT/skip_if_missing).exists():
        step.update({"status":"skipped","message":f"missing {skip_if_missing}","finished_at":now_iso()})
        return step
    try:
        proc=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,check=False,env={**os.environ,"PYTHONPATH":str(ROOT)})
        step.update({"returncode":proc.returncode,"stdout":proc.stdout[-4000:],"stderr":proc.stderr[-4000:],"finished_at":now_iso()})
        if proc.returncode==0:
            step["status"]="success"
        else:
            step["status"]="error"
            if critical: step["fatal"]=True
    except Exception as exc:
        step.update({"status":"error","exception":repr(exc),"finished_at":now_iso()})
        if critical: step["fatal"]=True
    return step


def count_csv(path: str) -> int|None:
    p=ROOT/path
    if not p.exists(): return None
    try:
        with p.open('r',encoding='utf-8-sig',newline='') as f:
            return max(0, sum(1 for _ in csv.DictReader(f)))
    except Exception:
        return None


def count_json_records(path: str) -> int|None:
    p=ROOT/path
    if not p.exists(): return None
    try:
        data=json.loads(p.read_text(encoding='utf-8'))
        if isinstance(data,list): return len(data)
        if isinstance(data,dict):
            if isinstance(data.get('diseases'),list): return len(data['diseases'])
            if isinstance(data.get('entities'),list): return len(data['entities'])
        return None
    except Exception:
        return None


def build_summary() -> Dict[str, Any]:
    return {
        "official_events": {
            "adis": count_csv("data/official_sources/adis_events.csv"),
            "wahis": count_csv("data/official_sources/wahis_events.csv"),
            "izs_benv": count_csv("data/official_sources/izs_benv_events.csv"),
        },
        "territorial_layers": {
            "total": count_csv("data/territorial_layers/territorial_layers.csv"),
            "mosquito_alert_layers": count_csv("data/territorial_layers/mosquito_alert_layers.csv"),
            "vectornet_gbif_layers": count_csv("data/territorial_layers/vectornet_gbif_layers.csv"),
            "extended_vector_layers": count_csv("data/territorial_layers/extended_vector_layers.csv"),
            "benv_parasite_layers": count_csv("data/territorial_layers/benv_parasite_layers.csv"),
            "west_nile_surveillance": count_csv("data/territorial_layers/west_nile_surveillance.csv"),
            "esccap_parasites": count_csv("data/territorial_layers/esccap_parasites.csv"),
        },
        "catalogs": {
            "diseases_public_html": count_json_records("public_html/data/diseases.json"),
            "diseases_data": count_json_records("data/diseases.json"),
        },
        "reports": {
            "data_sources_status_json": (ROOT/"data/status/data_sources_status.json").exists(),
            "territorial_status_report_json": (ROOT/"data/territorial_layers/territorial_layers_status_report.json").exists(),
            "benv_import_report_csv": (ROOT/"data/official_sources/benv_import_report.csv").exists(),
            "benv_companion_report_csv": (ROOT/"data/official_sources/benv_companion_report.csv").exists(),
        }
    }


def write_csv_report(report: Dict[str, Any]) -> None:
    rows=[]
    for s in report.get('steps',[]):
        rows.append({"section":"step","name":s.get('name'),"status":s.get('status'),"critical":s.get('critical'),"returncode":s.get('returncode'),"message":s.get('message','') or s.get('exception','')})
    for group, vals in report.get('summary',{}).items():
        if isinstance(vals,dict):
            for k,v in vals.items():
                rows.append({"section":group,"name":k,"status":"value","critical":"","returncode":"","message":v})
    with REPORT_CSV.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f, fieldnames=["section","name","status","critical","returncode","message"])
        w.writeheader(); w.writerows(rows)


def write_json_report(report: Dict[str, Any]) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    tmp=REPORT_JSON.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(REPORT_JSON)
    if not REPORT_JSON.exists() or REPORT_JSON.stat().st_size == 0:
        raise RuntimeError(f"Failed to write {REPORT_JSON}")


def main() -> int:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    steps=[]; py=sys.executable
    if env_bool('VETECTOR_FULL_REFRESH_RUN_BENV', True):
        steps.append(run_step('benv_build',[py,'scripts/benv_xlsx_to_vetector_csv.py'],critical=True,skip_if_missing='scripts/benv_xlsx_to_vetector_csv.py'))
        if (ROOT/'data/official_sources/izs_benv_events.csv').exists():
            steps.append(run_step('benv_validate',[py,'scripts/validate_italy_sources.py','data/official_sources/izs_benv_events.csv'],critical=True,skip_if_missing='scripts/validate_italy_sources.py'))
    if env_bool('VETECTOR_FULL_REFRESH_RUN_TERRITORIAL', True):
        steps.append(run_step('vectors_invasive_local',[py,'scripts/build_invasive_mosquito_layers.py'],skip_if_missing='scripts/build_invasive_mosquito_layers.py'))
        steps.append(run_step('vectors_extended_local',[py,'scripts/build_extended_vector_layers.py'],skip_if_missing='scripts/build_extended_vector_layers.py'))
        steps.append(run_step('parasites_from_benv',[py,'scripts/build_benv_parasite_layers.py'],skip_if_missing='scripts/build_benv_parasite_layers.py'))
        steps.append(run_step('territorial_merge',[py,'scripts/refresh_territorial_layers_all.py'],critical=True,skip_if_missing='scripts/refresh_territorial_layers_all.py'))
        if (ROOT/'data/territorial_layers/territorial_layers.csv').exists():
            steps.append(run_step('territorial_validate',[py,'scripts/validate_territorial_layers.py','data/territorial_layers/territorial_layers.csv'],critical=True,skip_if_missing='scripts/validate_territorial_layers.py'))
        steps.append(run_step('territorial_status_report',[py,'scripts/build_territorial_layers_status_report.py'],skip_if_missing='scripts/build_territorial_layers_status_report.py'))
    if env_bool('VETECTOR_FULL_REFRESH_RUN_DISEASES', True):
        if (ROOT/'public_html/data/diseases.json').exists():
            steps.append(run_step('diseases_validate_public_html',[py,'scripts/validate_diseases_catalog.py','public_html/data/diseases.json'],critical=True,skip_if_missing='scripts/validate_diseases_catalog.py'))
        elif (ROOT/'data/diseases.json').exists():
            steps.append(run_step('diseases_validate_data',[py,'scripts/validate_diseases_catalog.py','data/diseases.json'],critical=True,skip_if_missing='scripts/validate_diseases_catalog.py'))
        else:
            steps.append({"name":"diseases_validate","status":"skipped","critical":False,"message":"diseases.json not found","started_at":now_iso(),"finished_at":now_iso()})
    if env_bool('VETECTOR_FULL_REFRESH_RUN_STATUS', True):
        steps.append(run_step('data_sources_status',[py,'scripts/build_data_sources_status.py'],skip_if_missing='scripts/build_data_sources_status.py'))
    fatal=any(s.get('fatal') for s in steps)
    report={"version":"v178b-full-database-refresh-json-fix","generated_at":now_iso(),"status":"error" if fatal else "ok","steps":steps,"summary":build_summary()}
    write_json_report(report)
    write_csv_report(report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 1 if fatal else 0

if __name__=='__main__':
    raise SystemExit(main())
