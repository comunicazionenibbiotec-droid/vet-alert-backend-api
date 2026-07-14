#!/usr/bin/env python3
import csv
from pathlib import Path

BASE = Path('data/territorial_layers')
OUT = BASE / 'territorial_layers.csv'
SOURCES = [
    BASE / 'west_nile_surveillance.csv',
    BASE / 'mosquito_alert_layers.csv',
    BASE / 'vectornet_gbif_layers.csv',
    BASE / 'esccap_parasites.csv',
]

def main():
    all_rows = []
    fieldnames = None
    seen = set()
    for path in SOURCES:
        if not path.exists():
            continue
        with path.open('r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if fieldnames is None:
                fieldnames = reader.fieldnames
            for row in reader:
                eid = (row.get('external_id') or '').strip()
                if not eid or eid in seen:
                    continue
                seen.add(eid)
                all_rows.append(row)
    if fieldnames is None:
        raise SystemExit('No source CSVs found')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f'Wrote {OUT} rows={len(all_rows)}')

if __name__ == '__main__':
    main()
