#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, os, time, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone

GBIF_API=os.getenv('GBIF_OCCURRENCE_API','https://api.gbif.org/v1/occurrence/search')
CSV_PATH=Path(os.getenv('TERRITORIAL_LAYERS_CSV_PATH','data/territorial_layers/territorial_layers.csv'))
COUNTRY=os.getenv('REAL_EVENTS_COUNTRY','IT')
MAX_PER_QUERY=int(os.getenv('REAL_EVENTS_MAX_PER_QUERY','300'))
MAX_PAGES=int(os.getenv('REAL_EVENTS_MAX_PAGES','4'))
PAGE_SIZE=int(os.getenv('REAL_EVENTS_PAGE_SIZE','300'))
MAX_UNCERTAINTY_M=float(os.getenv('REAL_EVENTS_MAX_UNCERTAINTY_M','10000'))
USER_AGENT=os.getenv('GBIF_USER_AGENT','vetector-real-events-importer/230; contact=nibbiotec.com')
VECTORNET_DATASET_KEY=os.getenv('VECTORNET_GBIF_DATASET_KEY','4abd984b-122c-44a0-8c92-b37e2f5299b1')
MOSQUITO_ALERT_DATASET_KEY=os.getenv('MOSQUITO_ALERT_DATASET_KEY','1fef1ead-3d02-495e-8ff1-6aeb01123408')
INCLUDE_VECTORNET=os.getenv('REAL_EVENTS_INCLUDE_VECTORNET','true').lower()=='true'
INCLUDE_MOSQUITO_ALERT=os.getenv('REAL_EVENTS_INCLUDE_MOSQUITO_ALERT','true').lower()=='true'

FIELDNAMES=[
 'id','external_id','category','ui_group','ui_group_label','subcategory','source','display_source','label','scientific_name','data_type','count','count_label','period_start','period_end','country','region','province','municipality','location','lat','lon','radius_km','display_radius_km','localization_precision','aggregation_level','precision','color','url_source','notes','coordinate_uncertainty_m','license','source_dataset','updated_at'
]
GROUP_LABELS={'sand_flies':'Flebotomi','ticks':'Zecche','mosquitoes_other_vectors':'Zanzare / altri vettori'}
COLORS={'sand_flies':'#F26522','ticks':'#7C3AED','mosquitoes_other_vectors':'#2563EB'}
SPECIES={
 'sand_flies':['Phlebotomus perniciosus','Phlebotomus perfiliewi','Phlebotomus neglectus','Phlebotomus ariasi','Phlebotomus mascitii','Phlebotomus papatasi','Phlebotomus sergenti','Phlebotomus tobbi'],
 'ticks':['Ixodes ricinus','Dermacentor reticulatus','Hyalomma marginatum','Hyalomma lusitanicum','Rhipicephalus sanguineus','Ornithodoros erraticus','Ixodes persulcatus'],
 'mosquitoes_other_vectors':['Aedes albopictus','Aedes aegypti','Aedes japonicus','Aedes koreicus','Culex pipiens','Culex modestus','Anopheles maculipennis','Culicoides imicola']
}

def stable_id(*parts):
    return hashlib.sha1('|'.join(str(p or '').strip().lower() for p in parts).encode('utf-8')).hexdigest()[:32]

def gbif_json(params):
    q=urllib.parse.urlencode(params)
    req=urllib.request.Request(f'{GBIF_API}?{q}',headers={'User-Agent':USER_AGENT})
    with urllib.request.urlopen(req,timeout=90) as r:
        return json.loads(r.read().decode('utf-8'))

def precision_ok(item):
    if item.get('decimalLatitude') is None or item.get('decimalLongitude') is None: return False
    try: float(item.get('decimalLatitude')); float(item.get('decimalLongitude'))
    except Exception: return False
    unc=item.get('coordinateUncertaintyInMeters')
    if unc in (None,''): return True
    try: return float(unc)<=MAX_UNCERTAINTY_M
    except Exception: return True

def row_from_item(item, group, source_label):
    if not precision_ok(item): return None
    lat=float(item.get('decimalLatitude')); lon=float(item.get('decimalLongitude'))
    scientific=item.get('scientificName') or item.get('acceptedScientificName') or item.get('verbatimScientificName') or 'Vettore'
    gbif_key=item.get('key') or item.get('gbifID') or item.get('occurrenceID')
    event_date=str(item.get('eventDate') or '')[:10]
    year=item.get('year')
    period=event_date or (str(year) if year else '')
    unc=item.get('coordinateUncertaintyInMeters')
    rid='real-gbif-'+stable_id(gbif_key,scientific,lat,lon,source_label)
    note='Occorrenza reale georeferenziata importata da GBIF. Dato di contesto territoriale, non diagnosi clinica.'
    if unc not in (None,''): note += f' Coordinate uncertainty: {unc} m.'
    else: note += ' Coordinate uncertainty not declared by source.'
    return {
        'id':rid,'external_id':str(gbif_key or rid),'category':'vectors','ui_group':group,'ui_group_label':GROUP_LABELS[group],'subcategory':group,
        'source':source_label,'display_source':source_label,'label':scientific,'scientific_name':scientific,'data_type':'Real precise vector occurrence','count':'1','count_label':'occurrence record',
        'period_start':period,'period_end':period,'country':item.get('country') or COUNTRY,'region':item.get('stateProvince') or '','province':item.get('county') or '',
        'municipality':item.get('municipality') or '','location':item.get('locality') or item.get('municipality') or item.get('county') or item.get('stateProvince') or '',
        'lat':f'{lat:.7f}','lon':f'{lon:.7f}','radius_km':'10','display_radius_km':'10','localization_precision':'coordinate / puntuale','aggregation_level':'occurrence_point','precision':'coordinate / puntuale','color':COLORS[group],
        'url_source':('https://www.gbif.org/occurrence/'+str(gbif_key)) if gbif_key else 'https://www.gbif.org/','notes':note,'coordinate_uncertainty_m':'' if unc is None else str(unc),
        'license':item.get('license') or '','source_dataset':item.get('datasetName') or item.get('datasetKey') or '','updated_at':datetime.now(timezone.utc).isoformat()
    }

def fetch_query(params,group,source_label):
    rows=[]; offset=0; pages=0; fetched=0
    while fetched<MAX_PER_QUERY and pages<MAX_PAGES:
        limit=min(PAGE_SIZE,MAX_PER_QUERY-fetched)
        payload=gbif_json(dict(params,limit=limit,offset=offset))
        batch=payload.get('results') or []
        if not batch: break
        for item in batch:
            row=row_from_item(item,group,source_label)
            if row: rows.append(row)
        fetched += len(batch); offset += len(batch); pages += 1
        if payload.get('endOfRecords'): break
        time.sleep(0.15)
    return rows

def read_existing(path):
    if not path.exists(): return [], FIELDNAMES[:]
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f); rows=list(reader); fields=list(reader.fieldnames or [])
    for f in FIELDNAMES:
        if f not in fields: fields.append(f)
    return rows,fields

def write_rows(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)

def main():
    new=[]; detail={}
    common={'country':COUNTRY,'hasCoordinate':'true','hasGeospatialIssue':'false','occurrenceStatus':'PRESENT'}
    if INCLUDE_VECTORNET:
        for group,names in SPECIES.items():
            for species in names:
                params=dict(common,datasetKey=VECTORNET_DATASET_KEY,scientificName=species)
                try:
                    rows=fetch_query(params,group,'VectorNet / GBIF')
                    detail[f'VectorNet {species}']=len(rows); new.extend(rows)
                except Exception as e:
                    detail[f'VectorNet {species}']=f'error: {e}'
    if INCLUDE_MOSQUITO_ALERT:
        try:
            rows=fetch_query(dict(common,datasetKey=MOSQUITO_ALERT_DATASET_KEY),'mosquitoes_other_vectors','Mosquito Alert / GBIF')
            detail['Mosquito Alert dataset']=len(rows); new.extend(rows)
        except Exception as e:
            detail['Mosquito Alert dataset']=f'error: {e}'
    existing,fields=read_existing(CSV_PATH)
    by_id={r.get('id'):r for r in existing if r.get('id')}
    inserted=updated=0
    for row in new:
        rid=row.get('id')
        if rid in by_id:
            by_id[rid].update(row); updated += 1
        else:
            existing.append(row); by_id[rid]=row; inserted += 1
    write_rows(CSV_PATH,existing,fields)
    print(json.dumps({'status':'success','csv_path':str(CSV_PATH),'candidate_rows':len(new),'inserted':inserted,'updated':updated,'total_rows':len(existing),'detail':detail},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
