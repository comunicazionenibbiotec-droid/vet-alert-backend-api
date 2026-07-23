#!/usr/bin/env python3
from __future__ import annotations
import csv, json, os, hashlib
from pathlib import Path
from datetime import datetime, timezone

CSV_PATH = Path(os.getenv('TERRITORIAL_LAYERS_CSV_PATH', 'data/territorial_layers/territorial_layers.csv'))
CITIES_PATH = Path(os.getenv('SOURCE_CITIES_PATH', 'data/source_cities.json'))

FIELDNAMES = [
    'id','external_id','category','ui_group','ui_group_label','subcategory','source','display_source',
    'label','scientific_name','data_type','count','count_label','case_count','period_start','period_end',
    'country','region','province','municipality','location','lat','lon','radius_km','display_radius_km',
    'localization_precision','aggregation_level','precision','color','url_source','notes',
    'coordinate_uncertainty_m','license','source_dataset','updated_at'
]

LABELS = {'sand_flies':'Flebotomi','ticks':'Zecche','mosquitoes_other_vectors':'Zanzare / altri vettori'}
COLORS = {'sand_flies':'#F26522','ticks':'#7C3AED','mosquitoes_other_vectors':'#2563EB'}

# Conservative pilot layer set: contextual vector-presence layers, not clinical cases.
PILOT_VECTOR_SET = [
    ('mosquitoes_other_vectors', 'Aedes albopictus', 'Aedes albopictus', 'municipal_context_vector_presence', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/mosquito-maps'),
    ('mosquitoes_other_vectors', 'Culex pipiens', 'Culex pipiens', 'municipal_context_vector_presence', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/mosquito-maps'),
    ('ticks', 'Ixodes ricinus', 'Ixodes ricinus', 'municipal_context_tick_presence', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/tick-maps'),
    ('ticks', 'Rhipicephalus sanguineus', 'Rhipicephalus sanguineus', 'municipal_context_tick_presence', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/tick-maps'),
    ('sand_flies', 'Phlebotomus perniciosus', 'Phlebotomus perniciosus', 'municipal_context_sandfly_presence', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps'),
    ('mosquitoes_other_vectors', 'Culicoides spp.', 'Culicoides spp.', 'municipal_context_biting_midge_presence', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/biting-midge-maps')
]

TARGET_PILOT_AREAS = ['Val Bormida - studio pilota']
# Keep a narrow pilot focus by default. Can be extended with env var.
INCLUDE_BROADER_LIGURIA = os.getenv('PILOT_MUNICIPAL_INCLUDE_BROADER_LIGURIA','false').lower() == 'true'
INCLUDE_BASSO_PIEMONTE = os.getenv('PILOT_MUNICIPAL_INCLUDE_BASSO_PIEMONTE','false').lower() == 'true'


def stable_id(*parts):
    return hashlib.sha1('|'.join(str(p or '').strip().lower() for p in parts).encode('utf-8')).hexdigest()[:32]


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


def load_pilot_cities():
    cities = json.loads(CITIES_PATH.read_text(encoding='utf-8'))
    out = []
    for c in cities:
        if not isinstance(c, dict):
            continue
        area = str(c.get('pilot_area',''))
        if area in TARGET_PILOT_AREAS:
            out.append(c)
        elif INCLUDE_BROADER_LIGURIA and area == 'Liguria':
            out.append(c)
        elif INCLUDE_BASSO_PIEMONTE and area == 'Basso Piemonte':
            out.append(c)
    return out


def main():
    if not CITIES_PATH.exists():
        raise SystemExit(f'Cities file not found: {CITIES_PATH}')
    rows, fields = read_csv(CSV_PATH)
    by_id = {r.get('id'): r for r in rows if r.get('id')}
    cities = load_pilot_cities()
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    updated = 0
    new_rows = []
    for city in cities:
        name = str(city.get('name','')).strip()
        if not name:
            continue
        lat = city.get('lat')
        lon = city.get('lon')
        province = city.get('province','')
        region = city.get('region','')
        for group, label, scientific, data_type, url in PILOT_VECTOR_SET:
            rid = 'pilot-municipal-' + stable_id(name, province, group, scientific)
            note = (
                'Layer municipale di contesto per area pilota Val Bormida. '
                'Dato di presenza/ecologia vettoriale di supporto al pilota, non diagnosi clinica e non focolaio. '
                'Count=1 indica layer di presenza documentata/contestuale, non numero di casi.'
            )
            row = {
                'id': rid,
                'external_id': rid,
                'category': 'vectors',
                'ui_group': group,
                'ui_group_label': LABELS[group],
                'subcategory': group,
                'source': 'PILOT_MUNICIPAL_VECTOR_CONTEXT',
                'display_source': 'PILOT_MUNICIPAL_VECTOR_CONTEXT',
                'label': label,
                'scientific_name': scientific,
                'data_type': data_type,
                'count': '1',
                'count_label': 'layer municipale di contesto',
                'case_count': '1',
                'period_start': '2026-01-01',
                'period_end': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                'country': city.get('country','Italy'),
                'region': region,
                'province': province,
                'municipality': name,
                'location': name,
                'lat': str(lat),
                'lon': str(lon),
                'radius_km': '10',
                'display_radius_km': '10',
                'localization_precision': 'comunale',
                'aggregation_level': 'municipal_context',
                'precision': 'comunale',
                'color': COLORS[group],
                'url_source': url,
                'notes': note,
                'coordinate_uncertainty_m': '',
                'license': '',
                'source_dataset': 'vet.ector pilot municipal layer',
                'updated_at': now
            }
            if rid in by_id:
                by_id[rid].update(row)
                updated += 1
            else:
                rows.append(row)
                by_id[rid] = row
                inserted += 1
                new_rows.append(row)
    write_csv(CSV_PATH, rows, fields)
    group_counts = {}
    city_counts = {}
    for r in [by_id[k] for k in by_id if str(k).startswith('pilot-municipal-')]:
        group_counts[r.get('ui_group','missing')] = group_counts.get(r.get('ui_group','missing'), 0) + 1
        city_counts[r.get('location','missing')] = city_counts.get(r.get('location','missing'), 0) + 1
    print(json.dumps({
        'status': 'success',
        'scope': 'Val Bormida pilot municipal vector context layers',
        'pilot_cities_used': [c.get('name') for c in cities],
        'inserted': inserted,
        'updated': updated,
        'total_rows': len(rows),
        'pilot_layer_group_counts': group_counts,
        'pilot_layer_city_counts': city_counts,
        'csv_path': str(CSV_PATH)
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
