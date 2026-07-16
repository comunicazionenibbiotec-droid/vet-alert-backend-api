
#!/usr/bin/env python3
"""Merge territorial layers from curated/generated source CSVs.

This version includes: mosquito_alert_layers.csv, vectornet_gbif_layers.csv,
extended_vector_layers.csv, benv_parasite_layers.csv, esccap_parasites.csv,
and west_nile_surveillance.csv.
"""
import csv, json
from pathlib import Path
from datetime import datetime

BASE = Path('data/territorial_layers')
OUT = BASE/'territorial_layers.csv'
STATUS = BASE/'refresh_status.json'
COLS = ['external_id','source','disease','category','data_type','evidence_count','period_start','period_end','country','region','province','location','lat','lon','radius_km','url_source','notes']
SOURCES = [
    BASE/'mosquito_alert_layers.csv',
    BASE/'vectornet_gbif_layers.csv',
    BASE/'extended_vector_layers.csv',
    BASE/'benv_parasite_layers.csv',
    BASE/'esccap_parasites.csv',
    BASE/'west_nile_surveillance.csv',
]

def normalize_row(row, src_name):
    out={c: str(row.get(c,'') or '').strip() for c in COLS}
    # Backward compatibility with older schemas
    if not out['disease']:
        out['disease']=str(row.get('label') or row.get('scientific_name') or '').strip()
    if not out['evidence_count']:
        out['evidence_count']=str(row.get('count') or '1').strip()
    if not out['period_start']:
        out['period_start']=str(row.get('observation_date') or row.get('start_date') or '').strip()
    if not out['period_end']:
        out['period_end']=str(row.get('report_date') or row.get('end_date') or out['period_start']).strip()
    if not out['radius_km']:
        out['radius_km']=str(row.get('radius') or row.get('radiusKm') or '50').strip()
    if not out['external_id']:
        out['external_id']=f"{src_name}-{abs(hash(tuple(out.items())))%100000000}"
    return out

def main():
    BASE.mkdir(parents=True, exist_ok=True)
    rows=[]; status={'version':'v163-real-recent-territorial-data','generated_at':datetime.utcnow().isoformat()+'Z','sources':[]}
    seen=set()
    for p in SOURCES:
        item={'path':str(p),'exists':p.exists(),'rows':0,'status':'skipped'}
        if not p.exists():
            status['sources'].append(item); continue
        try:
            with p.open(newline='', encoding='utf-8') as f:
                reader=csv.DictReader(f)
                for row in reader:
                    if not row: continue
                    out=normalize_row(row, p.stem.upper())
                    if not out['category'] or not out['lat'] or not out['lon']:
                        continue
                    key=out['external_id']
                    if key in seen:
                        continue
                    seen.add(key); rows.append(out); item['rows']+=1
            item['status']='success'
        except Exception as e:
            item['status']='error'; item['error']=str(e)
        status['sources'].append(item)
    with OUT.open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=COLS)
        w.writeheader(); w.writerows(rows)
    counts={}
    for r in rows: counts[r['category']]=counts.get(r['category'],0)+1
    status['output']=str(OUT); status['rows_total']=len(rows); status['categories']=counts
    STATUS.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(status, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
