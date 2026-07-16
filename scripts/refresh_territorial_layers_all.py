#!/usr/bin/env python3
from __future__ import annotations
import csv, json
from pathlib import Path
from datetime import datetime, timezone
HEADERS=['external_id', 'category', 'source', 'label', 'scientific_name', 'data_type', 'count', 'period_start', 'period_end', 'country', 'region', 'province', 'location', 'lat', 'lon', 'radius_km', 'color', 'url_source', 'notes']
BASE=Path('data/territorial_layers')
OUT=BASE/'territorial_layers.csv'
STATUS=BASE/'refresh_status.json'
SOURCE_FILES=[BASE/'mosquito_alert_layers.csv',BASE/'vectornet_gbif_layers.csv',BASE/'extended_vector_layers.csv',BASE/'west_nile_surveillance.csv',BASE/'esccap_parasites.csv']

def read_rows(path):
    if not path.exists(): return []
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        return [{h:(r.get(h,'') or '').strip() for h in HEADERS} for r in csv.DictReader(f) if any((v or '').strip() for v in r.values())]

def main():
    rows=[]; seen=set(); status={'version':'v149-extended-vector-preserving-refresh','generated_at':datetime.now(timezone.utc).isoformat(),'sources':[]}
    for src in SOURCE_FILES:
        part=read_rows(src); status['sources'].append({'path':str(src),'rows':len(part),'exists':src.exists()})
        for r in part:
            eid=r.get('external_id')
            if not eid or eid in seen: continue
            seen.add(eid); rows.append(r)
    with OUT.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=HEADERS); w.writeheader(); w.writerows(rows)
    cats={}; species={}
    for r in rows:
        cats[r.get('category','')]=cats.get(r.get('category',''),0)+1
        species[r.get('scientific_name','')]=species.get(r.get('scientific_name',''),0)+1
    status.update({'rows_total':len(rows),'categories':cats,'species_counts':species})
    STATUS.write_text(json.dumps(status,indent=2,ensure_ascii=False),encoding='utf-8')
    print(status)
if __name__ == '__main__': main()
