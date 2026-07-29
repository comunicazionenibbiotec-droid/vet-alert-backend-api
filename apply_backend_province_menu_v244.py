#!/usr/bin/env python3
"""
v244 - Public Home menu: Italian provincial capitals by name only, sorted alphabetically, plus Cairo Montenotte.

Behavior:
- public /cities menu shows entries named "Alessandria", "Ancona", "Aosta", ... not "Provincia di ...";
- entries are sorted alphabetically by displayed name;
- Cairo Montenotte remains visible in the menu;
- hidden operational municipalities already present in data/source_cities.json are preserved with show_in_menu=false.

Run from backend root:
  python apply_backend_province_menu_v244.py
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

# Display name is the provincial capital/province name shown in the Home menu.
# For metropolitan/province names with compound official names, the display label stays concise and user-friendly.
LOCATIONS = [
    # Abruzzo
    ("Chieti", "Chieti", "Abruzzo", 42.3510, 14.1675),
    ("L'Aquila", "L'Aquila", "Abruzzo", 42.3498, 13.3995),
    ("Pescara", "Pescara", "Abruzzo", 42.4618, 14.2161),
    ("Teramo", "Teramo", "Abruzzo", 42.6612, 13.6990),
    # Basilicata
    ("Matera", "Matera", "Basilicata", 40.6664, 16.6043),
    ("Potenza", "Potenza", "Basilicata", 40.6404, 15.8056),
    # Calabria
    ("Catanzaro", "Catanzaro", "Calabria", 38.9098, 16.5877),
    ("Cosenza", "Cosenza", "Calabria", 39.2983, 16.2537),
    ("Crotone", "Crotone", "Calabria", 39.0808, 17.1271),
    ("Reggio Calabria", "Reggio Calabria", "Calabria", 38.1144, 15.6500),
    ("Vibo Valentia", "Vibo Valentia", "Calabria", 38.6758, 16.0983),
    # Campania
    ("Avellino", "Avellino", "Campania", 40.9146, 14.7896),
    ("Benevento", "Benevento", "Campania", 41.1298, 14.7827),
    ("Caserta", "Caserta", "Campania", 41.0723, 14.3311),
    ("Napoli", "Napoli", "Campania", 40.8518, 14.2681),
    ("Salerno", "Salerno", "Campania", 40.6824, 14.7681),
    # Emilia-Romagna
    ("Bologna", "Bologna", "Emilia-Romagna", 44.4949, 11.3426),
    ("Ferrara", "Ferrara", "Emilia-Romagna", 44.8381, 11.6198),
    ("Forlì-Cesena", "Forlì-Cesena", "Emilia-Romagna", 44.2227, 12.0407),
    ("Modena", "Modena", "Emilia-Romagna", 44.6471, 10.9252),
    ("Parma", "Parma", "Emilia-Romagna", 44.8015, 10.3279),
    ("Piacenza", "Piacenza", "Emilia-Romagna", 45.0526, 9.6937),
    ("Ravenna", "Ravenna", "Emilia-Romagna", 44.4184, 12.2035),
    ("Reggio Emilia", "Reggio Emilia", "Emilia-Romagna", 44.6983, 10.6312),
    ("Rimini", "Rimini", "Emilia-Romagna", 44.0678, 12.5695),
    # Friuli-Venezia Giulia
    ("Gorizia", "Gorizia", "Friuli-Venezia Giulia", 45.9415, 13.6220),
    ("Pordenone", "Pordenone", "Friuli-Venezia Giulia", 45.9569, 12.6605),
    ("Trieste", "Trieste", "Friuli-Venezia Giulia", 45.6495, 13.7768),
    ("Udine", "Udine", "Friuli-Venezia Giulia", 46.0711, 13.2346),
    # Lazio
    ("Frosinone", "Frosinone", "Lazio", 41.6396, 13.3426),
    ("Latina", "Latina", "Lazio", 41.4676, 12.9037),
    ("Rieti", "Rieti", "Lazio", 42.4045, 12.8567),
    ("Roma", "Roma", "Lazio", 41.9028, 12.4964),
    ("Viterbo", "Viterbo", "Lazio", 42.4207, 12.1077),
    # Liguria
    ("Genova", "Genova", "Liguria", 44.4056, 8.9463),
    ("Imperia", "Imperia", "Liguria", 43.8897, 8.0396),
    ("La Spezia", "La Spezia", "Liguria", 44.1025, 9.8241),
    ("Savona", "Savona", "Liguria", 44.3079, 8.4810),
    # Lombardia
    ("Bergamo", "Bergamo", "Lombardia", 45.6983, 9.6773),
    ("Brescia", "Brescia", "Lombardia", 45.5416, 10.2118),
    ("Como", "Como", "Lombardia", 45.8081, 9.0852),
    ("Cremona", "Cremona", "Lombardia", 45.1332, 10.0227),
    ("Lecco", "Lecco", "Lombardia", 45.8566, 9.3977),
    ("Lodi", "Lodi", "Lombardia", 45.3136, 9.5035),
    ("Mantova", "Mantova", "Lombardia", 45.1564, 10.7914),
    ("Milano", "Milano", "Lombardia", 45.4642, 9.1900),
    ("Monza e Brianza", "Monza e Brianza", "Lombardia", 45.5845, 9.2744),
    ("Pavia", "Pavia", "Lombardia", 45.1847, 9.1582),
    ("Sondrio", "Sondrio", "Lombardia", 46.1699, 9.8788),
    ("Varese", "Varese", "Lombardia", 45.8206, 8.8251),
    # Marche
    ("Ancona", "Ancona", "Marche", 43.6158, 13.5189),
    ("Ascoli Piceno", "Ascoli Piceno", "Marche", 42.8536, 13.5749),
    ("Fermo", "Fermo", "Marche", 43.1606, 13.7184),
    ("Macerata", "Macerata", "Marche", 43.2984, 13.4531),
    ("Pesaro e Urbino", "Pesaro e Urbino", "Marche", 43.9125, 12.9155),
    # Molise
    ("Campobasso", "Campobasso", "Molise", 41.5603, 14.6627),
    ("Isernia", "Isernia", "Molise", 41.5960, 14.2330),
    # Piemonte
    ("Alessandria", "Alessandria", "Piemonte", 44.9073, 8.6117),
    ("Asti", "Asti", "Piemonte", 44.9008, 8.2065),
    ("Biella", "Biella", "Piemonte", 45.5629, 8.0583),
    ("Cuneo", "Cuneo", "Piemonte", 44.3845, 7.5427),
    ("Novara", "Novara", "Piemonte", 45.4469, 8.6212),
    ("Torino", "Torino", "Piemonte", 45.0703, 7.6869),
    ("Verbano-Cusio-Ossola", "Verbano-Cusio-Ossola", "Piemonte", 45.9214, 8.5518),
    ("Vercelli", "Vercelli", "Piemonte", 45.3230, 8.4232),
    # Puglia
    ("Bari", "Bari", "Puglia", 41.1171, 16.8719),
    ("Andria", "Barletta-Andria-Trani", "Puglia", 41.2273, 16.2950),
    ("Brindisi", "Brindisi", "Puglia", 40.6327, 17.9418),
    ("Foggia", "Foggia", "Puglia", 41.4622, 15.5446),
    ("Lecce", "Lecce", "Puglia", 40.3515, 18.1750),
    ("Taranto", "Taranto", "Puglia", 40.4644, 17.2470),
    # Sardegna
    ("Cagliari", "Cagliari", "Sardegna", 39.2238, 9.1217),
    ("Nuoro", "Nuoro", "Sardegna", 40.3202, 9.3264),
    ("Oristano", "Oristano", "Sardegna", 39.9038, 8.5912),
    ("Sassari", "Sassari", "Sardegna", 40.7259, 8.5557),
    ("Carbonia", "Sud Sardegna", "Sardegna", 39.1667, 8.5220),
    # Sicilia
    ("Agrigento", "Agrigento", "Sicilia", 37.3094, 13.5858),
    ("Caltanissetta", "Caltanissetta", "Sicilia", 37.4901, 14.0629),
    ("Catania", "Catania", "Sicilia", 37.5079, 15.0830),
    ("Enna", "Enna", "Sicilia", 37.5677, 14.2798),
    ("Messina", "Messina", "Sicilia", 38.1938, 15.5540),
    ("Palermo", "Palermo", "Sicilia", 38.1157, 13.3615),
    ("Ragusa", "Ragusa", "Sicilia", 36.9269, 14.7255),
    ("Siracusa", "Siracusa", "Sicilia", 37.0755, 15.2866),
    ("Trapani", "Trapani", "Sicilia", 38.0176, 12.5365),
    # Toscana
    ("Arezzo", "Arezzo", "Toscana", 43.4633, 11.8796),
    ("Firenze", "Firenze", "Toscana", 43.7696, 11.2558),
    ("Grosseto", "Grosseto", "Toscana", 42.7635, 11.1124),
    ("Livorno", "Livorno", "Toscana", 43.5485, 10.3106),
    ("Lucca", "Lucca", "Toscana", 43.8429, 10.5027),
    ("Massa", "Massa-Carrara", "Toscana", 44.0354, 10.1397),
    ("Pisa", "Pisa", "Toscana", 43.7228, 10.4017),
    ("Pistoia", "Pistoia", "Toscana", 43.9303, 10.9079),
    ("Prato", "Prato", "Toscana", 43.8777, 11.1022),
    ("Siena", "Siena", "Toscana", 43.3188, 11.3308),
    # Trentino-Alto Adige
    ("Bolzano", "Bolzano", "Trentino-Alto Adige", 46.4983, 11.3548),
    ("Trento", "Trento", "Trentino-Alto Adige", 46.0748, 11.1217),
    # Umbria
    ("Perugia", "Perugia", "Umbria", 43.1107, 12.3908),
    ("Terni", "Terni", "Umbria", 42.5636, 12.6427),
    # Valle d'Aosta
    ("Aosta", "Aosta", "Valle d'Aosta", 45.7376, 7.3172),
    # Veneto
    ("Belluno", "Belluno", "Veneto", 46.1425, 12.2167),
    ("Padova", "Padova", "Veneto", 45.4064, 11.8768),
    ("Rovigo", "Rovigo", "Veneto", 45.0698, 11.7902),
    ("Treviso", "Treviso", "Veneto", 45.6669, 12.2430),
    ("Venezia", "Venezia", "Veneto", 45.4408, 12.3155),
    ("Verona", "Verona", "Veneto", 45.4384, 10.9916),
    ("Vicenza", "Vicenza", "Veneto", 45.5455, 11.5354),
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

def menu_row(display_name, province, region, lat, lon):
    return {
        'name': display_name,
        'lat': float(lat),
        'lon': float(lon),
        'province': province,
        'region': region,
        'country': 'Italy',
        'location_type': 'province_capital',
        'area_type': 'provincia',
        'radius_default_km': 75,
        'show_in_menu': True,
    }

def main():
    current = read_current()
    backup = SOURCE.with_name(f'source_cities.before_province_menu_v244_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.json')
    backup.write_text(SOURCE.read_text(encoding='utf-8'), encoding='utf-8')

    visible = [menu_row(*p) for p in LOCATIONS]
    visible.append(CAIRO)
    visible = sorted(visible, key=lambda x: x['name'].casefold())

    hidden = []
    visible_names = {x['name'] for x in visible}
    for row in current:
        if not isinstance(row, dict):
            continue
        row = dict(row)
        row['name'] = fixed_name(row.get('name'))
        if row['name'] in visible_names:
            continue
        if row.get('show_in_menu') is False or row.get('pilot_area') or row.get('pilot_center'):
            row['show_in_menu'] = False
            hidden.append(row)

    combined = []
    seen = set()
    for row in visible:
        key = ('visible', row.get('name'))
        if key not in seen:
            seen.add(key)
            combined.append(row)
    for row in hidden:
        key = ('hidden', row.get('name'), row.get('province',''), row.get('region',''))
        if key not in seen:
            seen.add(key)
            combined.append(row)

    SOURCE.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    public_names = [x['name'] for x in combined if x.get('show_in_menu') is not False]
    print(json.dumps({
        'status': 'success',
        'source_cities': str(SOURCE),
        'backup': str(backup),
        'visible_menu_entries': len(public_names),
        'hidden_operational_entries': len(combined) - len(public_names),
        'first_visible_entries': public_names[:15],
        'last_visible_entries': public_names[-15:],
        'cairo_included': 'Cairo Montenotte' in public_names,
        'province_prefix_removed': not any(name.startswith('Provincia di ') for name in public_names)
    }, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
