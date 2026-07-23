#!/usr/bin/env python3
"""
Backend patch v237:
- adds hidden pilot-area municipalities around Cairo Montenotte and broader Liguria/basso Piemonte
- keeps menu simple through show_in_menu=false for non-primary municipalities
- updates /cities so the public menu returns only show_in_menu != false
- adds /cities?include_hidden=true for inspection/debug
Run from backend repository root.
"""
from pathlib import Path
from datetime import datetime
import json
import py_compile
import re

MAIN = Path('main.py')
CITIES = Path('data/source_cities.json')
if not MAIN.exists():
    raise SystemExit('ERROR: main.py not found. Run from backend root.')
if not CITIES.exists():
    raise SystemExit('ERROR: data/source_cities.json not found. Run from backend root.')

stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
main_backup = Path(f'main.before_hidden_pilot_cities_v237_{stamp}.py')
cities_backup = CITIES.with_name(f'source_cities.before_hidden_pilot_cities_v237_{stamp}.json')
main_text = MAIN.read_text(encoding='utf-8')
cities_text = CITIES.read_text(encoding='utf-8')
main_backup.write_text(main_text, encoding='utf-8')
cities_backup.write_text(cities_text, encoding='utf-8')

cities = json.loads(cities_text)
if not isinstance(cities, list):
    raise SystemExit('ERROR: data/source_cities.json must be a JSON array.')

# Main cities remain visible in the menu. Smaller pilot-area towns are hidden from the menu but remain usable for imports/events/layers.
VISIBLE_MENU_CITIES = {
    'torino','milano','roma','napoli','bologna','verona',
    'cairo montenotte','savona','genova','imperia','la spezia',
    'cuneo','asti','alessandria'
}

pilot_cities = [
    # Core pilot municipalities around Cairo Montenotte, Val Bormida and nearby Savona province
    {"name":"Cairo Montenotte","lat":44.3979,"lon":8.2778,"province":"Savona","region":"Liguria","country":"Italy","pilot_center":True,"pilot_area":"Val Bormida - studio pilota","show_in_menu":True},
    {"name":"Carcare","lat":44.3568,"lon":8.2906,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Val Bormida - studio pilota","show_in_menu":False},
    {"name":"Altare","lat":44.3367,"lon":8.3454,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Val Bormida - studio pilota","show_in_menu":False},
    {"name":"Cosseria","lat":44.3674,"lon":8.2352,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Val Bormida - studio pilota","show_in_menu":False},
    {"name":"Millesimo","lat":44.3650,"lon":8.2045,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Val Bormida - studio pilota","show_in_menu":False},
    {"name":"Cengio","lat":44.3896,"lon":8.2099,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Val Bormida - studio pilota","show_in_menu":False},
    {"name":"Dego","lat":44.4439,"lon":8.3076,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Val Bormida - studio pilota","show_in_menu":False},
    {"name":"Roccavignale","lat":44.3611,"lon":8.1904,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Val Bormida - studio pilota","show_in_menu":False},
    {"name":"Pallare","lat":44.3270,"lon":8.2769,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Val Bormida - studio pilota","show_in_menu":False},
    {"name":"Bormida","lat":44.2780,"lon":8.2327,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Val Bormida - studio pilota","show_in_menu":False},
    {"name":"Mallare","lat":44.2943,"lon":8.2969,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Val Bormida - studio pilota","show_in_menu":False},
    {"name":"Plodio","lat":44.3565,"lon":8.2449,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Val Bormida - studio pilota","show_in_menu":False},
    {"name":"Osiglia","lat":44.2819,"lon":8.1997,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Val Bormida - studio pilota","show_in_menu":False},
    # Visible and hidden broader Liguria pilot-area cities already useful for map context
    {"name":"Savona","lat":44.3079,"lon":8.4810,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":True},
    {"name":"Albenga","lat":44.0490,"lon":8.2130,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Alassio","lat":44.0039,"lon":8.1671,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Finale Ligure","lat":44.1695,"lon":8.3446,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Loano","lat":44.1278,"lon":8.2574,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Vado Ligure","lat":44.2695,"lon":8.4335,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Varazze","lat":44.3590,"lon":8.5760,"province":"Savona","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Imperia","lat":43.8897,"lon":8.0396,"province":"Imperia","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":True},
    {"name":"Sanremo","lat":43.8173,"lon":7.7772,"province":"Imperia","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Ventimiglia","lat":43.7912,"lon":7.6076,"province":"Imperia","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Diano Marina","lat":43.9109,"lon":8.0807,"province":"Imperia","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Genova","lat":44.4056,"lon":8.9463,"province":"Genova","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":True},
    {"name":"Arenzano","lat":44.4050,"lon":8.6830,"province":"Genova","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Chiavari","lat":44.3177,"lon":9.3224,"province":"Genova","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Rapallo","lat":44.3496,"lon":9.2270,"province":"Genova","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Lavagna","lat":44.3091,"lon":9.3422,"province":"Genova","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"Sestri Levante","lat":44.2732,"lon":9.3968,"province":"Genova","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    {"name":"La Spezia","lat":44.1025,"lon":9.8241,"province":"La Spezia","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":True},
    {"name":"Sarzana","lat":44.1117,"lon":9.9605,"province":"La Spezia","region":"Liguria","country":"Italy","pilot_area":"Liguria","show_in_menu":False},
    # Basso Piemonte: keep capoluoghi visible; other towns hidden but usable
    {"name":"Cuneo","lat":44.3845,"lon":7.5427,"province":"Cuneo","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":True},
    {"name":"Alba","lat":44.7009,"lon":8.0357,"province":"Cuneo","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Bra","lat":44.6978,"lon":7.8556,"province":"Cuneo","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Fossano","lat":44.5509,"lon":7.7257,"province":"Cuneo","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Mondovì","lat":44.3898,"lon":7.8207,"province":"Cuneo","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Saluzzo","lat":44.6445,"lon":7.4931,"province":"Cuneo","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Savigliano","lat":44.6487,"lon":7.6579,"province":"Cuneo","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Ceva","lat":44.3852,"lon":8.0350,"province":"Cuneo","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Carrù","lat":44.4797,"lon":7.8747,"province":"Cuneo","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Asti","lat":44.9008,"lon":8.2065,"province":"Asti","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":True},
    {"name":"Canelli","lat":44.7218,"lon":8.2923,"province":"Asti","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Nizza Monferrato","lat":44.7743,"lon":8.3578,"province":"Asti","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Villanova d'Asti","lat":44.9428,"lon":7.9367,"province":"Asti","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Alessandria","lat":44.9073,"lon":8.6117,"province":"Alessandria","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":True},
    {"name":"Acqui Terme","lat":44.6755,"lon":8.4693,"province":"Alessandria","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Casale Monferrato","lat":45.1334,"lon":8.4525,"province":"Alessandria","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Novi Ligure","lat":44.7620,"lon":8.7878,"province":"Alessandria","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Tortona","lat":44.8978,"lon":8.8640,"province":"Alessandria","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Ovada","lat":44.6377,"lon":8.6469,"province":"Alessandria","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False},
    {"name":"Valenza","lat":45.0120,"lon":8.6432,"province":"Alessandria","region":"Piemonte","country":"Italy","pilot_area":"Basso Piemonte","show_in_menu":False}
]

by_name = {str(row.get('name','')).strip().lower(): row for row in cities if isinstance(row, dict)}
inserted = 0
updated = 0
for city in pilot_cities:
    key = city['name'].strip().lower()
    city['show_in_menu'] = bool(city.get('show_in_menu', False))
    if key in by_name:
        by_name[key].update(city)
        updated += 1
    else:
        cities.append(city)
        by_name[key] = city
        inserted += 1

# Apply show_in_menu defaults to existing cities. Unknown cities remain visible unless they are pilot-area hidden entries set above.
for row in cities:
    if not isinstance(row, dict):
        continue
    name_key = str(row.get('name','')).strip().lower()
    if 'show_in_menu' not in row:
        row['show_in_menu'] = name_key in VISIBLE_MENU_CITIES

cities.sort(key=lambda r: (0 if r.get('show_in_menu') else 1, str(r.get('region','')), str(r.get('province','')), str(r.get('name','')).lower()))
CITIES.write_text(json.dumps(cities, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

# Patch /cities endpoint to hide show_in_menu=false by default and allow include_hidden=true.
old_inline = '@app.get("/cities")\ndef get_cities(): return {"cities":load_json("data/source_cities.json")}'
new_endpoint = '''@app.get("/cities")
def get_cities(include_hidden: bool = False):
    cities = load_json("data/source_cities.json")
    if not include_hidden:
        cities = [c for c in cities if not isinstance(c, dict) or c.get("show_in_menu", True) is not False]
    return {"cities": cities}'''
if old_inline in main_text:
    main_text = main_text.replace(old_inline, new_endpoint, 1)
elif 'def get_cities(include_hidden: bool = False)' not in main_text:
    # More flexible replacement for a two-line endpoint with the same route.
    pattern = r'@app\.get\("/cities"\)\s*\ndef get_cities\([^\)]*\):\s*return \{"cities":load_json\("data/source_cities\.json"\)\}'
    main_text, n = re.subn(pattern, new_endpoint, main_text, count=1, flags=re.S)
    if n == 0:
        raise SystemExit('ERROR: could not patch /cities endpoint automatically. Please patch manually.')

MAIN.write_text(main_text, encoding='utf-8')
try:
    py_compile.compile(str(MAIN), doraise=True)
except Exception as e:
    MAIN.write_text(main_backup.read_text(encoding='utf-8'), encoding='utf-8')
    CITIES.write_text(cities_backup.read_text(encoding='utf-8'), encoding='utf-8')
    raise SystemExit(f'ERROR: compile failed; restored backups: {e}')

visible_count = sum(1 for c in cities if not isinstance(c, dict) or c.get('show_in_menu', True) is not False)
hidden_count = len(cities) - visible_count
print(json.dumps({
    'status': 'success',
    'inserted': inserted,
    'updated': updated,
    'total_cities': len(cities),
    'visible_menu_cities': visible_count,
    'hidden_cities': hidden_count,
    'main_backup': str(main_backup),
    'cities_backup': str(cities_backup),
    'endpoint': '/cities?include_hidden=true'
}, ensure_ascii=False, indent=2))
