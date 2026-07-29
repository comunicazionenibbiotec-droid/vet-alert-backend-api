#!/usr/bin/env python3
"""
v243 - Rebuild public Home location menu using an embedded complete list of Italian provinces.

Public menu:
  - all Italian provinces
  - Cairo Montenotte

Hidden operational cities already present in data/source_cities.json are preserved for importer/search use,
but kept with show_in_menu=false.

Run from backend root:
  python apply_backend_province_menu_v243.py
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime

SOURCE = Path('data/source_cities.json')

CAIRO = {
    "name": "Cairo Montenotte",
    "lat": 44.3979,
    "lon": 8.2778,
    "province": "Savona",
    "region": "Liguria",
    "country": "Italy",
    "location_type": "municipality",
    "area_type": "comune_pilota",
    "pilot_center": True,
    "pilot_area": "Val Bormida - studio pilota",
    "radius_default_km": 50,
    "notes": "Centro dello studio pilota vet.ector",
    "show_in_menu": True,
}

# Approximate centroids/capital coordinates for Italian provinces and metropolitan cities.
# Purpose: map menu search center. Exact polygon centroids are not required for this use case.
PROVINCES = [
    # Abruzzo
    ("Chieti", "Abruzzo", 42.3510, 14.1675),
    ("L'Aquila", "Abruzzo", 42.3498, 13.3995),
    ("Pescara", "Abruzzo", 42.4618, 14.2161),
    ("Teramo", "Abruzzo", 42.6612, 13.6990),
    # Basilicata
    ("Matera", "Basilicata", 40.6664, 16.6043),
    ("Potenza", "Basilicata", 40.6404, 15.8056),
    # Calabria
    ("Catanzaro", "Calabria", 38.9098, 16.5877),
    ("Cosenza", "Calabria", 39.2983, 16.2537),
    ("Crotone", "Calabria", 39.0808, 17.1271),
    ("Reggio Calabria", "Calabria", 38.1144, 15.6500),
    ("Vibo Valentia", "Calabria", 38.6758, 16.0983),
    # Campania
    ("Avellino", "Campania", 40.9146, 14.7896),
    ("Benevento", "Campania", 41.1298, 14.7827),
    ("Caserta", "Campania", 41.0723, 14.3311),
    ("Napoli", "Campania", 40.8518, 14.2681),
    ("Salerno", "Campania", 40.6824, 14.7681),
    # Emilia-Romagna
    ("Bologna", "Emilia-Romagna", 44.4949, 11.3426),
    ("Ferrara", "Emilia-Romagna", 44.8381, 11.6198),
    ("Forlì-Cesena", "Emilia-Romagna", 44.2227, 12.0407),
    ("Modena", "Emilia-Romagna", 44.6471, 10.9252),
    ("Parma", "Emilia-Romagna", 44.8015, 10.3279),
    ("Piacenza", "Emilia-Romagna", 45.0526, 9.6937),
    ("Ravenna", "Emilia-Romagna", 44.4184, 12.2035),
    ("Reggio Emilia", "Emilia-Romagna", 44.6983, 10.6312),
    ("Rimini", "Emilia-Romagna", 44.0678, 12.5695),
    # Friuli-Venezia Giulia
    ("Gorizia", "Friuli-Venezia Giulia", 45.9415, 13.6220),
    ("Pordenone", "Friuli-Venezia Giulia", 45.9569, 12.6605),
    ("Trieste", "Friuli-Venezia Giulia", 45.6495, 13.7768),
    ("Udine", "Friuli-Venezia Giulia", 46.0711, 13.2346),
    # Lazio
    ("Frosinone", "Lazio", 41.6396, 13.3426),
    ("Latina", "Lazio", 41.4676, 12.9037),
    ("Rieti", "Lazio", 42.4045, 12.8567),
    ("Roma", "Lazio", 41.9028, 12.4964),
    ("Viterbo", "Lazio", 42.4207, 12.1077),
    # Liguria
    ("Genova", "Liguria", 44.4056, 8.9463),
    ("Imperia", "Liguria", 43.8897, 8.0396),
    ("La Spezia", "Liguria", 44.1025, 9.8241),
    ("Savona", "Liguria", 44.3079, 8.4810),
    # Lombardia
    ("Bergamo", "Lombardia", 45.6983, 9.6773),
    ("Brescia", "Lombardia", 45.5416, 10.2118),
    ("Como", "Lombardia", 45.8081, 9.0852),
    ("Cremona", "Lombardia", 45.1332, 10.0227),
    ("Lecco", "Lombardia", 45.8566, 9.3977),
    ("Lodi", "Lombardia", 45.3136, 9.5035),
    ("Mantova", "Lombardia", 45.1564, 10.7914),
    ("Milano", "Lombardia", 45.4642, 9.1900),
    ("Monza e Brianza", "Lombardia", 45.5845, 9.2744),
    ("Pavia", "Lombardia", 45.1847, 9.1582),
    ("Sondrio", "Lombardia", 46.1699, 9.8788),
    ("Varese", "Lombardia", 45.8206, 8.8251),
    # Marche
    ("Ancona", "Marche", 43.6158, 13.5189),
    ("Ascoli Piceno", "Marche", 42.8536, 13.5749),
    ("Fermo", "Marche", 43.1606, 13.7184),
    ("Macerata", "Marche", 43.2984, 13.4531),
    ("Pesaro e Urbino", "Marche", 43.9125, 12.9155),
    # Molise
    ("Campobasso", "Molise", 41.5603, 14.6627),
    ("Isernia", "Molise", 41.5960, 14.2330),
    # Piemonte
    ("Alessandria", "Piemonte", 44.9073, 8.6117),
    ("Asti", "Piemonte", 44.9008, 8.2065),
    ("Biella", "Piemonte", 45.5629, 8.0583),
    ("Cuneo", "Piemonte", 44.3845, 7.5427),
    ("Novara", "Piemonte", 45.4469, 8.6212),
    ("Torino", "Piemonte", 45.0703, 7.6869),
    ("Verbano-Cusio-Ossola", "Piemonte", 45.9214, 8.5518),
    ("Vercelli", "Piemonte", 45.3230, 8.4232),
    # Puglia
    ("Bari", "Puglia", 41.1171, 16.8719),
    ("Barletta-Andria-Trani", "Puglia", 41.2273, 16.2950),
    ("Brindisi", "Puglia", 40.6327, 17.9418),
    ("Foggia", "Puglia", 41.4622, 15.5446),
    ("Lecce", "Puglia", 40.3515, 18.1750),
    ("Taranto", "Puglia", 40.4644, 17.2470),
    # Sardegna
    ("Cagliari", "Sardegna", 39.2238, 9.1217),
    ("Nuoro", "Sardegna", 40.3202, 9.3264),
    ("Oristano", "Sardegna", 39.9038, 8.5912),
    ("Sassari", "Sardegna", 40.7259, 8.5557),
    ("Sud Sardegna", "Sardegna", 39.1667, 8.5220),
    # Sicilia
    ("Agrigento", "Sicilia", 37.3094, 13.5858),
    ("Caltanissetta", "Sicilia", 37.4901, 14.0629),
    ("Catania", "Sicilia", 37.5079, 15.0830),
    ("Enna", "Sicilia", 37.5677, 14.2798),
    ("Messina", "Sicilia", 38.1938, 15.5540),
    ("Palermo", "Sicilia", 38.1157, 13.3615),
    ("Ragusa", "Sicilia", 36.9269, 14.7255),
    ("Siracusa", "Sicilia", 37.0755, 15.2866),
    ("Trapani", "Sicilia", 38.0176, 12.5365),
    # Toscana
    ("Arezzo", "Toscana", 43.4633, 11.8796),
    ("Firenze", "Toscana", 43.7696, 11.2558),
    ("Grosseto", "Toscana", 42.7635, 11.1124),
    ("Livorno", "Toscana", 43.5485, 10.3106),
    ("Lucca", "Toscana", 43.8429, 10.5027),
    ("Massa-Carrara", "Toscana", 44.0354, 10.1397),
    ("Pisa", "Toscana", 43.7228, 10.4017),
    ("Pistoia", "Toscana", 43.9303, 10.9079),
    ("Prato", "Toscana", 43.8777, 11.1022),
    ("Siena", "Toscana", 43.3188, 11.3308),
    # Trentino-Alto Adige
    ("Bolzano", "Trentino-Alto Adige", 46.4983, 11.3548),
    ("Trento", "Trentino-Alto Adige", 46.0748, 11.1217),
    # Umbria
    ("Perugia", "Umbria", 43.1107, 12.3908),
    ("Terni", "Umbria", 42.5636, 12.6427),
    # Valle d'Aosta
    ("Aosta", "Valle d'Aosta", 45.7376, 7.3172),
    # Veneto
    ("Belluno", "Veneto", 46.1425, 12.2167),
    ("Padova", "Veneto", 45.4064, 11.8768),
    ("Rovigo", "Veneto", 45.0698, 11.7902),
    ("Treviso", "Veneto", 45.6669, 12.2430),
    ("Venezia", "Veneto", 45.4408, 12.3155),
    ("Verona", "Veneto", 45.4384, 10.9916),
    ("Vicenza", "Veneto", 45.5455, 11.5354),
]

MOJIBAKE_FIXES = {
    'Carr├╣': 'Carrù',
    'Mondov├¼': 'Mondovì',
    'Forli-Cesena': 'Forlì-Cesena',
}

def read_current():
    if not SOURCE.exists():
        raise SystemExit('data/source_cities.json not found')
    return json.loads(SOURCE.read_text(encoding='utf-8'))

def fixed_name(name):
    name = str(name or '').strip()
    return MOJIBAKE_FIXES.get(name, name)

def province_row(province, region, lat, lon):
    return {
        'name': f'Provincia di {province}',
        'lat': float(lat),
        'lon': float(lon),
        'province': province,
        'region': region,
        'country': 'Italy',
        'location_type': 'province',
        'area_type': 'provincia',
        'radius_default_km': 75,
        'show_in_menu': True,
    }

def main():
    current = read_current()
    backup = SOURCE.with_name(f'source_cities.before_province_menu_v243_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.json')
    backup.write_text(SOURCE.read_text(encoding='utf-8'), encoding='utf-8')

    visible_provinces = [province_row(*p) for p in PROVINCES]

    hidden = []
    for row in current:
        if not isinstance(row, dict):
            continue
        row = dict(row)
        row['name'] = fixed_name(row.get('name'))
        if row['name'] == 'Cairo Montenotte':
            continue
        # Preserve only entries that were intentionally hidden or operational/pilot.
        if row.get('show_in_menu') is False or row.get('pilot_area') or row.get('pilot_center'):
            row['show_in_menu'] = False
            hidden.append(row)

    combined = []
    seen = set()
    for row in sorted(visible_provinces, key=lambda x: (x['region'], x['province'])):
        key = ('province', row['province'])
        if key not in seen:
            seen.add(key)
            combined.append(row)

    combined.append(CAIRO)
    seen.add(('municipality', 'Cairo Montenotte'))

    for row in hidden:
        key = ('hidden', row.get('name'), row.get('province',''), row.get('region',''))
        if key not in seen:
            seen.add(key)
            combined.append(row)

    SOURCE.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    visible = sum(1 for x in combined if x.get('show_in_menu') is not False)
    hidden_count = len(combined) - visible
    print(json.dumps({
        'status': 'success',
        'source_cities': str(SOURCE),
        'backup': str(backup),
        'visible_menu_entries': visible,
        'province_menu_entries': len(visible_provinces),
        'hidden_operational_entries': hidden_count,
        'cairo_included': True
    }, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
