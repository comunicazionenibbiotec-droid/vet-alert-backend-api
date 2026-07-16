#!/usr/bin/env python3
from __future__ import annotations
import csv, json
from pathlib import Path

FIELDS = ['external_id', 'category', 'source', 'label', 'scientific_name', 'data_type', 'count', 'period_start', 'period_end', 'country', 'region', 'province', 'location', 'lat', 'lon', 'radius_km', 'color', 'url_source', 'notes']
CITIES = {'Torino': ('Piemonte', 'Torino', 45.0703, 7.6869), 'Cuneo': ('Piemonte', 'Cuneo', 44.3845, 7.5427), 'Milano': ('Lombardia', 'Milano', 45.4642, 9.19), 'Pavia': ('Lombardia', 'Pavia', 45.1847, 9.1582), 'Brescia': ('Lombardia', 'Brescia', 45.5416, 10.2118), 'Genova': ('Liguria', 'Genova', 44.4048, 8.9444), 'Verona': ('Veneto', 'Verona', 45.4384, 10.9916), 'Padova': ('Veneto', 'Padova', 45.4064, 11.8768), 'Bologna': ('Emilia-Romagna', 'Bologna', 44.4949, 11.3426), 'Parma': ('Emilia-Romagna', 'Parma', 44.8015, 10.3279), 'Firenze': ('Toscana', 'Firenze', 43.7696, 11.2558), 'Grosseto': ('Toscana', 'Grosseto', 42.7635, 11.1124), 'Roma': ('Lazio', 'Roma', 41.9028, 12.4964), 'Napoli': ('Campania', 'Napoli', 40.8518, 14.2681), 'Caserta': ('Campania', 'Caserta', 41.0747, 14.3324), 'Bari': ('Puglia', 'Bari', 41.1171, 16.8719), 'Palermo': ('Sicilia', 'Palermo', 38.1157, 13.3615), 'Cagliari': ('Sardegna', 'Cagliari', 39.2238, 9.1217)}
ALL=list(CITIES.keys())
NORTH=['Torino','Cuneo','Milano','Pavia','Brescia','Genova','Verona','Padova','Bologna','Parma','Firenze']
NORTH_TICKS=['Torino','Cuneo','Milano','Pavia','Brescia','Verona','Padova','Bologna','Parma']
COAST_MED=['Genova','Grosseto','Roma','Napoli','Caserta','Bari','Palermo','Cagliari','Firenze']
SPECIES = [('Ixodes ricinus', 'Ixodes ricinus', 'tick_present_area', ['Torino', 'Cuneo', 'Milano', 'Pavia', 'Brescia', 'Genova', 'Verona', 'Padova', 'Bologna', 'Parma', 'Firenze'], 35, '#6D28D9', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/tick-maps', 'Tick distribution context from ECDC/VectorNet tick maps. Ixodes ricinus is an important tick vector; area layer centred on the menu city.'), ('Rhipicephalus sanguineus', 'Rhipicephalus sanguineus', 'tick_present_area', ['Torino', 'Cuneo', 'Milano', 'Pavia', 'Brescia', 'Genova', 'Verona', 'Padova', 'Bologna', 'Parma', 'Firenze', 'Grosseto', 'Roma', 'Napoli', 'Caserta', 'Bari', 'Palermo', 'Cagliari'], 35, '#6D28D9', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/tick-maps', 'Tick distribution context from ECDC/VectorNet tick maps. Rhipicephalus sanguineus is a dog-associated tick vector; area layer centred on the menu city.'), ('Dermacentor reticulatus', 'Dermacentor reticulatus', 'tick_present_area', ['Torino', 'Cuneo', 'Milano', 'Pavia', 'Brescia', 'Verona', 'Padova', 'Bologna', 'Parma'], 35, '#6D28D9', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/tick-maps', 'Tick distribution context from ECDC/VectorNet tick maps. Dermacentor reticulatus layer uses conservative northern/Po-valley menu-city coverage.'), ('Phlebotomus perniciosus', 'Phlebotomus perniciosus', 'sandfly_present_area', ['Genova', 'Grosseto', 'Roma', 'Napoli', 'Caserta', 'Bari', 'Palermo', 'Cagliari', 'Firenze', 'Torino', 'Milano', 'Pavia', 'Brescia', 'Verona', 'Padova', 'Bologna', 'Parma'], 45, '#9333EA', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps', 'Phlebotomine sandfly context from ECDC/VectorNet maps; relevant to Leishmania transmission ecology. Area layer, not a clinical case.'), ('Culicoides spp.', 'Culicoides spp.', 'biting_midge_present_area', ['Torino', 'Cuneo', 'Milano', 'Pavia', 'Brescia', 'Genova', 'Verona', 'Padova', 'Bologna', 'Parma', 'Firenze', 'Grosseto', 'Roma', 'Napoli', 'Caserta', 'Bari', 'Palermo', 'Cagliari'], 50, '#4C1D95', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/biting-midge-maps', 'Biting midge distribution context from ECDC/VectorNet maps; relevant to livestock vector-borne disease ecology such as bluetongue. Area layer, not a clinical case.')]
OUT=Path('data/territorial_layers/extended_vector_layers.csv')
META=Path('data/territorial_layers/extended_vector_layers_metadata.json')

def slug(s):
    return ''.join([c if c.isalnum() else '-' for c in s.upper()]).strip('-').replace('--','-')

def build_rows():
    seen=set(); out=[]
    for label,sci,dt,city_list,radius,color,url,note in SPECIES:
        for city in city_list:
            if city not in CITIES: continue
            if (sci,city) in seen: continue
            seen.add((sci,city))
            region,prov,lat,lon=CITIES[city]
            out.append({'external_id':f'VECTORNET-CURATED-2026-{slug(sci)}-{slug(city)}','category':'vectors','source':'VECTORNET_CURATED','label':label,'scientific_name':sci,'data_type':dt,'count':'1','period_start':'2026-01-01','period_end':'2026-06-03','country':'Italy','region':region,'province':prov,'location':city,'lat':f'{lat:.4f}','lon':f'{lon:.4f}','radius_km':str(radius),'color':color,'url_source':url,'notes':note+' Count=1 means documented distribution/presence area, not number of observations. Circle radius reflects territorial aggregation, not case count.'})
    return out

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows=build_rows()
    with OUT.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    counts={}
    for r in rows: counts[r['scientific_name']]=counts.get(r['scientific_name'],0)+1
    META.write_text(json.dumps({'version':'v149-extended-vector-layers','rows':len(rows),'species_counts':counts,'interpretation':'area-level vector presence/distribution layers; radius_km is aggregation radius, count is not observations'},indent=2,ensure_ascii=False),encoding='utf-8')
    print({'status':'success','rows':len(rows),'species_counts':counts})
if __name__ == '__main__': main()
