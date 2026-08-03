#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, math, re, shutil, unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_EVENTS = Path('data/official_sources/izs_benv_events.csv')
DEFAULT_COMUNI = Path('data/reference/italia_comuni_centroids.csv')
DEFAULT_REPORT = Path('data/official_sources/geocoding_fix_report_v256.csv')
ALIASES = {
    'capaccio': 'capaccio paestum',
    'tremosine': 'tremosine sul garda',
    'cornedo all isarco karneid': 'cornedo all isarco',
    'nova levante welschnofen': 'nova levante',
    'renon ritten': 'renon',
    'corvara in badia corvara': 'corvara in badia',
    'campo di trens freienfeld': 'campo di trens',
    'tubre taufers im muenstertal': 'tubre',
}

def norm(s: str) -> str:
    s = str(s or '').strip().lower().replace('\\', ' ')
    s = unicodedata.normalize('NFD', s)
    s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
    s = s.replace('’', "'").replace('`', "'")
    s = re.sub(r'\b(comune|provincia)\s+di\b', ' ', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def corrected_coordinate(value: str, axis: str) -> tuple[float, bool]:
    x = float(str(value).replace(',', '.'))
    lo, hi = ((35.0, 48.0) if axis == 'lat' else (5.0, 20.0))
    if lo <= x <= hi:
        return x, False
    for divisor in (10.0, 100.0, 1000.0, 10000.0):
        y = x / divisor
        if lo <= y <= hi:
            return y, True
    raise ValueError(f'invalid {axis}: {value}')

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))

def province_code(notes: str) -> str:
    m = re.search(r'provincia\s*:\s*([^;,.]+)', str(notes or ''), re.I)
    return m.group(1).strip().upper() if m else ''

def read_csv(path: Path):
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        return list(reader), list(reader.fieldnames or [])

def write_csv(path: Path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)

def load_comuni(path: Path):
    rows, _ = read_csv(path)
    items, repaired = [], []
    for row in rows:
        try:
            lat, lat_fixed = corrected_coordinate(row.get('lat',''), 'lat')
            lon, lon_fixed = corrected_coordinate(row.get('lon',''), 'lon')
        except Exception:
            continue
        name = str(row.get('comune') or '').strip()
        if not name:
            continue
        item = {
            'name': name, 'province': str(row.get('provincia') or '').strip(),
            'province_code': str(row.get('sigla_provincia') or '').strip().upper(),
            'region': str(row.get('regione') or '').strip(), 'lat': lat, 'lon': lon,
            'n_name': norm(name), 'n_region': norm(row.get('regione')),
        }
        items.append(item)
        if lat_fixed or lon_fixed:
            repaired.append({'comune': name, 'old_lat': row.get('lat'), 'old_lon': row.get('lon'),
                             'new_lat': f'{lat:.6f}', 'new_lon': f'{lon:.6f}'})
    if len(items) < 7000:
        raise SystemExit(f'Unexpected municipality reference size: {len(items)}')
    return items, repaired

def build_indices(items):
    by_nr, by_pc, by_n = defaultdict(list), defaultdict(list), defaultdict(list)
    for x in items:
        by_nr[(x['n_name'], x['n_region'])].append(x)
        by_pc[(x['n_name'], x['province_code'])].append(x)
        by_n[x['n_name']].append(x)
    return by_nr, by_pc, by_n

def match_municipality(row, indices):
    by_nr, by_pc, by_n = indices
    raw = norm(row.get('location'))
    nloc = ALIASES.get(raw, raw)
    nreg = norm(row.get('region'))
    pcode = province_code(row.get('notes'))
    for key, index, reason in [
        ((nloc, nreg), by_nr, 'municipality_region'),
        ((nloc, pcode), by_pc, 'municipality_province_code'),
    ]:
        if key[1] and len(index.get(key, [])) == 1:
            return index[key][0], reason, raw != nloc
    if len(by_n.get(nloc, [])) == 1:
        return by_n[nloc][0], 'municipality_unique', raw != nloc
    return None, ('ambiguous' if len(by_n.get(nloc, [])) > 1 else 'not_found'), raw != nloc

def clean_notes(notes: str, match, old_lat, old_lon, reason):
    text = str(notes or '')
    text = re.sub(r';?\s*geocoding level:\s*province', '', text, flags=re.I)
    text = re.sub(r';?\s*municipality centroid unavailable', '', text, flags=re.I)
    text = re.sub(r';?\s*coordinates set to province capital for map display\.?', '', text, flags=re.I)
    text = re.sub(r';?\s*geocoding correction v245:[^;]*;?', ';', text, flags=re.I)
    text = re.sub(r';{2,}', ';', text).strip(' ;')
    suffix = (f'geocoding level: municipality; municipality centroid: {match["name"]} '
              f'({match["province_code"]}); geocoding correction v256; previous coordinates '
              f'{old_lat},{old_lon}; match={reason}.')
    return f'{text}; {suffix}' if text else suffix

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--events', type=Path, default=DEFAULT_EVENTS)
    ap.add_argument('--comuni', type=Path, default=DEFAULT_COMUNI)
    ap.add_argument('--report', type=Path, default=DEFAULT_REPORT)
    ap.add_argument('--output', type=Path, default=None)
    ap.add_argument('--in-place', action='store_true')
    args = ap.parse_args()
    if args.in_place and args.output:
        raise SystemExit('Use either --in-place or --output')
    output = args.events if args.in_place else (args.output or args.events.with_name(args.events.stem + '_geocoded_v256.csv'))
    rows, fields = read_csv(args.events)
    items, repaired_reference = load_comuni(args.comuni)
    indices = build_indices(items)
    report, unmatched = [], []
    changed = 0
    if args.in_place:
        backup = args.events.with_suffix(args.events.suffix + '.before_v256.bak')
        shutil.copy2(args.events, backup)
    for row in rows:
        match, reason, alias_used = match_municipality(row, indices)
        old_lat, old_lon = row.get('lat',''), row.get('lon','')
        if not match:
            unmatched.append({'external_id': row.get('external_id',''), 'location': row.get('location',''),
                              'region': row.get('region',''), 'province_code': province_code(row.get('notes')),
                              'reason': reason})
            continue
        new_lat, new_lon = f'{match["lat"]:.6f}', f'{match["lon"]:.6f}'
        try: shift = haversine_km(float(old_lat), float(old_lon), match['lat'], match['lon'])
        except Exception: shift = None
        is_changed = str(old_lat) != new_lat or str(old_lon) != new_lon
        if is_changed:
            changed += 1
            row['lat'], row['lon'] = new_lat, new_lon
            row['notes'] = clean_notes(row.get('notes'), match, old_lat, old_lon, reason)
        report.append({
            'external_id': row.get('external_id',''), 'location': row.get('location',''),
            'region': row.get('region',''), 'province': match['province'],
            'province_code': match['province_code'], 'match': reason,
            'alias_used': str(alias_used).lower(), 'old_lat': old_lat, 'old_lon': old_lon,
            'new_lat': new_lat, 'new_lon': new_lon,
            'distance_shift_km': '' if shift is None else f'{shift:.3f}',
            'changed': str(is_changed).lower(),
        })
    write_csv(output, rows, fields)
    report_fields = ['external_id','location','region','province','province_code','match','alias_used',
                     'old_lat','old_lon','new_lat','new_lon','distance_shift_km','changed']
    write_csv(args.report, report, report_fields)
    unmatched_path = args.report.with_name(args.report.stem + '_unmatched.csv')
    write_csv(unmatched_path, unmatched, ['external_id','location','region','province_code','reason'])
    result = {
        'status':'success','generated_at':datetime.now(timezone.utc).isoformat(),
        'events_rows':len(rows),'matched_rows':len(report),'changed_rows':changed,
        'unmatched_rows':len(unmatched),'reference_rows':len(items),
        'reference_coordinates_repaired':len(repaired_reference),
        'output':str(output),'report':str(args.report),'unmatched_report':str(unmatched_path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
