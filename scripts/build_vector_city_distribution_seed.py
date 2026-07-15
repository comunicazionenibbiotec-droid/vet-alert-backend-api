from __future__ import annotations
import csv, json, os, re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'territorial_layers' / 'vectornet_gbif_layers.csv'
STATUS = ROOT / 'data' / 'territorial_layers' / 'vector_city_distribution_metadata.json'
CITY_SOURCES = [
    ROOT / 'data' / 'source_cities.json',
    ROOT / 'public_html' / 'data' / 'source_cities.json',
    ROOT / 'public_html' / 'data' / 'cities.json',
]

# Fallback list used only if no menu/source city file is present. Replace/extend from source_cities.json when available.
FALLBACK_CITIES = [
    {'name':'Torino','region':'Piemonte','lat':45.0703,'lon':7.6869},
    {'name':'Cuneo','region':'Piemonte','lat':44.3845,'lon':7.5427},
    {'name':'Milano','region':'Lombardia','lat':45.4642,'lon':9.1900},
    {'name':'Pavia','region':'Lombardia','lat':45.1847,'lon':9.1582},
    {'name':'Brescia','region':'Lombardia','lat':45.5416,'lon':10.2118},
    {'name':'Genova','region':'Liguria','lat':44.40478,'lon':8.94439},
    {'name':'Verona','region':'Veneto','lat':45.4384,'lon':10.9916},
    {'name':'Padova','region':'Veneto','lat':45.4064,'lon':11.8768},
    {'name':'Bologna','region':'Emilia-Romagna','lat':44.4949,'lon':11.3426},
    {'name':'Parma','region':'Emilia-Romagna','lat':44.8015,'lon':10.3279},
    {'name':'Firenze','region':'Toscana','lat':43.7696,'lon':11.2558},
    {'name':'Grosseto','region':'Toscana','lat':42.7635,'lon':11.1124},
    {'name':'Roma','region':'Lazio','lat':41.9028,'lon':12.4964},
    {'name':'Napoli','region':'Campania','lat':40.8518,'lon':14.2681},
    {'name':'Caserta','region':'Campania','lat':41.0747,'lon':14.3324},
    {'name':'Bari','region':'Puglia','lat':41.1171,'lon':16.8719},
    {'name':'Palermo','region':'Sicilia','lat':38.1157,'lon':13.3615},
    {'name':'Cagliari','region':'Sardegna','lat':39.2238,'lon':9.1217},
]

FIELDS = ['external_id','category','source','label','scientific_name','data_type','count','period_start','period_end','country','region','province','location','lat','lon','radius_km','color','url_source','notes']

def slug(s: str) -> str:
    s = (s or '').strip().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-') or 'area'

def load_cities():
    for p in CITY_SOURCES:
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                data = data.get('cities') or data.get('items') or data.get('data') or []
            cities = []
            for r in data:
                name = r.get('name') or r.get('city') or r.get('comune') or r.get('label')
                lat = r.get('lat') or r.get('latitude')
                lon = r.get('lon') or r.get('lng') or r.get('longitude')
                if name and lat is not None and lon is not None:
                    cities.append({
                        'name': str(name),
                        'region': str(r.get('region') or r.get('regione') or ''),
                        'province': str(r.get('province') or r.get('provincia') or ''),
                        'lat': float(lat),
                        'lon': float(lon),
                    })
            if cities:
                return cities, str(p)
    return FALLBACK_CITIES, 'embedded_fallback_city_list'

def row_for_city(c):
    name = c['name']
    region = c.get('region','')
    province = c.get('province','')
    return {
        'external_id': f'ECDC-VECTORNET-AEDES-ALBOPICTUS-2026-IT-{slug(name).upper()}',
        'category': 'vectors',
        'source': 'ECDC_VECTORNET',
        'label': 'Aedes albopictus',
        'scientific_name': 'Aedes albopictus',
        'data_type': 'established_distribution_area',
        'count': '1',
        'period_start': '2026-01-01',
        'period_end': '2026-06-03',
        'country': 'Italy',
        'region': region,
        'province': province,
        'location': name,
        'lat': f"{float(c['lat']):.5f}",
        'lon': f"{float(c['lon']):.5f}",
        'radius_km': '30',
        'color': '#7C3AED',
        'url_source': 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/invasive-mosquito-maps',
        'notes': 'Dato reale di distribuzione vettoriale: Aedes albopictus established/known distribution at administrative-area level from ECDC/VectorNet maps; circle centred on menu city for map display; not a disease case and not a punctual mosquito report.'
    }

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cities, source_file = load_cities()
    seen = set()
    rows = []
    for c in cities:
        key = slug(c['name'])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row_for_city(c))
    with OUT.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    STATUS.write_text(json.dumps({
        'source': 'ECDC_VECTORNET',
        'dataset': 'Aedes albopictus current known distribution / invasive mosquito maps',
        'city_source': source_file,
        'rows_written': len(rows),
        'generated_at': date.today().isoformat(),
        'notes': 'Rows are area-level distribution layers centred on cities from the menu/source city file. Counts indicate one established distribution layer, not observation counts.'
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {len(rows)} vector city distribution rows to {OUT}')

if __name__ == '__main__':
    main()
