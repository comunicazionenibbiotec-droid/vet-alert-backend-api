#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, os, time, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone

CSV_PATH = Path(os.getenv('TERRITORIAL_LAYERS_CSV_PATH', 'data/territorial_layers/territorial_layers.csv'))
GBIF_OCCURRENCE_API = os.getenv('GBIF_OCCURRENCE_API', 'https://api.gbif.org/v1/occurrence/search')
GBIF_SPECIES_MATCH_API = os.getenv('GBIF_SPECIES_MATCH_API', 'https://api.gbif.org/v1/species/match')
USER_AGENT = os.getenv('GBIF_USER_AGENT', 'vetector-piemonte-liguria-genus-importer/235')
PAGE_SIZE = int(os.getenv('GENUS_IMPORT_PAGE_SIZE', '300'))
MAX_PER_GENUS_PROVINCE = int(os.getenv('GENUS_IMPORT_MAX_PER_GENUS_PROVINCE', '1500'))
MAX_PAGES_PER_GENUS_PROVINCE = int(os.getenv('GENUS_IMPORT_MAX_PAGES_PER_GENUS_PROVINCE', '5'))
MAX_UNCERTAINTY_M = float(os.getenv('GENUS_IMPORT_MAX_UNCERTAINTY_M', '10000'))
SLEEP_SECONDS = float(os.getenv('GENUS_IMPORT_SLEEP_SECONDS', '0.12'))

FIELDNAMES = [
    'id','external_id','category','ui_group','ui_group_label','subcategory','source','display_source',
    'label','scientific_name','data_type','count','count_label','case_count','period_start','period_end',
    'country','region','province','municipality','location','lat','lon','radius_km','display_radius_km',
    'localization_precision','aggregation_level','precision','color','url_source','notes',
    'coordinate_uncertainty_m','license','source_dataset','updated_at'
]

PROVINCES = {
    'Piemonte': {
        'Torino': (6.75, 44.55, 8.35, 45.65),
        'Cuneo': (6.55, 43.85, 8.45, 44.95),
        'Asti': (7.85, 44.45, 8.65, 45.15),
        'Alessandria': (8.20, 44.35, 9.30, 45.25),
        'Vercelli': (7.75, 45.05, 8.65, 45.95),
        'Novara': (8.25, 45.25, 8.95, 45.95),
        'Biella': (7.75, 45.35, 8.35, 46.05),
        'Verbano-Cusio-Ossola': (7.80, 45.75, 8.75, 46.55)
    },
    'Liguria': {
        'Imperia': (7.45, 43.75, 8.20, 44.35),
        'Savona': (8.05, 43.90, 8.65, 44.65),
        'Genova': (8.55, 43.95, 9.35, 44.70),
        'La Spezia': (9.55, 43.95, 10.10, 44.40)
    }
}

GENERA = {
    'sand_flies': ['Phlebotomus', 'Sergentomyia'],
    'ticks': ['Ixodes', 'Dermacentor', 'Rhipicephalus', 'Hyalomma', 'Ornithodoros', 'Haemaphysalis'],
    'mosquitoes_other_vectors': ['Aedes', 'Culex', 'Anopheles', 'Culiseta', 'Coquillettidia', 'Culicoides', 'Simulium']
}
LABELS = {'sand_flies': 'Flebotomi', 'ticks': 'Zecche', 'mosquitoes_other_vectors': 'Zanzare / altri vettori'}
COLORS = {'sand_flies': '#F26522', 'ticks': '#7C3AED', 'mosquitoes_other_vectors': '#2563EB'}
TAXON_CACHE: dict[str, str] = {}

def stable_id(*parts):
    return hashlib.sha1('|'.join(str(p or '').strip().lower() for p in parts).encode('utf-8')).hexdigest()[:32]

def bbox_wkt(bbox):
    min_lon, min_lat, max_lon, max_lat = bbox
    return f'POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},{max_lon} {max_lat},{min_lon} {max_lat},{min_lon} {min_lat}))'

def get_json(url, params):
    req = urllib.request.Request(url + '?' + urllib.parse.urlencode(params), headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode('utf-8'))

def taxon_key_for_genus(genus):
    if genus in TAXON_CACHE:
        return TAXON_CACHE[genus]
    try:
        payload = get_json(GBIF_SPECIES_MATCH_API, {'name': genus, 'rank': 'GENUS'})
        key = payload.get('usageKey') or payload.get('acceptedUsageKey') or ''
        TAXON_CACHE[genus] = str(key) if key else ''
        return TAXON_CACHE[genus]
    except Exception:
        TAXON_CACHE[genus] = ''
        return ''

def ok_coords(item):
    if item.get('decimalLatitude') is None or item.get('decimalLongitude') is None:
        return False
    try:
        float(item.get('decimalLatitude'))
        float(item.get('decimalLongitude'))
    except Exception:
        return False
    unc = item.get('coordinateUncertaintyInMeters')
    if unc in (None, ''):
        return True
    try:
        return float(unc) <= MAX_UNCERTAINTY_M
    except Exception:
        return True

def row_from_item(item, group, region, province, genus):
    if not ok_coords(item):
        return None
    lat = float(item.get('decimalLatitude'))
    lon = float(item.get('decimalLongitude'))
    scientific = item.get('scientificName') or item.get('acceptedScientificName') or item.get('verbatimScientificName') or genus
    gbif_key = item.get('key') or item.get('gbifID') or item.get('occurrenceID')
    event_date = str(item.get('eventDate') or '')[:10]
    year = item.get('year')
    period = event_date or (str(year) if year else '')
    unc = item.get('coordinateUncertaintyInMeters')
    locality = item.get('locality') or item.get('municipality') or item.get('county') or province
    county = item.get('county') or province
    rid = 'gbif-genus-piemlig-' + stable_id(gbif_key, scientific, lat, lon, item.get('datasetKey'), province)
    note = 'Occorrenza reale georeferenziata importata da GBIF con ricerca per genere e provincia target in Piemonte/Liguria. Dato territoriale di presenza vettoriale, non diagnosi clinica.'
    if unc not in (None, ''):
        note += f' Coordinate uncertainty: {unc} m.'
    else:
        note += ' Coordinate uncertainty not declared by source.'
    note += f' Provincia target di ricerca: {province}. Genere ricercato: {genus}.'
    return {
        'id': rid,
        'external_id': str(gbif_key or rid),
        'category': 'vectors',
        'ui_group': group,
        'ui_group_label': LABELS[group],
        'subcategory': group,
        'source': 'GBIF genus province import',
        'display_source': 'GBIF genus province import',
        'label': scientific,
        'scientific_name': scientific,
        'data_type': 'real_vector_occurrence_genus_province_piem_lig',
        'count': '1',
        'count_label': 'record di occorrenza reale',
        'case_count': '1',
        'period_start': period,
        'period_end': period,
        'country': item.get('country') or 'Italy',
        'region': region,
        'province': county,
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
        'url_source': ('https://www.gbif.org/occurrence/' + str(gbif_key)) if gbif_key else 'https://www.gbif.org/',
        'notes': note,
        'coordinate_uncertainty_m': '' if unc is None else str(unc),
        'license': item.get('license') or '',
        'source_dataset': item.get('datasetName') or item.get('datasetKey') or '',
        'updated_at': datetime.now(timezone.utc).isoformat()
    }

def query_genus_province(genus, group, region, province, bbox):
    rows = []
    offset = 0
    pages = 0
    fetched = 0
    taxon_key = taxon_key_for_genus(genus)
    base = {
        'country': 'IT',
        'hasCoordinate': 'true',
        'hasGeospatialIssue': 'false',
        'occurrenceStatus': 'PRESENT',
        'geometry': bbox_wkt(bbox)
    }
    if taxon_key:
        base['taxonKey'] = taxon_key
    else:
        base['scientificName'] = genus
    while fetched < MAX_PER_GENUS_PROVINCE and pages < MAX_PAGES_PER_GENUS_PROVINCE:
        limit = min(PAGE_SIZE, MAX_PER_GENUS_PROVINCE - fetched)
        payload = get_json(GBIF_OCCURRENCE_API, dict(base, limit=limit, offset=offset))
        batch = payload.get('results') or []
        if not batch:
            break
        for item in batch:
            row = row_from_item(item, group, region, province, genus)
            if row:
                rows.append(row)
        fetched += len(batch)
        offset += len(batch)
        pages += 1
        if payload.get('endOfRecords'):
            break
        time.sleep(SLEEP_SECONDS)
    return rows, fetched, taxon_key

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
    for region, provinces in PROVINCES.items():
        for province, bbox in provinces.items():
            for group, genera in GENERA.items():
                for genus in genera:
                    key = f'{region} | {province} | {group} | {genus}'
                    try:
                        rows, fetched, taxon_key = query_genus_province(genus, group, region, province, bbox)
                        detail[key] = {'candidate_rows': len(rows), 'gbif_records_read': fetched, 'taxon_key': taxon_key}
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
    group_counts = {}
    province_counts = {}
    for row in new_rows:
        group_counts[row.get('ui_group','missing')] = group_counts.get(row.get('ui_group','missing'), 0) + 1
        province_counts[row.get('province','missing')] = province_counts.get(row.get('province','missing'), 0) + 1
    print(json.dumps({
        'status': 'success',
        'scope': 'Piemonte and Liguria, province boxes and genus search',
        'csv_path': str(CSV_PATH),
        'candidate_rows': len(new_rows),
        'inserted': inserted,
        'updated': updated,
        'total_rows': len(existing),
        'ui_group_counts_new_rows': group_counts,
        'province_counts_new_rows': province_counts,
        'detail': detail
    }, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
