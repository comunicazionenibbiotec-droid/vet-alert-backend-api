#!/usr/bin/env python3
from __future__ import annotations
import csv, json, urllib.request
from pathlib import Path
from datetime import datetime

REF_DIR = Path('data/reference')
COMUNI_LOCAL = REF_DIR / 'opendatasicilia_comuni.csv'
COORD_LOCAL = REF_DIR / 'opendatasicilia_coordinate.csv'
OUT = REF_DIR / 'italia_comuni_centroids.csv'
COMUNI_URL = 'https://raw.githubusercontent.com/opendatasicilia/comuni-italiani/main/dati/comuni.csv'
COORD_URL = 'https://raw.githubusercontent.com/opendatasicilia/comuni-italiani/main/dati/coordinate.csv'

def download(url, path):
    req = urllib.request.Request(url, headers={'User-Agent': 'vetector-comuni-reference-builder/246'})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    path.write_bytes(data)
    return len(data)

def ensure_sources(download_if_missing=True):
    REF_DIR.mkdir(parents=True, exist_ok=True)
    status = {}
    if download_if_missing and not COMUNI_LOCAL.exists():
        status['downloaded_comuni_bytes'] = download(COMUNI_URL, COMUNI_LOCAL)
    if download_if_missing and not COORD_LOCAL.exists():
        status['downloaded_coordinate_bytes'] = download(COORD_URL, COORD_LOCAL)
    if not COMUNI_LOCAL.exists() or not COORD_LOCAL.exists():
        raise SystemExit('Missing source files. Put comuni.csv as data/reference/opendatasicilia_comuni.csv and coordinate.csv as data/reference/opendatasicilia_coordinate.csv')
    return status

def read_csv(path):
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def main():
    status = ensure_sources(download_if_missing=True)
    comuni = read_csv(COMUNI_LOCAL)
    coords = read_csv(COORD_LOCAL)
    coord_by_code = {str(r.get('pro_com_t','')).zfill(6): r for r in coords}
    rows = []
    for c in comuni:
        code = str(c.get('pro_com_t','')).zfill(6)
        coord = coord_by_code.get(code)
        if not coord:
            continue
        lat = coord.get('lat')
        lon = coord.get('long') or coord.get('lon') or coord.get('lng')
        try:
            latf = float(str(lat).replace(',', '.'))
            lonf = float(str(lon).replace(',', '.'))
        except Exception:
            continue
        rows.append({
            'comune': c.get('comune','').strip(),
            'provincia': c.get('den_prov','').strip(),
            'sigla_provincia': c.get('sigla','').strip(),
            'regione': c.get('den_reg','').strip(),
            'lat': f'{latf:.6f}',
            'lon': f'{lonf:.6f}',
            'pro_com_t': code,
        })
    if len(rows) < 7000:
        raise SystemExit(f'Parsed only {len(rows)} comune coordinate rows; expected >7000. Check source CSV schemas.')
    backup = None
    if OUT.exists():
        backup = OUT.with_name(f'italia_comuni_centroids.before_v246_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.csv')
        backup.write_text(OUT.read_text(encoding='utf-8'), encoding='utf-8')
    with OUT.open('w', encoding='utf-8', newline='') as f:
        fields = ['comune','provincia','sigla_provincia','regione','lat','lon','pro_com_t']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
    print(json.dumps({
        'status': 'success',
        'rows': len(rows),
        'output': str(OUT),
        'backup': str(backup) if backup else None,
        **status
    }, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
