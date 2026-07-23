#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, math, os, time, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone

CSV_PATH = Path(os.getenv('TERRITORIAL_LAYERS_CSV_PATH', 'data/territorial_layers/territorial_layers.csv'))
CITIES_PATH = Path(os.getenv('SOURCE_CITIES_PATH', 'data/source_cities.json'))
GBIF_OCCURRENCE_API = os.getenv('GBIF_OCCURRENCE_API', 'https://api.gbif.org/v1/occurrence/search')
GBIF_SPECIES_MATCH_API = os.getenv('GBIF_SPECIES_MATCH_API', 'https://api.gbif.org/v1/species/match')
USER_AGENT = os.getenv('GBIF_USER_AGENT', 'vetector-real-city-importer/240; vet.ector')
RADIUS_KM = float(os.getenv('REAL_CITY_IMPORT_RADIUS_KM', '35'))
PAGE_SIZE = int(os.getenv('REAL_CITY_IMPORT_PAGE_SIZE', '300'))
MAX_PER_GENUS_CITY = int(os.getenv('REAL_CITY_IMPORT_MAX_PER_GENUS_CITY', '900'))
MAX_PAGES_PER_GENUS_CITY = int(os.getenv('REAL_CITY_IMPORT_MAX_PAGES_PER_GENUS_CITY', '3'))
MAX_UNCERTAINTY_M = float(os.getenv('REAL_CITY_IMPORT_MAX_UNCERTAINTY_M', '10000'))
SLEEP_SECONDS = float(os.getenv('REAL_CITY_IMPORT_SLEEP_SECONDS', '0.10'))
INCLUDE_ONLY_PILOT_AREAS = os.getenv('REAL_CITY_IMPORT_ONLY_PILOT_AREAS', 'true').lower() == 'true'

FIELDNAMES = [
    'id','external_id','category','ui_group','ui_group_label','subcategory','source','display_source','label','scientific_name',
    'data_type','count','count_label','case_count','period_start','period_end','country','region','province','municipality','location',
    'lat','lon','radius_km','display_radius_km','localization_precision','aggregation_level','precision','color','url_source','notes',
    'coordinate_uncertainty_m','license','source_dataset','updated_at'
]

GENERA = {
    'sand_flies': ['Phlebotomus'],
    'ticks': ['Ixodes','Dermacentor','Rhipicephalus','Hyalomma','Haemaphysalis','Ornithodoros'],
    'mosquitoes_other_vectors': ['Aedes','Culex','Anopheles','Culiseta','Coquillettidia','Culicoides','Simulium']
}
LABELS = {'sand_flies':'Flebotomi','ticks':'Zecche','mosquitoes_other_vectors':'Zanzare / altri vettori'}
COLORS = {'sand_flies':'#F26522','ticks':'#7C3AED','mosquitoes_other_vectors':'#2563EB'}
TAXON_CACHE = {}


def stable_id(*parts):
    return hashlib.sha1('|'.join(str(p or '').strip().lower() for p in parts).encode('utf-8')).hexdigest()[:32]


def bbox_for_point(lat, lon, radius_km):
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def bbox_wkt(bbox):
    min_lon, min_lat, max_lon, max_lat = bbox
    return f'POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},{max_lon} {max_lat},{min_lon} {max_lat},{min_lon} {min_lat}))'


def haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 2 * radius * math.asin(math.sqrt(a))


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


def valid_coords(item):
    try:
        lat = float(item.get('decimalLatitude'))
        lon = float(item.get('decimalLongitude'))
    except Exception:
        return False
    unc = item.get('coordinateUncertaintyInMeters')
    if unc in (None, ''):
        return True
    try:
        return float(unc) <= MAX_UNCERTAINTY_M
    except Exception:
        return True


def row_from_item(item, group, city, genus, distance_km):
    if not valid_coords(item):
        return None
    lat = float(item.get('decimalLatitude'))
    lon = float(item.get('decimalLongitude'))
    scientific = item.get('scientificName') or item.get('acceptedScientificName') or item.get('verbatimScientificName') or genus
    gbif_key = item.get('key') or item.get('gbifID') or item.get('occurrenceID')
    event_date = str(item.get('eventDate') or '')[:10]
    year = item.get('year')
    period = event_date or (str(year) if year else '')
    unc = item.get('coordinateUncertaintyInMeters')
    dataset = item.get('datasetName') or item.get('datasetKey') or ''
    source = 'GBIF real occurrence'
    if str(item.get('datasetKey','')) == '1fef1ead-3d02-495e-8ff1-6aeb01123408' or 'Mosquito Alert' in str(dataset):
        source = 'Mosquito Alert / GBIF validated occurrence'
    rid = 'real-city-gbif-' + stable_id(gbif_key, scientific, lat, lon, item.get('datasetKey'))
    note = (
        'Occorrenza reale georeferenziata importata da GBIF usando città operative visibili e nascoste come centri di ricerca. '
        'Dato reale di presenza vettoriale. Non è diagnosi clinica e non è focolaio. '
        f'Città di ricerca più vicina: {city.get("name")}; distanza dal centro: {distance_km:.1f} km; genere ricercato: {genus}.'
    )
    if unc not in (None, ''):
        note += f' Coordinate uncertainty: {unc} m.'
    return {
        'id': rid,
        'external_id': str(gbif_key or rid),
        'category': 'vectors',
        'ui_group': group,
        'ui_group_label': LABELS[group],
        'subcategory': group,
        'source': source,
        'display_source': source,
        'label': scientific,
        'scientific_name': scientific,
        'data_type': 'real_vector_occurrence_city_search',
        'count': '1',
        'count_label': 'record reale di occorrenza',
        'case_count': '1',
        'period_start': period,
        'period_end': period,
        'country': item.get('country') or 'Italy',
        'region': city.get('region',''),
        'province': item.get('county') or city.get('province',''),
        'municipality': item.get('municipality') or '',
        'location': item.get('locality') or item.get('municipality') or city.get('name',''),
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
        'source_dataset': dataset,
        'updated_at': datetime.now(timezone.utc).isoformat()
    }


def load_cities():
    all_cities = json.loads(CITIES_PATH.read_text(encoding='utf-8'))
    out = []
    for c in all_cities:
        if not isinstance(c, dict):
            continue
        try:
            lat = float(c.get('lat'))
            lon = float(c.get('lon'))
        except Exception:
            continue
        region = str(c.get('region',''))
        area = str(c.get('pilot_area',''))
        if INCLUDE_ONLY_PILOT_AREAS:
            if area in ('Val Bormida - studio pilota','Liguria','Basso Piemonte') or region in ('Liguria','Piemonte'):
                out.append(c)
        else:
            out.append(c)
    return out


def query_city_genus(city, group, genus):
    lat = float(city.get('lat'))
    lon = float(city.get('lon'))
    taxon_key = taxon_key_for_genus(genus)
    base = {
        'country': 'IT',
        'hasCoordinate': 'true',
        'hasGeospatialIssue': 'false',
        'occurrenceStatus': 'PRESENT',
        'geometry': bbox_wkt(bbox_for_point(lat, lon, RADIUS_KM))
    }
    if taxon_key:
        base['taxonKey'] = taxon_key
    else:
        base['scientificName'] = genus
    rows = []
    offset = 0
    pages = 0
    fetched = 0
    while fetched < MAX_PER_GENUS_CITY and pages < MAX_PAGES_PER_GENUS_CITY:
        limit = min(PAGE_SIZE, MAX_PER_GENUS_CITY - fetched)
        payload = get_json(GBIF_OCCURRENCE_API, dict(base, limit=limit, offset=offset))
        batch = payload.get('results') or []
        if not batch:
            break
        for item in batch:
            if not valid_coords(item):
                continue
            ilat = float(item.get('decimalLatitude'))
            ilon = float(item.get('decimalLongitude'))
            dist = haversine_km(lat, lon, ilat, ilon)
            if dist <= RADIUS_KM:
                row = row_from_item(item, group, city, genus, dist)
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


def purge_non_real(rows):
    purged = []
    kept = []
    for r in rows:
        source = str(r.get('source',''))
        rid = str(r.get('id',''))
        if source == 'PILOT_MUNICIPAL_VECTOR_CONTEXT' or rid.startswith('pilot-municipal-'):
            purged.append(r)
        else:
            kept.append(r)
    return kept, purged


def main():
    if not CITIES_PATH.exists():
        raise SystemExit(f'Cities file not found: {CITIES_PATH}')
    existing, fields = read_csv(CSV_PATH)
    existing, purged = purge_non_real(existing)
    by_id = {r.get('id'): r for r in existing if r.get('id')}
    cities = load_cities()
    detail = {}
    new_rows = []
    for city in cities:
        cname = str(city.get('name',''))
        for group, genera in GENERA.items():
            for genus in genera:
                key = f'{cname} | {group} | {genus}'
                try:
                    rows, fetched = query_city_genus(city, group, genus)
                    detail[key] = {'candidate_rows': len(rows), 'gbif_records_read': fetched}
                    new_rows.extend(rows)
                except Exception as e:
                    detail[key] = {'error': str(e)}
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
    source_counts = {}
    for row in new_rows:
        group_counts[row.get('ui_group','missing')] = group_counts.get(row.get('ui_group','missing'), 0) + 1
        source_counts[row.get('source','missing')] = source_counts.get(row.get('source','missing'), 0) + 1
    print(json.dumps({
        'status': 'success',
        'scope': 'Real GBIF city-centered import for Piemonte and Liguria operational cities',
        'cities_used': len(cities),
        'radius_km': RADIUS_KM,
        'purged_non_real_pilot_layers': len(purged),
        'candidate_rows': len(new_rows),
        'inserted': inserted,
        'updated': updated,
        'total_rows': len(existing),
        'ui_group_counts_new_rows': group_counts,
        'source_counts_new_rows': source_counts,
        'detail': detail,
        'csv_path': str(CSV_PATH)
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
