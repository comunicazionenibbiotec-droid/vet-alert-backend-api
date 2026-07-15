#!/usr/bin/env python3
from __future__ import annotations
import csv, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'/'territorial_layers'
STATUS=DATA/'refresh_status.json'
TERRITORIAL=DATA/'territorial_layers.csv'

FIELDNAMES=['external_id','category','source','label','scientific_name','data_type','count','period_start','period_end','country','region','province','location','lat','lon','radius_km','color','url_source','notes']

def run_step(name, cmd, required=False):
    started=datetime.now(timezone.utc).isoformat()
    result={'name':name,'started_at':started,'status':'skipped','command':' '.join(cmd)}
    script=ROOT/cmd[1] if len(cmd)>1 and cmd[0].endswith('python') else None
    try:
        proc=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=int(os.getenv('TERRITORIAL_REFRESH_STEP_TIMEOUT','240')))
        result.update({'returncode':proc.returncode,'stdout':proc.stdout[-4000:],'stderr':proc.stderr[-4000:]})
        if proc.returncode==0:
            result['status']='success'
        else:
            result['status']='error'
            if required:
                raise RuntimeError(proc.stderr or proc.stdout or f'{name} failed')
    except FileNotFoundError as e:
        result.update({'status':'missing','error':str(e)})
        if required: raise
    except Exception as e:
        result.update({'status':'error','error':str(e)})
        if required: raise
    result['finished_at']=datetime.now(timezone.utc).isoformat()
    return result

def validate_csv(path):
    errors=[]; counts={}; rows=0; ids=set()
    if not path.exists():
        return {'ok':False,'rows':0,'errors':['missing territorial_layers.csv'],'counts':{}}
    with path.open(newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        missing=[c for c in FIELDNAMES if c not in (reader.fieldnames or [])]
        if missing: errors.append('missing columns: '+','.join(missing))
        for i,row in enumerate(reader,start=2):
            rows+=1
            eid=(row.get('external_id') or '').strip()
            if not eid: errors.append(f'line {i}: missing external_id')
            if eid in ids: errors.append(f'line {i}: duplicate {eid}')
            ids.add(eid)
            cat=(row.get('category') or '').strip()
            counts[cat]=counts.get(cat,0)+1
            for col in ('lat','lon','radius_km'):
                try: float(row.get(col,''))
                except Exception: errors.append(f'line {i}: bad {col}')
    return {'ok':not errors,'rows':rows,'errors':errors[:100],'counts':counts}

def main():
    DATA.mkdir(parents=True,exist_ok=True)
    steps=[]
    py=sys.executable
    # These scripts are optional; they preserve current data if remote sources fail.
    optional_scripts=[
        ('mosquito_alert',[py,'scripts/build_mosquito_alert_layers.py']),
        ('vectornet_gbif',[py,'scripts/build_vectornet_gbif_layers.py']),
        ('west_nile',[py,'scripts/build_west_nile_layers.py']),
        ('esccap',[py,'scripts/build_esccap_layers.py']),
    ]
    for name,cmd in optional_scripts:
        if (ROOT/cmd[1]).exists():
            steps.append(run_step(name,cmd,required=False))
        else:
            steps.append({'name':name,'status':'missing','finished_at':datetime.now(timezone.utc).isoformat()})
    validation=validate_csv(TERRITORIAL)
    status={'version':'v143-territorial-automation','generated_at':datetime.now(timezone.utc).isoformat(),'steps':steps,'validation':validation,'territorial_layers_path':str(TERRITORIAL.relative_to(ROOT))}
    STATUS.write_text(json.dumps(status,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(status,indent=2,ensure_ascii=False))
    if not validation['ok']:
        raise SystemExit(1)

if __name__=='__main__':
    main()
