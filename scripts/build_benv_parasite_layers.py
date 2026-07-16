
#!/usr/bin/env python3
"""Build parasite territorial layers from official BENV/IZS events.

This script reads data/official_sources/izs_benv_events.csv and extracts selected
parasitic diseases (currently Leishmaniosi/Leishmaniasis and configurable aliases)
into data/territorial_layers/benv_parasite_layers.csv.
It does not invent data: it only transforms official BENV rows already present.
"""
import csv
import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

SRC = Path('data/official_sources/izs_benv_events.csv')
OUT = Path('data/territorial_layers/benv_parasite_layers.csv')
META = Path('data/territorial_layers/benv_parasite_layers_metadata.json')

PARASITE_KEYWORDS = {
    'leishmaniosi': ('Leishmania infantum', 'Leishmania infantum'),
    'leishmaniasis': ('Leishmania infantum', 'Leishmania infantum'),
    'filariosi': ('Dirofilaria spp.', 'Dirofilaria spp.'),
    'dirofilaria': ('Dirofilaria spp.', 'Dirofilaria spp.'),
    'giardia': ('Giardia spp.', 'Giardia spp.'),
    'giardiasi': ('Giardia spp.', 'Giardia spp.'),
    'echinococcosi': ('Echinococcus spp.', 'Echinococcus spp.'),
    'echinococcus': ('Echinococcus spp.', 'Echinococcus spp.'),
}

OUT_COLS = ['external_id','source','disease','category','data_type','evidence_count','period_start','period_end','country','region','province','location','lat','lon','radius_km','url_source','notes']

def norm(s):
    return re.sub(r'\s+', ' ', str(s or '').strip()).lower()

def parse_date(s):
    s=str(s or '').strip()
    if not s:
        return ''
    try:
        return datetime.fromisoformat(s[:10]).date().isoformat()
    except Exception:
        return s[:10]

def detect_parasite(row):
    disease = ' '.join([str(row.get('disease','')), str(row.get('disease_it','')), str(row.get('disease_original',''))])
    low = norm(disease)
    for key,(label,scientific) in PARASITE_KEYWORDS.items():
        if key in low:
            return label, scientific
    return None, None

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows=[]
    if not SRC.exists():
        with OUT.open('w', newline='', encoding='utf-8') as f:
            csv.DictWriter(f, fieldnames=OUT_COLS).writeheader()
        META.write_text(json.dumps({'status':'no_source','source':str(SRC),'rows':0}, indent=2), encoding='utf-8')
        print('BENV parasite layers: no source CSV, wrote empty output')
        return

    with SRC.open(newline='', encoding='utf-8') as f:
        reader=csv.DictReader(f)
        for row in reader:
            label, scientific = detect_parasite(row)
            if not label:
                continue
            lat=str(row.get('lat','')).strip(); lon=str(row.get('lon','')).strip()
            if not lat or not lon:
                continue
            loc=row.get('location') or row.get('Comune') or row.get('comune') or ''
            prov=row.get('province') or row.get('Provincia') or row.get('provincia') or ''
            reg=row.get('region') or row.get('Regione') or row.get('regione') or ''
            ext=row.get('external_id') or row.get('ID') or f"BENV-PARASITE-{len(rows)+1:05d}"
            obs=parse_date(row.get('observation_date') or row.get('Data conferma') or row.get('data_conferma'))
            rep=parse_date(row.get('report_date') or obs or date.today().isoformat())
            # city-level official event, local context circle
            notes=(row.get('notes') or '') + '; derived from official BENV/IZS parasitic disease event; territorial context layer, not standalone prevalence estimate'
            rows.append({
                'external_id':f"BENV-PARASITE-{ext}",
                'source':'IZS_BENV',
                'disease':label,
                'category':'parasites',
                'data_type':'official_event_context',
                'evidence_count':'1',
                'period_start':obs or rep,
                'period_end':rep or obs,
                'country':row.get('country') or 'Italy',
                'region':reg,
                'province':prov,
                'location':loc or prov or reg,
                'lat':lat,
                'lon':lon,
                'radius_km':'10' if loc else '50',
                'url_source':row.get('url_source') or 'https://www.izs.it/BENV_NEW/datiemappe.html',
                'notes':notes.strip('; ')
            })

    with OUT.open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=OUT_COLS)
        w.writeheader(); w.writerows(rows)
    by_disease=defaultdict(int)
    by_region=defaultdict(int)
    for r in rows:
        by_disease[r['disease']]+=1; by_region[r['region']]+=1
    META.write_text(json.dumps({
        'status':'success',
        'source':str(SRC),
        'output':str(OUT),
        'rows':len(rows),
        'by_disease':dict(by_disease),
        'by_region':dict(by_region),
        'generated_at':datetime.utcnow().isoformat()+'Z'
    }, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'BENV parasite territorial layers generated: {len(rows)} rows')

if __name__ == '__main__':
    main()
