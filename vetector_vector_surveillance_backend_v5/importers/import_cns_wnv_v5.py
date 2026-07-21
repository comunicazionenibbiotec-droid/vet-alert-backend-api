"""CNS WNV prevention measure importer.
Reuse/extend the v1 logic. Requires a complete province centroids JSON for production."""
import json
import os
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from common_v5 import db, finish_run, stable_id, start_run, upsert_layer

SOURCE_ID = 'cns_wnv'
DEFAULT_URL = 'https://www.centronazionalesangue.it/west-nile-virus-2025/'
CENTROIDS_JSON = os.getenv('PROVINCE_CENTROIDS_JSON', 'data/province_centroids_italy_minimal.json')
PROVINCE_PATTERN = re.compile(r'(?:provincia|province)\s+di\s+([^\n\r]+)', re.IGNORECASE)


def load_centroids():
    return json.loads(Path(CENTROIDS_JSON).read_text(encoding='utf-8'))


def split_provinces(text):
    text = re.sub(r'\([^)]*\)', '', text).replace(' e ', ',')
    return [p.strip(' .;:-') for p in text.split(',') if p.strip(' .;:-')]


def fetch_items(url):
    html = requests.get(url, timeout=30, headers={'User-Agent': 'vetector-cns-wnv-importer/5.0'}).text
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for node in soup.find_all(['li','p','a','td']):
        text = ' '.join(node.get_text(' ', strip=True).split())
        if ('WNV' in text or 'West Nile' in text) and ('provincia' in text or 'province' in text or 'prevenzione' in text):
            out.append(text)
    return out


def main():
    url = os.getenv('CNS_WNV_URL', DEFAULT_URL)
    centroids = load_centroids()
    items = fetch_items(url)
    inserted = 0
    with db() as conn:
        run_id = start_run(conn, SOURCE_ID, {'url': url})
        try:
            for text in items:
                m = PROVINCE_PATTERN.search(text)
                if not m:
                    continue
                for province in split_provinces(m.group(1)):
                    meta = centroids.get(province)
                    if not meta:
                        continue
                    upsert_layer(conn, {
                        'id': 'cns-wnv-' + stable_id(province, text),
                        'category': 'west_nile',
                        'label': 'West Nile / CNS prevention measure',
                        'scientific_name': None,
                        'data_type': 'blood_donation_prevention_area',
                        'count': 1,
                        'count_label': 'CNS prevention measure',
                        'country': 'Italy',
                        'region': meta.get('region'),
                        'province': province,
                        'location': province,
                        'lat': meta['lat'],
                        'lon': meta['lon'],
                        'radius_km': 50,
                        'aggregation_level': 'province',
                        'source': 'CNS WNV',
                        'display_source': 'Centro Nazionale Sangue',
                        'period_start': None,
                        'period_end': None,
                        'url_source': url,
                        'notes': text,
                        'raw_payload': json.dumps({'source_text': text}, ensure_ascii=False),
                    })
                    inserted += 1
            conn.commit()
            finish_run(conn, run_id, 'success', fetched=len(items), inserted=inserted)
        except Exception as exc:
            conn.rollback()
            finish_run(conn, run_id, 'failed', fetched=len(items), inserted=inserted, error=str(exc))
            raise
    print(json.dumps({'source': SOURCE_ID, 'items': len(items), 'inserted': inserted}, ensure_ascii=False))

if __name__ == '__main__':
    main()
