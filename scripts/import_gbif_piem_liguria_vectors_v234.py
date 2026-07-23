#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, math, os, time, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone

CSV_PATH = Path(os.getenv('TERRITORIAL_LAYERS_CSV_PATH', 'data/territorial_layers/territorial_layers.csv'))
GBIF_API = os.getenv('GBIF_OCCURRENCE_API', 'https://api.gbif.org/v1/occurrence/search')
USER_AGENT = os.getenv('GBIF_USER_AGENT', 'vetector-piemonte-liguria-importer/234')
PAGE_SIZE = int(os.getenv('REGION_IMPORT_PAGE_SIZE', '300'))
MAX_PER_SPECIES = int(os.getenv('REGION_IMPORT_MAX_PER_SPECIES', '3000'))
MAX_PAGES_PER_SPECIES = int(os.getenv('REGION_IMPORT_MAX_PAGES_PER_SPECIES', '12'))
MAX_UNCERTAINTY_M = float(os.getenv('REGION_IMPORT_MAX_UNCERTAINTY_M', '10000'))
SLEEP_SECONDS = float(os.getenv('REGION_IMPORT_SLEEP_SECONDS', '0.15'))

FIELDNAMES = [
    'id','external_id','category','ui_group','ui_group_label','subcategory','source','display_source',
    'label','scientific_name','data_type','count','count_label','case_count','period_start','period_end',
    'country','region','province','municipality','location','lat','lon','radius_km','display_radius_km',
    'localization_precision','aggregation_level','precision','color','url_source','notes',
    'coordinate_uncertainty_m','license','source_dataset','updated_at'
]

REGIONS = {
    'Piemonte': {
        'bbox': (6.55, 43.85, 9.35, 46.55),
        'provinces': ['Torino','Cuneo','Asti','Alessandria','Vercelli','Novara','Biella','Verbano-Cusio-Ossola']
    },
    'Liguria': {
        'bbox': (7.45, 43.65, 10.10, 44.75),
        'provinces': ['Imperia','Savona','Genova','La Spezia']
    }
}

# Species chosen to cover flebotomi, zecche, zanzare and other animal-health vectors.
SPECIES = {
    'sand_flies': [
        'Phlebotomus perniciosus','Phlebotomus perfiliewi','Phlebotomus neglectus',
        'Phlebotomus mascitii','Phlebotomus ariasi'
    ],
    'ticks': [
        'Ixodes ricinus','Dermacentor reticulatus','Rhipicephalus sanguineus',
        'Hyalomma marginatum','Hyalomma lusitanicum','Ornithodoros erraticus'
    ],
    'mosquitoes_other_vectors': [
        'Aedes albopictus','Aedes japonicus','Aedes koreicus','Aedes aegypti',
        'Culex pipiens','Culex modestus','Anopheles maculipennis','Culicoides imicola','Culicoides obsoletus'
    ]
}
LABELS = {'sand_flies':'Flebotomi','ticks':'Zecche','mosquitoes_other_vectors':'Zanzare / altri vettori'}
COLORS = {'sand_flies':'#F26522','ticks':'#7C3AED','mosquitoes_other_vectors':'#2563EB'}

def stable_id(*parts):
    return hashlib.sha1('|'.join(str(p or '').strip().lower() for p in parts).encode('utf-8')).hexdigest()[:32]

def bbox_wkt(bbox):
    min_lon, min_lat, max_lon, max_lat = bbox
    return f'POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},{max_lon} {max_lat},{min_lon} {max_lat},{min_lon} {min_lat}))'

def fetch_json(params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f'{GBIF_API}?{qs}', headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode('utf-8'))

def ok_coords(item):
    if item.get('decimalLatitude') is None or item.get('decimalLongitude') is None:
        return False
    try:
        float(item.get('decimalLatitude')); float(item.get('decimalLongitude'))
    except Exception:
        return False
    unc = item.get('coordinateUncertaintyInMeters')
    if unc in (None, ''):
        return True
    try:
        return float(unc) <= MAX_UNCERTAINTY_M
    except Exception:
        return True

def region_from_point(lat, lon):
    for region, info in REGIONS.items():
        min_lon, min_lat, max_lon, max_lat = info['bbox']
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return region
    return ''

def row_from_item(item, group, region_name, source_label='GBIF occurrence'):
    if not ok_coords(item):
        return None
    lat = float(item.get('decimalLatitude'))
    lon = float(item.get('decimalLongitude'))
    region = region_from_point(lat, lon) or region_name
    scientific = item.get('scientificName') or item.get('acceptedScientificName') or item.get('verbatimScientificName') or 'Vettore'
    key = item.get('key') or item.get('gbifID') or item.get('occurrenceID')
    event_date = str(item.get('eventDate') or '')[:10]
    year = item.get('year')
    period = event_date or (str(year) if year else '')
    unc = item.get('coordinateUncertaintyInMeters')
    locality = item.get('locality') or item.get('municipality') or item.get('county') or item.get('stateProvince') or ''
    province = item.get('county') or item.get('stateProvince') or ''
    rid = 'gbif-piemlig-' + stable_id(key, scientific, lat, lon, item.get('datasetKey'))
    note = 'Occorrenza reale georeferenziata importata da GBIF per Piemonte/Liguria. Dato territoriale di presenza vettoriale, non diagnosi clinica.'
    if unc not in (None, ''):
        note += f' Coordinate uncertainty: {unc} m.'
    else:
        note += ' Coordinate uncertainty not declared by source.'
    return {
        'id': rid,
        'external_id': str(key or rid),
        'category': 'vectors',
        'ui_group': group,
        'ui_group_label': LABELS[group],
        'subcategory': group,
        'source': source_label,
        'display_source': source_label,
        'label': scientific,
        'scientific_name': scientific,
        'data_type': 'real_vector_occurrence_piem_lig',
        'count': '1',
        'count_label': 'record di occorrenza reale',
        'case_count': '1',
        'period_start': period,
        'period_end': period,
        'country': item.get('country') or 'Italy',
        'region': region,
        'province': province,
        'municipality': item.get('municipality') or '',
        'location': locality,
        'lat': f'{lat:.7f}',
        'lon': f'{lon:.7f}',
        'radius_km': '10',
        'display_radius_km': '10',
        'localization_precision': 'coordinate / puntuale',
        'aggregation_level': 'occurrence_point',
        'precision': 'coordinate / puntuale',
        'color': COLORS[group],
        'url_source': ('https://www.gbif.org/occurrence/' + str(key)) if key else 'https://www.gbif.org/',
        'notes': note,
        'coordinate_uncertainty_m': '' if unc is None else str(unc),
        'license': item.get('license') or '',
        'source_dataset': item.get('datasetName') or item.get('datasetKey') or '',
        'updated_at': datetime.now(timezone.utc).isoformat()
    }

def query_species_region(species, group, region_name, bbox):
    rows = []
    offset = 0
    pages = 0
    fetched = 0
    params_base = {
        'country': 'IT',
        'hasCoordinate': 'true',
        'hasGeospatialIssue': 'false',
        'occurrenceStatus': 'PRESENT',
        'scientificName': species,
        'geometry': bbox_wkt(bbox)
    }
    while fetched < MAX_PER_SPECIES and pages < MAX_PAGES_PER_SPECIES:
        limit = min(PAGE_SIZE, MAX_PER_SPECIES - fetched)
        payload = fetch_json(dict(params_base, limit=limit, offset=offset))
        batch = payload.get('results') or []
        if not batch:
            break
        for item in batch:
            row = row_from_item(item, group, region_name)
            if row:
                rows.append(row)
        fetched += len(batch)
        offset += len(batch)
        pages += 1
        if payload.get('endOfRecords'):
            break
        time.sleep(SLEEP_SECONDS)
    return rows, fetched

def read_csv(path):
    if not path.exists():
        return [], FIELDNAMES[:]
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    for f in FIELDNAMES:
        if f not in fields:
            fields.append(f)
    return rows, fields

def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

def main():
    new_rows = []
    detail = {}
    for region_name, info in REGIONS.items():
        for group, species_list in SPECIES.items():
            for species in species_list:
                key = f'{region_name} | {group} | {species}'
                try:
                    rows, fetched = query_species_region(species, group, region_name, info['bbox'])
                    detail[key] = {'candidate_rows': len(rows), 'gbif_records_read': fetched}
                    new_rows.extend(rows)
                except Exception as e:
                    detail[key] = {'error': str(e)}
    existing, fields = read_csv(CSV_PATH)
    by_id = {r.get('id'): r for r in existing if r.get('id')}
    inserted = 0
    updated = 0
    for row in new_rows:
        rid = row.get('id')
        if rid in by_id:
            by_id[rid].update(row)
            updated += 1
        else:
            existing.append(row)
            by_id[rid] = row
            inserted += 1
    write_csv(CSV_PATH, existing, fields)
    counts = {}
    for row in new_rows:
        counts[row.get('ui_group','missing')] = counts.get(row.get('ui_group','missing'), 0) + 1
    print(json.dumps({
        'status': 'success',
        'scope': 'Piemonte and Liguria',
        'csv_path': str(CSV_PATH),
        'candidate_rows': len(new_rows),
        'inserted': inserted,
        'updated': updated,
        'total_rows': len(existing),
        'ui_group_counts_new_rows': counts,
        'detail': detail
    }, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
