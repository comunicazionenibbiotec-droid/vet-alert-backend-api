#!/usr/bin/env python3
"""
v242 - Rebuild source_cities.json for the public Home menu.
Public menu: all Italian provinces + Cairo Montenotte.
Hidden operational cities already present in source_cities.json are preserved for imports/search.

Run from backend root:
  python apply_backend_province_menu_v242.py
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime

SOURCE = Path('data/source_cities.json')
CENTROIDS = Path('data/province_centroids_italy_minimal.json')

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

PROVINCE_REGION_FALLBACK = {
    # Abruzzo
    "Chieti":"Abruzzo", "L'Aquila":"Abruzzo", "Pescara":"Abruzzo", "Teramo":"Abruzzo",
    # Basilicata
    "Matera":"Basilicata", "Potenza":"Basilicata",
    # Calabria
    "Catanzaro":"Calabria", "Cosenza":"Calabria", "Crotone":"Calabria", "Reggio Calabria":"Calabria", "Vibo Valentia":"Calabria",
    # Campania
    "Avellino":"Campania", "Benevento":"Campania", "Caserta":"Campania", "Napoli":"Campania", "Salerno":"Campania",
    # Emilia-Romagna
    "Bologna":"Emilia-Romagna", "Ferrara":"Emilia-Romagna", "Forli-Cesena":"Emilia-Romagna", "Modena":"Emilia-Romagna", "Parma":"Emilia-Romagna", "Piacenza":"Emilia-Romagna", "Ravenna":"Emilia-Romagna", "Reggio Emilia":"Emilia-Romagna", "Rimini":"Emilia-Romagna",
    # Friuli-Venezia Giulia
    "Gorizia":"Friuli-Venezia Giulia", "Pordenone":"Friuli-Venezia Giulia", "Trieste":"Friuli-Venezia Giulia", "Udine":"Friuli-Venezia Giulia",
    # Lazio
    "Frosinone":"Lazio", "Latina":"Lazio", "Rieti":"Lazio", "Roma":"Lazio", "Viterbo":"Lazio",
    # Liguria
    "Genova":"Liguria", "Imperia":"Liguria", "La Spezia":"Liguria", "Savona":"Liguria",
    # Lombardia
    "Bergamo":"Lombardia", "Brescia":"Lombardia", "Como":"Lombardia", "Cremona":"Lombardia", "Lecco":"Lombardia", "Lodi":"Lombardia", "Mantova":"Lombardia", "Milano":"Lombardia", "Monza e Brianza":"Lombardia", "Pavia":"Lombardia", "Sondrio":"Lombardia", "Varese":"Lombardia",
    # Marche
    "Ancona":"Marche", "Ascoli Piceno":"Marche", "Fermo":"Marche", "Macerata":"Marche", "Pesaro e Urbino":"Marche",
    # Molise
    "Campobasso":"Molise", "Isernia":"Molise",
    # Piemonte
    "Alessandria":"Piemonte", "Asti":"Piemonte", "Biella":"Piemonte", "Cuneo":"Piemonte", "Novara":"Piemonte", "Torino":"Piemonte", "Verbano-Cusio-Ossola":"Piemonte", "Vercelli":"Piemonte",
    # Puglia
    "Bari":"Puglia", "Barletta-Andria-Trani":"Puglia", "Brindisi":"Puglia", "Foggia":"Puglia", "Lecce":"Puglia", "Taranto":"Puglia",
    # Sardegna
    "Cagliari":"Sardegna", "Nuoro":"Sardegna", "Oristano":"Sardegna", "Sassari":"Sardegna", "Sud Sardegna":"Sardegna",
    # Sicilia
    "Agrigento":"Sicilia", "Caltanissetta":"Sicilia", "Catania":"Sicilia", "Enna":"Sicilia", "Messina":"Sicilia", "Palermo":"Sicilia", "Ragusa":"Sicilia", "Siracusa":"Sicilia", "Trapani":"Sicilia",
    # Toscana
    "Arezzo":"Toscana", "Firenze":"Toscana", "Grosseto":"Toscana", "Livorno":"Toscana", "Lucca":"Toscana", "Massa-Carrara":"Toscana", "Pisa":"Toscana", "Pistoia":"Toscana", "Prato":"Toscana", "Siena":"Toscana",
    # Trentino-Alto Adige
    "Bolzano":"Trentino-Alto Adige", "Trento":"Trentino-Alto Adige",
    # Umbria
    "Perugia":"Umbria", "Terni":"Umbria",
    # Valle d'Aosta
    "Aosta":"Valle d'Aosta",
    # Veneto
    "Belluno":"Veneto", "Padova":"Veneto", "Rovigo":"Veneto", "Treviso":"Veneto", "Venezia":"Veneto", "Verona":"Veneto", "Vicenza":"Veneto",
}

def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default

def norm_name(s):
    return str(s or '').strip()

def extract_centroid_entries(payload):
    """Accept several common JSON shapes and return province entries."""
    entries = []
    if isinstance(payload, list):
        source_iter = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get('provinces'), list):
            source_iter = payload['provinces']
        elif isinstance(payload.get('items'), list):
            source_iter = payload['items']
        else:
            source_iter = []
            for key, value in payload.items():
                if isinstance(value, dict):
                    row = dict(value)
                    row.setdefault('province', key)
                    source_iter.append(row)
    else:
        source_iter = []

    for row in source_iter:
        if not isinstance(row, dict):
            continue
        province = norm_name(row.get('province') or row.get('provincia') or row.get('name') or row.get('nome') or row.get('sigla'))
        if not province:
            continue
        try:
            lat = float(row.get('lat') if row.get('lat') is not None else row.get('latitude'))
            lon = float(row.get('lon') if row.get('lon') is not None else row.get('lng') if row.get('lng') is not None else row.get('longitude'))
        except Exception:
            continue
        region = norm_name(row.get('region') or row.get('regione') or PROVINCE_REGION_FALLBACK.get(province, ''))
        entries.append({
            'name': f'Provincia di {province}',
            'lat': lat,
            'lon': lon,
            'province': province,
            'region': region,
            'country': 'Italy',
            'location_type': 'province',
            'area_type': 'provincia',
            'radius_default_km': 75,
            'show_in_menu': True,
        })
    return entries

def de_mojibake(name):
    fixes = {
        'Carr├╣': 'Carrù',
        'Mondov├¼': 'Mondovì',
        'Forli-Cesena': 'Forlì-Cesena',
    }
    return fixes.get(name, name)

def main():
    if not SOURCE.exists():
        raise SystemExit('data/source_cities.json not found')
    if not CENTROIDS.exists():
        raise SystemExit('data/province_centroids_italy_minimal.json not found. Cannot build all-province menu safely.')

    backup = SOURCE.with_name(f'source_cities.before_province_menu_v242_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.json')
    backup.write_text(SOURCE.read_text(encoding='utf-8'), encoding='utf-8')

    current = read_json(SOURCE, [])
    centroid_payload = read_json(CENTROIDS, [])
    province_entries = extract_centroid_entries(centroid_payload)
    if len(province_entries) < 90:
        raise SystemExit(f'Only {len(province_entries)} province entries found in {CENTROIDS}; expected at least 90. Aborting.')

    # Preserve hidden operational municipalities/cities for imports, but keep them hidden in menu.
    hidden_operational = []
    for row in current:
        if not isinstance(row, dict):
            continue
        name = de_mojibake(norm_name(row.get('name')))
        row['name'] = name
        if name == 'Cairo Montenotte':
            continue
        if row.get('show_in_menu') is False:
            hidden_operational.append(row)

    # Remove duplicates by (name, type/province), preference order: provinces, Cairo, hidden.
    combined = []
    seen = set()
    for row in sorted(province_entries, key=lambda x: (x.get('region',''), x.get('province',''))):
        key = ('province', row.get('province'))
        if key not in seen:
            seen.add(key)
            combined.append(row)
    combined.append(CAIRO)
    seen.add(('municipality', 'Cairo Montenotte'))
    for row in hidden_operational:
        key = ('hidden', row.get('name'), row.get('province', ''), row.get('region', ''))
        if key not in seen:
            seen.add(key)
            row['show_in_menu'] = False
            combined.append(row)

    SOURCE.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    visible = sum(1 for x in combined if x.get('show_in_menu') is not False)
    hidden = len(combined) - visible
    print(json.dumps({
        'status': 'success',
        'source_cities': str(SOURCE),
        'backup': str(backup),
        'province_entries_visible': len(province_entries),
        'visible_menu_entries': visible,
        'hidden_operational_entries': hidden,
        'cairo_included': True
    }, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
