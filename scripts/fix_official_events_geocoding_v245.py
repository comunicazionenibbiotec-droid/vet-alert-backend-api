#!/usr/bin/env python3
from __future__ import annotations
import csv, json, re, unicodedata
from pathlib import Path
from datetime import datetime

OFFICIAL_FILES = [
    Path('data/official_sources/adis_events.csv'),
    Path('data/official_sources/wahis_events.csv'),
    Path('data/official_sources/izs_benv_events.csv'),
]
GEOCODING = Path('data/official_sources/geocoding_it.csv')
COMUNI = Path('data/reference/italia_comuni_centroids.csv')
REPORT = Path('data/official_sources/geocoding_fix_report_v245.csv')

PROVINCE_CODES = {
    'AG':'Agrigento','AL':'Alessandria','AN':'Ancona','AO':'Aosta','AR':'Arezzo','AP':'Ascoli Piceno','AT':'Asti','AV':'Avellino',
    'BA':'Bari','BT':'Barletta-Andria-Trani','BL':'Belluno','BN':'Benevento','BG':'Bergamo','BI':'Biella','BO':'Bologna','BZ':'Bolzano','BS':'Brescia','BR':'Brindisi',
    'CA':'Cagliari','CL':'Caltanissetta','CB':'Campobasso','CI':'Sud Sardegna','CE':'Caserta','CT':'Catania','CZ':'Catanzaro','CH':'Chieti','CO':'Como','CS':'Cosenza','CR':'Cremona','KR':'Crotone','CN':'Cuneo',
    'EN':'Enna','FM':'Fermo','FE':'Ferrara','FI':'Firenze','FG':'Foggia','FC':'Forlì-Cesena','FR':'Frosinone',
    'GE':'Genova','GO':'Gorizia','GR':'Grosseto',
    'IM':'Imperia','IS':'Isernia',
    'SP':'La Spezia','AQ':"L'Aquila",'LT':'Latina','LE':'Lecce','LC':'Lecco','LI':'Livorno','LO':'Lodi','LU':'Lucca',
    'MC':'Macerata','MN':'Mantova','MS':'Massa-Carrara','MT':'Matera','ME':'Messina','MI':'Milano','MO':'Modena','MB':'Monza e Brianza',
    'NA':'Napoli','NO':'Novara','NU':'Nuoro',
    'OR':'Oristano',
    'PD':'Padova','PA':'Palermo','PR':'Parma','PV':'Pavia','PG':'Perugia','PU':'Pesaro e Urbino','PE':'Pescara','PC':'Piacenza','PI':'Pisa','PT':'Pistoia','PN':'Pordenone','PZ':'Potenza','PO':'Prato',
    'RG':'Ragusa','RA':'Ravenna','RC':'Reggio Calabria','RE':'Reggio Emilia','RI':'Rieti','RN':'Rimini','RM':'Roma','RO':'Rovigo',
    'SA':'Salerno','SS':'Sassari','SV':'Savona','SI':'Siena','SR':'Siracusa','SO':'Sondrio','SU':'Sud Sardegna',
    'TA':'Taranto','TE':'Teramo','TR':'Terni','TO':'Torino','TP':'Trapani','TN':'Trento','TV':'Treviso','TS':'Trieste',
    'UD':'Udine',
    'VA':'Varese','VE':'Venezia','VB':'Verbano-Cusio-Ossola','VC':'Vercelli','VR':'Verona','VV':'Vibo Valentia','VI':'Vicenza','VT':'Viterbo'
}

def norm(s: str) -> str:
    s = str(s or '').strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
    s = s.replace('’', "'").replace('`', "'")
    s = re.sub(r"\bcomune\s+di\b", ' ', s)
    s = re.sub(r"\bprovincia\s+di\b", ' ', s)
    s = re.sub(r"[^a-z0-9]+", ' ', s)
    return re.sub(r"\s+", ' ', s).strip()

def clean_location(s: str) -> str:
    s = str(s or '').strip()
    s = re.sub(r'^Area\s+', '', s, flags=re.I).strip()
    return s

def pick(row, names):
    lower = {str(k).strip().lower(): k for k in row.keys()}
    for name in names:
        key = lower.get(name.lower())
        if key is not None and str(row.get(key) or '').strip():
            return row.get(key)
    return ''

def load_comuni():
    if not COMUNI.exists():
        raise SystemExit(f'{COMUNI} not found')
    items = []
    with COMUNI.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = pick(row, ['comune','nome_comune','denominazione_ita','denominazione','municipality','location','name'])
            region = pick(row, ['regione','region','nome_regione'])
            province = pick(row, ['provincia','province','nome_provincia','denominazione_provincia'])
            pcode = pick(row, ['sigla','sigla_provincia','province_code','provincia_sigla','codice_provincia'])
            lat = pick(row, ['lat','latitude','centroid_lat','y'])
            lon = pick(row, ['lon','lng','longitude','centroid_lon','x'])
            try:
                latf, lonf = float(str(lat).replace(',', '.')), float(str(lon).replace(',', '.'))
            except Exception:
                continue
            if not name:
                continue
            pcode = str(pcode or '').strip().upper()
            if pcode in PROVINCE_CODES and not province:
                province = PROVINCE_CODES[pcode]
            items.append({
                'name': str(name).strip(), 'region': str(region or '').strip(), 'province': str(province or '').strip(),
                'province_code': pcode, 'lat': latf, 'lon': lonf,
                'n_name': norm(name), 'n_region': norm(region), 'n_province': norm(province)
            })
    if len(items) < 1000:
        raise SystemExit(f'{COMUNI} seems too small or has unexpected columns; parsed {len(items)} rows')
    return items

def build_indices(items):
    by_name_region = {}
    by_name_province = {}
    by_name_code = {}
    by_name = {}
    for x in items:
        by_name_region.setdefault((x['n_name'], x['n_region']), []).append(x)
        by_name_province.setdefault((x['n_name'], x['n_province']), []).append(x)
        if x['province_code']:
            by_name_code.setdefault((x['n_name'], x['province_code']), []).append(x)
        by_name.setdefault(x['n_name'], []).append(x)
    return by_name_region, by_name_province, by_name_code, by_name

def extract_province_from_notes(notes: str):
    txt = str(notes or '')
    m = re.search(r'provincia\s*:\s*([^;,.]+)', txt, flags=re.I)
    if not m:
        return '', ''
    raw = m.group(1).strip()
    code = raw.upper()
    if code in PROVINCE_CODES:
        return PROVINCE_CODES[code], code
    return raw, ''

def best_match(location, region, notes, indices):
    by_name_region, by_name_province, by_name_code, by_name = indices
    loc = clean_location(location)
    nloc = norm(loc)
    nreg = norm(region)
    prov_name, prov_code = extract_province_from_notes(notes)
    nprov = norm(prov_name)
    if not nloc:
        return None, 'missing_location'
    candidates = []
    if nreg:
        candidates = by_name_region.get((nloc, nreg), [])
        if len(candidates) == 1: return candidates[0], 'municipality_region'
    if prov_code:
        candidates = by_name_code.get((nloc, prov_code), [])
        if len(candidates) == 1: return candidates[0], 'municipality_province_code'
    if nprov:
        candidates = by_name_province.get((nloc, nprov), [])
        if len(candidates) == 1: return candidates[0], 'municipality_province'
    candidates = by_name.get(nloc, [])
    if len(candidates) == 1: return candidates[0], 'municipality_unique'
    if len(candidates) > 1:
        return None, 'ambiguous_municipality'
    return None, 'not_found'

def read_csv(path):
    if not path.exists(): return [], []
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f)
        return list(r), list(r.fieldnames or [])

def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)

def update_geocoding_cache(items):
    rows, fields = read_csv(GEOCODING)
    if not fields:
        fields = ['location','region','lat','lon']
    for field in ['location','region','lat','lon']:
        if field not in fields: fields.append(field)
    seen = {(norm(r.get('location')), norm(r.get('region'))) for r in rows}
    added = 0
    for x in items:
        key = (x['n_name'], x['n_region'])
        if key in seen: continue
        rows.append({'location': x['name'], 'region': x['region'], 'lat': f"{x['lat']:.6f}", 'lon': f"{x['lon']:.6f}"})
        seen.add(key); added += 1
    write_csv(GEOCODING, rows, fields)
    return added, len(rows)

def fix_file(path, indices):
    rows, fields = read_csv(path)
    if not rows: return {'file': str(path), 'rows': 0, 'changed': 0, 'skipped': 0}
    changed = skipped = 0
    details = []
    for row in rows:
        match, reason = best_match(row.get('location'), row.get('region'), row.get('notes'), indices)
        old_lat, old_lon = row.get('lat'), row.get('lon')
        if match:
            new_lat, new_lon = f"{match['lat']:.6f}", f"{match['lon']:.6f}"
            if str(old_lat) != new_lat or str(old_lon) != new_lon:
                row['lat'], row['lon'] = new_lat, new_lon
                changed += 1
                note = str(row.get('notes') or '')
                correction = f" geocoding correction v245: municipality centroid matched to {match['name']} ({match['province']}); previous coordinates {old_lat},{old_lon}; match={reason}."
                if 'geocoding correction v245' not in note:
                    row['notes'] = (note + ';' + correction).strip(';')
            details.append({'file': path.name, 'external_id': row.get('external_id',''), 'location': row.get('location',''), 'region': row.get('region',''), 'province': match['province'], 'match': reason, 'old_lat': old_lat, 'old_lon': old_lon, 'new_lat': row.get('lat'), 'new_lon': row.get('lon'), 'changed': str(str(old_lat) != str(row.get('lat')) or str(old_lon) != str(row.get('lon'))).lower()})
        else:
            skipped += 1
            details.append({'file': path.name, 'external_id': row.get('external_id',''), 'location': row.get('location',''), 'region': row.get('region',''), 'province': extract_province_from_notes(row.get('notes'))[0], 'match': reason, 'old_lat': old_lat, 'old_lon': old_lon, 'new_lat': old_lat, 'new_lon': old_lon, 'changed': 'false'})
    write_csv(path, rows, fields)
    return {'file': str(path), 'rows': len(rows), 'changed': changed, 'skipped': skipped, 'details': details}

def main():
    items = load_comuni()
    indices = build_indices(items)
    report_rows = []
    results = []
    for path in OFFICIAL_FILES:
        res = fix_file(path, indices)
        report_rows.extend(res.pop('details', []))
        results.append(res)
    geo_added, geo_total = update_geocoding_cache(items)
    report_fields = ['file','external_id','location','region','province','match','old_lat','old_lon','new_lat','new_lon','changed']
    write_csv(REPORT, report_rows, report_fields)
    print(json.dumps({
        'status': 'success',
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'reference_comuni_rows': len(items),
        'geocoding_cache_added': geo_added,
        'geocoding_cache_total': geo_total,
        'official_files': results,
        'report': str(REPORT),
        'next_step': 'Run /sync/adis/run, /sync/wahis/run, /sync/izs-benv/run to reload corrected CSV coordinates into SQLite.'
    }, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
