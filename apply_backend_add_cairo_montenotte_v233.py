#!/usr/bin/env python3
"""
Add Cairo Montenotte (SV) to backend /cities source list.
Run from backend root where data/source_cities.json is located.
"""
from pathlib import Path
from datetime import datetime
import json

path = Path('data/source_cities.json')
if not path.exists():
    raise SystemExit('ERROR: data/source_cities.json not found. Run from backend root.')
backup = path.with_name(f'source_cities.before_cairo_montenotte_v233_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.json')
text = path.read_text(encoding='utf-8')
backup.write_text(text, encoding='utf-8')
try:
    data = json.loads(text)
except Exception as e:
    raise SystemExit(f'ERROR: cannot parse data/source_cities.json: {e}')
if not isinstance(data, list):
    raise SystemExit('ERROR: data/source_cities.json must be a JSON array.')

city = {
    "name": "Cairo Montenotte",
    "lat": 44.3979,
    "lon": 8.2778,
    "province": "Savona",
    "region": "Liguria",
    "country": "Italy",
    "pilot_center": True,
    "notes": "Centro dello studio pilota vet.ector"
}

found = False
for row in data:
    if str(row.get('name','')).strip().lower() == 'cairo montenotte':
        row.update(city)
        found = True
        break
if not found:
    data.append(city)

data.sort(key=lambda r: str(r.get('name','')).lower())
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('OK: Cairo Montenotte added/updated in data/source_cities.json')
print(f'Backup: {backup}')
print('City: Cairo Montenotte, province Savona, region Liguria, lat 44.3979, lon 8.2778')
