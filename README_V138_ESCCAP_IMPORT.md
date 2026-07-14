# vet.ector v138 - ESCCAP / Parassiti territorial import

This patch adds a curated ESCCAP parasite layer import into the territorial layer pipeline.

## Why curated CSV?

ESCCAP Parasite Infection Maps are useful for companion animal parasites and parasite-associated infections, including dogs and cats. The maps represent the percentage of positive tests among screened pets, not the real prevalence in the whole pet population. For a public/commercial platform, verify terms of use or obtain written authorisation before importing ESCCAP data at scale.

## Files

```text
sync/esccap_connector.py
scripts/build_esccap_layers.py
data/territorial_layers/esccap_parasites.csv
data/territorial_layers/esccap_parasites_template.csv
.github/workflows/territorial_layers_refresh.yml
V138_MAIN_PATCH.md
```

## Data flow

```text
curated/authed ESCCAP aggregate CSV
↓
sync/esccap_connector.py
↓
scripts/build_esccap_layers.py
↓
data/territorial_layers/territorial_layers.csv
↓
GET /territorial-layers
↓
Home map: Parassiti checkbox
```

## CSV schema

```csv
external_id,parasite,scientific_name,animal_species,animal_group,data_type,positive_tests,tested,percent_positive,period_start,period_end,country,region,province,location,lat,lon,radius_km,url_source,notes
```

## Run locally

```bash
python scripts/build_esccap_layers.py
python scripts/validate_territorial_layers.py data/territorial_layers/territorial_layers.csv
```

## Backend endpoint to add

See `V138_MAIN_PATCH.md`.

## Classification in vet.ector

```text
category = parasites
source = ESCCAP
data_type = positive_tests_aggregate
display = Contesto territoriale / Parassiti
```

These records are not disease outbreaks, not official confirmations, and not individual clinical cases. They are aggregate diagnostic context layers.
