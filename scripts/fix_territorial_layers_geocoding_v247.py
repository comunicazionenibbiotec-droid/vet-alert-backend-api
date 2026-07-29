#!/usr/bin/env python3
from __future__ import annotations
import csv, json, re, unicodedata
from pathlib import Path
from datetime import datetime

COMUNI = Path('data/reference/italia_comuni_centroids.csv')
REPORT = Path('data/territorial_layers/territorial_geocoding_fix_report_v247.csv')
FILES = [
    Path('data/territorial_layers/territorial_layers.csv'),
    Path('data/territorial_layers/vectornet_gbif_layers.csv'),
    Path('data/territorial_layers/mosquito_alert_layers.csv'),
    Path('data/territorial_layers/west_nile_surveillance.csv'),
    Path('data/territorial_layers/benv_parasite_layers.csv'),
    Path('data/territorial_layers/esccap_parasites.csv'),
    Path('data/territorial_layers/extended_vector_layers.csv'),
]
PROVINCE_CAPITAL_DISPLAY_FIX = {
    'Forli-Cesena': 'Forlì-Cesena',
    'Massa-Carrara': 'Massa',
    'Barletta-Andria-Trani': 'Andria',
    'Sud Sardegna': 'Carbonia',
}

def norm(s: str) -> str:
    s = str(s or '').strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
    s = re.sub(r"\b(provincia|comune)\s+(di|del|della|dei|degli|dell')?\b", ' ', s)
    s = re.sub(r"[^a-z0-9]+", ' ', s)
    return re.sub(r"\s+", ' ', s).strip()

def clean(s): return str(s or '').strip()

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

def load_comuni():
    rows, fields = read_csv(COMUNI)
    if len(rows) < 7000:
        raise SystemExit(f'{COMUNI} has only {len(rows)} rows; run scripts/build_comuni_reference_v246.py first')
    items=[]
    for r in rows:
        name = clean(r.get('comune') or r.get('location') or r.get('municipality') or r.get('name'))
        prov = clean(r.get('provincia') or r.get('province'))
        sigla = clean(r.get('sigla_provincia') or r.get('sigla') or r.get('province_code')).upper()
        reg = clean(r.get('regione') or r.get('region'))
        try:
            lat=float(str(r.get('lat')).replace(',','.')); lon=float(str(r.get('lon') or r.get('long') or r.get('lng')).replace(',','.'))
        except Exception:
            continue
        if not name: continue
        items.append({'name':name,'province':prov,'province_code':sigla,'region':reg,'lat':lat,'lon':lon,'n_name':norm(name),'n_province':norm(prov),'n_region':norm(reg)})
    return items

def build_indices(items):
    by_name_region={}; by_name_prov={}; by_name={}
    for x in items:
        by_name_region.setdefault((x['n_name'],x['n_region']),[]).append(x)
        by_name_prov.setdefault((x['n_name'],x['n_province']),[]).append(x)
        by_name.setdefault(x['n_name'],[]).append(x)
    province_centers={}
    for x in items:
        # Prefer capital whose name matches the province or special display fix.
        display = PROVINCE_CAPITAL_DISPLAY_FIX.get(x['province'], x['province'])
        if norm(x['name']) == norm(display):
            province_centers[x['n_province']] = x
    # fallback first item per province
    for x in items:
        province_centers.setdefault(x['n_province'], x)
    return by_name_region, by_name_prov, by_name, province_centers

def source_text(row):
    return ' '.join(str(row.get(k,'') or '') for k in ['source','display_source','data_type','label','scientific_name','notes','note','category','localization_precision','aggregation_level'])

def is_point_occurrence(row):
    t = source_text(row).lower()
    if 'coordinate / puntuale' in t or 'occurrence_point' in t or 'point occurrence' in t or 'real precise' in t:
        return True
    # Real occurrence coordinates must not be snapped to municipalities.
    if 'gbif real occurrence' in t or 'mosquito alert / gbif validated occurrence' in t or 'real_gbif' in t:
        return True
    return False

def explicit_precision(row):
    t = source_text(row).lower()
    if 'region' in t and 'regionale' in t: return 'regionale'
    if 'provinc' in t or 'provinciale' in t: return 'provinciale'
    if 'comun' in t or 'municip' in t: return 'comunale'
    if is_point_occurrence(row): return 'coordinate / puntuale'
    return ''

def location_value(row):
    for k in ['municipality','comune','city','locality','location','area_label','area']:
        v = clean(row.get(k))
        if v: return v
    return ''

def match_municipality(row, idx):
    by_name_region, by_name_prov, by_name, province_centers = idx
    loc = location_value(row)
    if not loc or re.match(r'^provincia\s+', loc, flags=re.I): return None, 'missing_or_province_location'
    nloc=norm(loc); nreg=norm(row.get('region')); nprov=norm(row.get('province'))
    if nreg:
        c=by_name_region.get((nloc,nreg),[])
        if len(c)==1: return c[0], 'municipality_region'
    if nprov:
        c=by_name_prov.get((nloc,nprov),[])
        if len(c)==1: return c[0], 'municipality_province'
    c=by_name.get(nloc,[])
    if len(c)==1: return c[0], 'municipality_unique'
    if len(c)>1: return None, 'ambiguous_municipality'
    return None, 'not_found'

def match_province(row, idx):
    nprov = norm(row.get('province') or row.get('location'))
    return idx[3].get(nprov)

def fix_row(row, idx):
    precision = explicit_precision(row)
    old_lat, old_lon = row.get('lat'), row.get('lon')
    target=None; match=''
    # Do not rewrite real point occurrences. They are already source coordinates.
    if precision == 'coordinate / puntuale':
        return False, 'kept_point_occurrence', old_lat, old_lon
    # Strong preference for real municipality/locality if available.
    target, match = match_municipality(row, idx)
    if not target and precision in {'provinciale','regionale'}:
        target = match_province(row, idx); match = 'province_centroid' if target else 'province_not_found'
    if not target:
        return False, match or 'not_found', old_lat, old_lon
    new_lat, new_lon = f"{target['lat']:.6f}", f"{target['lon']:.6f}"
    changed = str(old_lat) != new_lat or str(old_lon) != new_lon
    if changed:
        row['lat'], row['lon'] = new_lat, new_lon
        # Fill province/region when missing or inconsistent.
        if not clean(row.get('province')): row['province'] = target['province']
        if not clean(row.get('region')): row['region'] = target['region']
        note_key = 'territorial geocoding correction v247'
        note = row.get('notes') or row.get('note') or ''
        msg = f"{note_key}: snapped to {target['name']} ({target['province']}); previous coordinates {old_lat},{old_lon}; match={match}."
        if note_key not in note:
            if 'notes' in row: row['notes'] = (note + '; ' + msg).strip('; ')
            elif 'note' in row: row['note'] = (note + '; ' + msg).strip('; ')
    return changed, match, old_lat, old_lon

def fix_file(path, idx):
    rows, fields = read_csv(path)
    if not rows: return {'file':str(path),'rows':0,'changed':0,'skipped':0}, []
    for field in ['lat','lon','province','region','notes']:
        if field not in fields: fields.append(field)
    changed=0; skipped=0; report=[]
    for row in rows:
        did, match, old_lat, old_lon = fix_row(row, idx)
        changed += 1 if did else 0
        skipped += 0 if did else 1
        report.append({'file':path.name,'external_id':row.get('external_id') or row.get('id',''),'category':row.get('category',''),'source':row.get('source',''),'label':row.get('label') or row.get('scientific_name',''),'location':location_value(row),'province':row.get('province',''),'precision':explicit_precision(row),'match':match,'old_lat':old_lat,'old_lon':old_lon,'new_lat':row.get('lat',''),'new_lon':row.get('lon',''),'changed':str(did).lower()})
    write_csv(path, rows, fields)
    return {'file':str(path),'rows':len(rows),'changed':changed,'skipped':skipped}, report

def main():
    items=load_comuni(); idx=build_indices(items)
    results=[]; reports=[]
    for f in FILES:
        res, rep = fix_file(f, idx)
        results.append(res); reports.extend(rep)
    fields=['file','external_id','category','source','label','location','province','precision','match','old_lat','old_lon','new_lat','new_lon','changed']
    write_csv(REPORT, reports, fields)
    print(json.dumps({'status':'success','generated_at':datetime.utcnow().isoformat()+'Z','reference_comuni_rows':len(items),'files':results,'report':str(REPORT)},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
