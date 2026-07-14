#!/usr/bin/env python3
import csv, sys
from pathlib import Path

REQUIRED = ['external_id','category','source','label','count','lat','lon','radius_km']
VALID_CATEGORIES = {'vectors','parasites','west_nile'}

def fail(msg):
    print('ERROR', msg)
    sys.exit(1)

def main(path):
    p = Path(path)
    if not p.exists():
        fail(f'missing file: {path}')
    rows = 0
    ids = set()
    with p.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            fail(f'missing columns: {missing}')
        for i, row in enumerate(reader, start=2):
            rows += 1
            eid = (row.get('external_id') or '').strip()
            if not eid:
                fail(f'{path}:{i}: missing external_id')
            if eid in ids:
                fail(f'{path}:{i}: duplicate external_id {eid}')
            ids.add(eid)
            cat = (row.get('category') or '').strip()
            if cat not in VALID_CATEGORIES:
                fail(f'{path}:{i}: invalid category {cat}')
            for c in ['lat','lon','radius_km']:
                try:
                    float(row.get(c, ''))
                except Exception:
                    fail(f'{path}:{i}: invalid {c}')
            try:
                int(float(row.get('count', '')))
            except Exception:
                fail(f'{path}:{i}: invalid count')
    print(f'OK {path} rows={rows}')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'data/territorial_layers/territorial_layers.csv')
