"""Import VectorNet/GBIF vector occurrences, prioritising sand flies for leishmaniasis.

This importer uses GBIF occurrence search. In production, set either:
- VECTORNET_PUBLISHER_KEY (default: current VectorNet GBIF publisher key when known), or
- VECTORNET_DATASET_KEY for a specific VectorNet dataset.

It writes raw occurrences into vector_occurrences and creates territorial_layers rows for map display.
"""
import json
import os
from datetime import date

import requests

from common_v5 import db, finish_run, stable_id, start_run, upsert_layer, upsert_occurrence

SOURCE_ID = 'vectornet_gbif'
GBIF_API = 'https://api.gbif.org/v1/occurrence/search'
DEFAULT_PUBLISHER_KEY = '8f9f9814-a595-4bc3-8631-776ba3c9c62e'

PRIORITY_SPECIES = [
    'Phlebotomus perniciosus',
    'Phlebotomus perfiliewi',
    'Phlebotomus neglectus',
    'Phlebotomus ariasi',
    'Phlebotomus mascitii',
    'Phlebotomus papatasi',
    'Phlebotomus sergenti',
    'Phlebotomus tobbi',
    'Ixodes ricinus',
    'Culex pipiens',
    'Aedes albopictus',
]

LEISH_FOCUS = {
    'phlebotomus perniciosus', 'phlebotomus perfiliewi', 'phlebotomus neglectus',
    'phlebotomus ariasi', 'phlebotomus mascitii', 'phlebotomus papatasi',
    'phlebotomus sergenti', 'phlebotomus tobbi'
}


def norm_date(value):
    if not value:
        return None
    return str(value)[:10]


def fetch_species(species, limit, max_pages):
    results = []
    offset = 0
    publisher_key = os.getenv('VECTORNET_PUBLISHER_KEY', DEFAULT_PUBLISHER_KEY)
    dataset_key = os.getenv('VECTORNET_DATASET_KEY')
    while len(results) < limit and offset < limit and (offset // 300) < max_pages:
        params = {
            'country': os.getenv('VECTORNET_COUNTRY', 'IT'),
            'scientificName': species,
            'hasCoordinate': 'true',
            'limit': min(300, limit - len(results)),
            'offset': offset,
        }
        if dataset_key:
            params['datasetKey'] = dataset_key
        elif publisher_key:
            params['publishingOrg'] = publisher_key
        r = requests.get(GBIF_API, params=params, timeout=45, headers={'User-Agent': 'vetector-vectornet-importer/5.0'})
        r.raise_for_status()
        payload = r.json()
        batch = payload.get('results', [])
        results.extend(batch)
        if payload.get('endOfRecords') or not batch:
            break
        offset += len(batch)
    return results


def occurrence_record(item, species):
    lat = item.get('decimalLatitude')
    lon = item.get('decimalLongitude')
    if lat is None or lon is None:
        return None
    sci = item.get('scientificName') or species
    focus = 'Leishmania infantum / leishmaniasis vector' if sci.lower() in LEISH_FOCUS else None
    common = 'sand_fly' if sci.lower().startswith('phlebotomus') else ('mosquito' if sci.lower() in ['culex pipiens','aedes albopictus'] else 'tick')
    gbif_id = item.get('key') or item.get('gbifID')
    return {
        'id': 'gbif-vector-' + stable_id(gbif_id, sci, item.get('decimalLatitude'), item.get('decimalLongitude')),
        'scientific_name': sci,
        'common_group': common,
        'pathogen_focus': focus,
        'occurrence_status': item.get('occurrenceStatus') or 'PRESENT',
        'event_date': norm_date(item.get('eventDate')),
        'year': item.get('year'),
        'country': item.get('country') or 'Italy',
        'region': item.get('stateProvince'),
        'province': item.get('county'),
        'municipality': item.get('municipality'),
        'locality': item.get('locality'),
        'lat': float(lat),
        'lon': float(lon),
        'coordinate_uncertainty_m': item.get('coordinateUncertaintyInMeters'),
        'source': 'VectorNet / GBIF',
        'source_dataset': item.get('datasetName') or item.get('datasetKey'),
        'source_url': 'https://www.gbif.org/occurrence/' + str(gbif_id) if gbif_id else 'https://www.gbif.org/',
        'license': item.get('license'),
        'confidence_score': 90 if sci.lower() in LEISH_FOCUS else 75,
        'raw_payload': json.dumps(item, ensure_ascii=False),
    }


def occurrence_layer(rec):
    is_leish = rec['pathogen_focus'] is not None
    radius = 8 if rec.get('coordinate_uncertainty_m') is None else max(5, min(25, float(rec['coordinate_uncertainty_m']) / 1000.0))
    return {
        'id': 'layer-' + rec['id'],
        'category': 'vectors',
        'label': rec['scientific_name'],
        'scientific_name': rec['scientific_name'],
        'data_type': 'Vector occurrence' + (' / leishmaniasis vector' if is_leish else ''),
        'count': 1,
        'count_label': 'occurrence record',
        'country': rec['country'],
        'region': rec['region'],
        'province': rec['province'],
        'location': rec['locality'] or rec['municipality'] or rec['province'] or rec['region'],
        'lat': rec['lat'],
        'lon': rec['lon'],
        'radius_km': radius,
        'aggregation_level': 'occurrence_point',
        'source': 'VectorNet / GBIF',
        'display_source': 'VectorNet / GBIF occurrence',
        'period_start': rec['event_date'],
        'period_end': rec['event_date'],
        'url_source': rec['source_url'],
        'notes': 'High priority for leishmaniasis pilot.' if is_leish else 'Vector occurrence record; not a disease diagnosis.',
        'raw_payload': rec['raw_payload'],
    }


def main():
    species_list = [s.strip() for s in os.getenv('VECTORNET_SPECIES', ','.join(PRIORITY_SPECIES)).split(',') if s.strip()]
    per_species_limit = int(os.getenv('VECTORNET_LIMIT_PER_SPECIES', '300'))
    max_pages = int(os.getenv('VECTORNET_MAX_PAGES_PER_SPECIES', '3'))
    fetched = inserted = 0
    with db() as conn:
        run_id = start_run(conn, SOURCE_ID, {'species': species_list, 'limit_per_species': per_species_limit})
        try:
            for species in species_list:
                items = fetch_species(species, per_species_limit, max_pages)
                fetched += len(items)
                for item in items:
                    rec = occurrence_record(item, species)
                    if not rec:
                        continue
                    upsert_occurrence(conn, rec)
                    upsert_layer(conn, occurrence_layer(rec))
                    inserted += 1
            conn.commit()
            finish_run(conn, run_id, 'success', fetched=fetched, inserted=inserted)
        except Exception as exc:
            conn.rollback()
            finish_run(conn, run_id, 'failed', fetched=fetched, inserted=inserted, error=str(exc))
            raise
    print(json.dumps({'source': SOURCE_ID, 'fetched': fetched, 'inserted': inserted}, ensure_ascii=False))

if __name__ == '__main__':
    main()
