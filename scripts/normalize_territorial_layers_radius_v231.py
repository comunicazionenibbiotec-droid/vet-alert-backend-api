#!/usr/bin/env python3
from __future__ import annotations
import csv, json, os
from pathlib import Path
from datetime import datetime, timezone

CSV_PATH = Path(os.getenv('TERRITORIAL_LAYERS_CSV_PATH', 'data/territorial_layers/territorial_layers.csv'))
FIELD_EXTRA = [
    'ui_group','ui_group_label','subcategory','localization_precision','display_radius_km',
    'radius_km','count','count_label','case_count','updated_at'
]
GROUP_LABELS = {
    'sand_flies':'Flebotomi',
    'ticks':'Zecche',
    'mosquitoes_other_vectors':'Zanzare / altri vettori',
    'parasites':'Parassiti',
    'west_nile':'West Nile'
}

CAPITALS = {
 'Torino':(45.0703,7.6869),'Cuneo':(44.3845,7.5427),'Asti':(44.9008,8.2065),'Alessandria':(44.9073,8.6117),'Vercelli':(45.3202,8.4185),'Novara':(45.4469,8.6222),'Verbania':(45.9212,8.5517),'Biella':(45.5629,8.0583),
 'Milano':(45.4642,9.1900),'Pavia':(45.1847,9.1582),'Brescia':(45.5416,10.2118),'Bergamo':(45.6983,9.6773),'Mantova':(45.1564,10.7914),'Como':(45.8081,9.0852),'Varese':(45.8206,8.8251),'Lecco':(45.8566,9.3977),'Lodi':(45.3097,9.5037),'Cremona':(45.1332,10.0227),'Sondrio':(46.1699,9.8788),
 'Genova':(44.4056,8.9463),'Savona':(44.3079,8.4810),'Imperia':(43.8897,8.0396),'La Spezia':(44.1025,9.8241),
 'Bologna':(44.4949,11.3426),'Ferrara':(44.8381,11.6198),'Modena':(44.6471,10.9252),'Parma':(44.8015,10.3279),'Reggio Emilia':(44.6983,10.6312),'Ravenna':(44.4184,12.2035),'Forli-Cesena':(44.2227,12.0407),'Rimini':(44.0678,12.5695),'Piacenza':(45.0526,9.6933),
 'Verona':(45.4384,10.9916),'Padova':(45.4064,11.8768),'Rovigo':(45.0698,11.7902),'Vicenza':(45.5455,11.5354),'Treviso':(45.6669,12.2430),'Venezia':(45.4408,12.3155),'Belluno':(46.1425,12.2167),
 'Firenze':(43.7696,11.2558),'Grosseto':(42.7635,11.1124),'Livorno':(43.5485,10.3106),'Pisa':(43.7228,10.4017),'Siena':(43.3188,11.3308),'Arezzo':(43.4633,11.8796),'Prato':(43.8777,11.1022),'Pistoia':(43.9303,10.9079),'Lucca':(43.8429,10.5027),
 'Roma':(41.9028,12.4964),'Latina':(41.4676,12.9037),'Frosinone':(41.6396,13.3512),'Viterbo':(42.4207,12.1077),'Rieti':(42.4045,12.8567),
 'Napoli':(40.8518,14.2681),'Caserta':(41.0724,14.3316),'Salerno':(40.6824,14.7681),'Avellino':(40.9146,14.7897),'Benevento':(41.1298,14.7821),
 'Bari':(41.1171,16.8719),'Lecce':(40.3515,18.1750),'Foggia':(41.4622,15.5446),'Taranto':(40.4644,17.2470),'Brindisi':(40.6327,17.9418),
 'Palermo':(38.1157,13.3615),'Catania':(37.5079,15.0830),'Messina':(38.1938,15.5540),'Trapani':(38.0176,12.5362),'Agrigento':(37.3111,13.5765),'Caltanissetta':(37.4901,14.0629),'Enna':(37.5675,14.2790),'Ragusa':(36.9269,14.7255),'Siracusa':(37.0755,15.2866),
 'Cagliari':(39.2238,9.1217),'Sassari':(40.7259,8.5557),'Nuoro':(40.3202,9.3264),'Oristano':(39.9062,8.5884),'Sud Sardegna':(39.1670,8.5220)
}
REGION_CAPITALS = {
 'Piemonte':'Torino','Lombardia':'Milano','Liguria':'Genova','Emilia-Romagna':'Bologna','Veneto':'Venezia','Toscana':'Firenze','Lazio':'Roma','Campania':'Napoli','Puglia':'Bari','Sicilia':'Palermo','Sardegna':'Cagliari','Friuli Venezia Giulia':'Trieste','Trentino-Alto Adige':'Trento','Marche':'Ancona','Umbria':'Perugia','Abruzzo':'L Aquila','Molise':'Campobasso','Basilicata':'Potenza','Calabria':'Catanzaro','Valle d Aosta':'Aosta'
}

def row_text(row):
    return ' '.join(str(row.get(k,'') or '') for k in ['category','label','scientific_name','data_type','source','display_source','notes','note','ui_group','subcategory']).lower()

def infer_group(row):
    t = row_text(row)
    cat = str(row.get('category','') or '').lower()
    explicit = str(row.get('ui_group') or row.get('subcategory') or '').strip()
    if explicit in GROUP_LABELS: return explicit
    if cat == 'west_nile' or 'west nile' in t or 'usutu' in t: return 'west_nile'
    if cat in ('parasites','parasite') or any(x in t for x in ['giardia','toxocara','ancylostoma','dirofilaria','echinococcus','parasite','parassit']): return 'parasites'
    if any(x in t for x in ['phlebotomus','phlebotominae','phlebotomine','sand fly','sandfly','flebotom','leish']): return 'sand_flies'
    if any(x in t for x in ['ixodes','dermacentor','hyalomma','rhipicephalus','ornithodoros','amblyomma','tick','zecc']): return 'ticks'
    if cat in ('vectors','vector'): return 'mosquitoes_other_vectors'
    return cat or 'mosquitoes_other_vectors'

def has_numeric_coords(row):
    try:
        return row.get('lat') not in (None,'') and row.get('lon') not in (None,'') and float(row.get('lat')) and float(row.get('lon'))
    except Exception:
        return False

def has_municipality(row):
    return any(str(row.get(k,'') or '').strip() for k in ['municipality','comune','city','locality','location'])

def infer_precision(row, group):
    explicit = ' '.join(str(row.get(k,'') or '').lower() for k in ['localization_precision','aggregation_level','precision','area_level','data_type'])
    # Real GBIF/Mosquito Alert points stay precise.
    if any(x in explicit for x in ['occurrence_point','real precise','point occurrence','coordinate / puntuale']):
        return 'coordinate / puntuale'
    # IMPORTANT: vector and parasite territorial layers with a municipality/location are municipal, not provincial.
    if group in ('sand_flies','ticks','mosquitoes_other_vectors','parasites') and has_municipality(row):
        return 'comunale'
    # Existing explicit administrative precision for WNV or records without municipality.
    if 'region' in explicit: return 'regionale'
    if 'prov' in explicit: return 'provinciale'
    if any(x in explicit for x in ['comun','municip','city','locality']): return 'comunale'
    if has_municipality(row): return 'comunale'
    if str(row.get('province','') or '').strip(): return 'provinciale'
    if str(row.get('region','') or '').strip(): return 'regionale'
    if has_numeric_coords(row): return 'coordinate / puntuale'
    return 'territoriale'

def radius_for_precision(precision):
    return '10' if precision in ('coordinate / puntuale','comunale') else '25'

def center_admin_aggregate(row, precision):
    # Only provincial/regional aggregates are recentered on administrative capital.
    # Municipal and precise rows keep their uploaded coordinates.
    if precision not in ('provinciale','regionale'):
        return
    prov = (row.get('province') or row.get('location') or '').strip()
    reg = (row.get('region') or '').strip()
    cap = prov if prov in CAPITALS else REGION_CAPITALS.get(reg,'')
    if cap in CAPITALS:
        lat, lon = CAPITALS[cap]
        row['lat'] = str(lat)
        row['lon'] = str(lon)
        if not row.get('location'):
            row['location'] = cap

def normalize_count(row):
    raw = row.get('count') or row.get('case_count') or row.get('value') or '1'
    try:
        n = int(float(str(raw).replace(',','.')))
        if n < 1: n = 1
    except Exception:
        n = 1
    return n

def main():
    if not CSV_PATH.exists():
        raise SystemExit(f'CSV not found: {CSV_PATH}')
    with CSV_PATH.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    for f in FIELD_EXTRA:
        if f not in fields:
            fields.append(f)
    changed = 0
    counts = {}
    radius_counts = {}
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        before = {k: row.get(k) for k in FIELD_EXTRA + ['lat','lon']}
        group = infer_group(row)
        precision = infer_precision(row, group)
        center_admin_aggregate(row, precision)
        n = normalize_count(row)
        row['ui_group'] = group
        row['ui_group_label'] = GROUP_LABELS.get(group, group)
        row['subcategory'] = group
        row['localization_precision'] = precision
        row['display_radius_km'] = radius_for_precision(precision)
        row['radius_km'] = radius_for_precision(precision)
        row['count'] = str(n)
        row['case_count'] = str(n)
        row['count_label'] = row.get('count_label') or ('record reale' if n == 1 else 'record reali')
        row['updated_at'] = now
        counts[group] = counts.get(group, 0) + 1
        key = f"{precision} -> {row['display_radius_km']}"
        radius_counts[key] = radius_counts.get(key, 0) + 1
        after = {k: row.get(k) for k in FIELD_EXTRA + ['lat','lon']}
        if before != after:
            changed += 1
    with CSV_PATH.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'status':'success','csv_path':str(CSV_PATH),'rows':len(rows),'changed':changed,'ui_group_counts':counts,'radius_counts':radius_counts}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
