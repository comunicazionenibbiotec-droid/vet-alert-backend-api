#!/usr/bin/env python3
"""
vet.ector frontend patch v220 - clean backend ui_group filters

Run from the frontend/public root where these files exist:
  index.html
  js/config.js
  js/report-prefill-v82.js

What this patch does:
- Replaces old territorial checkboxes with backend-driven groups:
  Flebotomi, Zecche, Zanzare / altri vettori, Parassiti, West Nile
- Filters using layer.ui_group / layer.subcategory from backend.
- Does NOT infer vector groups from labels/species in the browser.
- Does NOT call /vector-occurrences.
- Does NOT modify coordinates or backend data.
- Uses display_radius_km when present, otherwise radius_km.
"""
from pathlib import Path
from datetime import datetime
import re
import sys

ROOT = Path('.')
INDEX = ROOT / 'index.html'
CONFIG = ROOT / 'js' / 'config.js'
REPORT = ROOT / 'js' / 'report-prefill-v82.js'

for p in [INDEX, CONFIG, REPORT]:
    if not p.exists():
        raise SystemExit(f'ERROR: missing {p}. Run this script from the frontend public root.')

stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
for p in [INDEX, CONFIG, REPORT]:
    backup = p.with_name(p.name + f'.before_ui_group_filters_v220_{stamp}')
    backup.write_text(p.read_text(encoding='utf-8'), encoding='utf-8')

js = REPORT.read_text(encoding='utf-8')
js = re.sub(r'// vet\.ector report prefill \+ territorial layers - .*', '// vet.ector report prefill + territorial layers - v220 backend ui_group filters', js, count=1)

# Replace META block.
meta_re = r"  const META = \{.*?\n  \};"
meta_new = """  const META = {
    sand_flies: { label: 'Flebotomi', color: '#F26522', icon: '🦟', note: 'Vettori rilevanti per Leishmania.' },
    ticks: { label: 'Zecche', color: '#7C3AED', icon: '●', note: 'Ectoparassiti e vettori di patogeni trasmessi da zecca.' },
    mosquitoes_other_vectors: { label: 'Zanzare / altri vettori', color: '#2563EB', icon: '🦟', note: 'Zanzare e altri artropodi vettori.' },
    parasites: { label: 'Parassiti', color: '#059669', icon: '🧫', note: 'Dato parassitologico aggregato.' },
    west_nile: { label: 'West Nile', color: '#F59E0B', icon: '🦟', note: 'Sorveglianza West Nile / Usutu.' }
  };"""
js, n = re.subn(meta_re, meta_new, js, count=1, flags=re.S)
if n != 1:
    raise SystemExit('ERROR: could not replace META block.')

# Replace territorialInfoUrl and insert backend group helper.
info_re = r"  function territorialInfoUrl\(cat\)\{.*?\n  \}"
info_new = """  function territorialInfoUrl(cat){
    const q = cat === 'sand_flies' ? 'flebotomi leishmaniosi' : cat === 'ticks' ? 'zecche' : cat === 'mosquitoes_other_vectors' ? 'zanzare vettori' : cat === 'parasites' ? 'parassiti' : cat === 'west_nile' ? 'west nile' : cat;
    return '/patologie/?q=' + encodeURIComponent(q);
  }
  function layerGroupKey(item){
    const group = String((item && (item.ui_group || item.subcategory)) || '').trim();
    if(group && META[group]) return group;
    const cat = String((item && item.category) || '').trim();
    if(cat === 'vectors') return 'mosquitoes_other_vectors';
    if(cat === 'parasites') return 'parasites';
    if(cat === 'west_nile') return 'west_nile';
    return cat && META[cat] ? cat : 'mosquitoes_other_vectors';
  }
  function layerDisplayRadiusKm(item){
    const d = Number(item && item.display_radius_km);
    if(Number.isFinite(d) && d > 0) return d;
    const r = Number(item && item.radius_km);
    return Number.isFinite(r) && r > 0 ? r : 10;
  }"""
js, n = re.subn(info_re, info_new, js, count=1, flags=re.S)
if n != 1:
    raise SystemExit('ERROR: could not replace territorialInfoUrl block.')

# Replace relevant() to use backend group key and radius helper.
rel_re = r"  function relevant\(\)\{.*?\n  function injectControls"
rel_new = """  function relevant(){ const sel=new Set(selected()); if(!sel.size) return []; const c=city(), r=radiusKm(); return data.filter(i => sel.has(layerGroupKey(i)) && distKm(c,{lat:Number(i.lat),lon:Number(i.lon)}) <= r + layerDisplayRadiusKm(i)); }
  function injectControls"""
js, n = re.subn(rel_re, rel_new, js, count=1, flags=re.S)
if n != 1:
    raise SystemExit('ERROR: could not replace relevant function.')

# Replace aggregate category assignment and bucket key logic.
js = js.replace('const key = i.category + \'|\' + areaKeyForLayer(i);', 'const key = layerGroupKey(i) + \'|\' + areaKeyForLayer(i);')
js = js.replace('const cat = list[0].category;', 'const cat = layerGroupKey(list[0]);')
js = js.replace('base_category: list[0].category || cat', 'base_category: list[0].category || cat')

# Use display radius in radiusForAggregate if function present.
rad_re = r"  function radiusForAggregate\(cat, list\)\{.*?\n  \}\n  function aggregateTerritorialItems"
rad_new = """  function radiusForAggregate(cat, list){
    const explicit = (list || []).map(layerDisplayRadiusKm).filter(n => Number.isFinite(n) && n > 0);
    if(explicit.length) return Math.max(...explicit);
    const levels = list.map(layerPrecision);
    if(levels.includes('region')) return Number(window.VETECTOR_TERRITORIAL_REGION_RADIUS_KM || 90);
    if(levels.includes('province')) return Number(window.VETECTOR_TERRITORIAL_PROVINCE_RADIUS_KM || 50);
    return Number(window.VETECTOR_TERRITORIAL_CITY_RADIUS_KM || 10);
  }
  function aggregateTerritorialItems"""
js, n = re.subn(rad_re, rad_new, js, count=1, flags=re.S)
if n != 1:
    # Older script may not have radiusForAggregate; non-fatal.
    pass

# Normalize new backend fields.
normalize_re = r"      aggregation_level: item\.aggregation_level \|\| item\.area_level \|\| item\.precision \|\| ''"
normalize_new = """      aggregation_level: item.aggregation_level || item.area_level || item.precision || '',
      ui_group: item.ui_group || item.subcategory || '',
      ui_group_label: item.ui_group_label || '',
      subcategory: item.subcategory || item.ui_group || '',
      localization_precision: item.localization_precision || '',
      display_radius_km: item.display_radius_km != null ? Number(item.display_radius_km) : null"""
js, n = re.subn(normalize_re, normalize_new, js, count=1)
if n != 1:
    raise SystemExit('ERROR: could not extend normalizeLayer return object.')

# Fix fallbacks from META.vectors if present.
js = js.replace('META.vectors', 'META.mosquitoes_other_vectors')
js = js.replace("cat === 'vectors' ? 'vettori'", "cat === 'mosquitoes_other_vectors' ? 'zanzare vettori'")
js = js.replace("cat === 'vectors'", "cat === 'mosquitoes_other_vectors'")

REPORT.write_text(js, encoding='utf-8')

# Config bump.
cfg = CONFIG.read_text(encoding='utf-8')
cfg = re.sub(r'// vet\.ector - config \+ .*', '// vet.ector - config + v220 backend ui_group filters', cfg, count=1)
cfg = re.sub(r'territorial_layers\.json\?v=\d+', 'territorial_layers.json?v=220', cfg)
CONFIG.write_text(cfg, encoding='utf-8')

# Index script cache bump.
html = INDEX.read_text(encoding='utf-8')
html = re.sub(r'/js/config\.js\?v=\d+', '/js/config.js?v=220', html)
html = re.sub(r'/js/report-prefill-v82\.js\?v=\d+', '/js/report-prefill-v82.js?v=220', html)
INDEX.write_text(html, encoding='utf-8')

# Validate necessary terms.
final = REPORT.read_text(encoding='utf-8')
needed = ['sand_flies', 'ticks', 'mosquitoes_other_vectors', 'layerGroupKey', 'display_radius_km', 'ui_group']
missing = [x for x in needed if x not in final]
if missing:
    raise SystemExit('ERROR: patched report file missing ' + ', '.join(missing))
print('OK: frontend patched to backend ui_group filters v220.')
print('Updated: index.html, js/config.js, js/report-prefill-v82.js')
print('No backend calls were added. No /vector-occurrences logic was added.')
