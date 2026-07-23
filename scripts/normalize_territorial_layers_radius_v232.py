#!/usr/bin/env python3
from __future__ import annotations
import csv, json, os
from pathlib import Path
from datetime import datetime, timezone

CSV_PATH = Path(os.getenv('TERRITORIAL_LAYERS_CSV_PATH', 'data/territorial_layers/territorial_layers.csv'))
FIELD_EXTRA = ['ui_group','ui_group_label','subcategory','localization_precision','display_radius_km','radius_km','case_count','updated_at']
LABELS = {'sand_flies':'Flebotomi','ticks':'Zecche','mosquitoes_other_vectors':'Zanzare / altri vettori','parasites':'Parassiti','west_nile':'West Nile'}

def txt(row):
    return ' '.join(str(row.get(k,'') or '') for k in ['category','label','scientific_name','data_type','source','display_source','notes','note','ui_group','subcategory']).lower()

def group(row):
    explicit = str(row.get('ui_group') or row.get('subcategory') or '').strip()
    if explicit in LABELS: return explicit
    t = txt(row); cat = str(row.get('category','') or '').lower()
    if cat == 'west_nile' or 'west nile' in t or 'wnv' in t or 'usutu' in t: return 'west_nile'
    if cat in ('parasites','parasite') or any(x in t for x in ['giardia','toxocara','ancylostoma','dirofilaria','echinococcus','parasite','parassit']): return 'parasites'
    if any(x in t for x in ['phlebotomus','phlebotominae','phlebotomine','sand fly','sandfly','flebotom','leish']): return 'sand_flies'
    if any(x in t for x in ['ixodes','dermacentor','hyalomma','rhipicephalus','ornithodoros','amblyomma','tick','zecc']): return 'ticks'
    if cat in ('vectors','vector'): return 'mosquitoes_other_vectors'
    return cat or 'mosquitoes_other_vectors'

def has_location(row):
    return any(str(row.get(k,'') or '').strip() for k in ['municipality','comune','city','locality','location'])

def precision(row, g):
    expl = ' '.join(str(row.get(k,'') or '').lower() for k in ['localization_precision','aggregation_level','precision','area_level','data_type','count_label'])
    loc = str(row.get('location','') or '').lower()
    # Real occurrence points stay point-level.
    if any(x in expl for x in ['occurrence_point','real precise','point occurrence','coordinate / puntuale']):
        return 'coordinate / puntuale'
    # West Nile prevention/surveillance areas are provincial/regional even when location contains "Provincia di ...".
    if g == 'west_nile':
        if 'region' in expl or (str(row.get('region','') or '').strip() and not str(row.get('province','') or '').strip()): return 'regionale'
        return 'provinciale'
    # Vectors/parasitology with explicit city/location are municipal contextual layers.
    if g in ('sand_flies','ticks','mosquitoes_other_vectors','parasites') and has_location(row): return 'comunale'
    if 'region' in expl: return 'regionale'
    if 'prov' in expl: return 'provinciale'
    if any(x in expl for x in ['comun','municip','city','locality']): return 'comunale'
    if has_location(row): return 'comunale'
    if str(row.get('province','') or '').strip(): return 'provinciale'
    if str(row.get('region','') or '').strip(): return 'regionale'
    return 'territoriale'

def radius(p):
    return '10' if p in ('coordinate / puntuale','comunale') else '25'

def count_value(row):
    raw = row.get('count') or row.get('case_count') or row.get('value') or '1'
    try:
        return max(1, int(float(str(raw).replace(',','.'))))
    except Exception:
        return 1

def main():
    if not CSV_PATH.exists(): raise SystemExit(f'CSV not found: {CSV_PATH}')
    with CSV_PATH.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f); rows = list(reader); fields = list(reader.fieldnames or [])
    for f in FIELD_EXTRA:
        if f not in fields: fields.append(f)
    changed = 0; groups = {}; radii = {}; now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        before = tuple(row.get(k) for k in FIELD_EXTRA + ['lat','lon'])
        g = group(row); p = precision(row, g); r = radius(p); n = count_value(row)
        row['ui_group'] = g; row['ui_group_label'] = LABELS.get(g,g); row['subcategory'] = g
        row['localization_precision'] = p; row['display_radius_km'] = r; row['radius_km'] = r
        row['count'] = str(n); row['case_count'] = str(n)
        if not row.get('count_label'):
            row['count_label'] = 'record reale' if n == 1 else 'record reali'
        row['updated_at'] = now
        groups[g] = groups.get(g,0)+1
        radii[f'{p} -> {r}'] = radii.get(f'{p} -> {r}',0)+1
        after = tuple(row.get(k) for k in FIELD_EXTRA + ['lat','lon'])
        if before != after: changed += 1
    with CSV_PATH.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({'status':'success','csv_path':str(CSV_PATH),'rows':len(rows),'changed':changed,'ui_group_counts':groups,'radius_counts':radii}, ensure_ascii=False, indent=2))

if __name__ == '__main__': main()
