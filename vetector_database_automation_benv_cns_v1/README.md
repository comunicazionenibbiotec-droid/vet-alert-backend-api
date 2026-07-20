# vet.ector database automation v1

This package starts the database automation for:

- BENV / IZS official veterinary data
- CNS WNV provincial prevention measures

## Setup

```bash
psql "$DATABASE_URL" -f db/schema.sql
psql "$DATABASE_URL" -f db/seed_data_sources.sql
pip install -r importers/requirements.txt
```

## Run CNS WNV import

```bash
export DATABASE_URL="postgresql://..."
python importers/import_cns_wnv.py
```

## Run BENV / IZS import

BENV pages are dynamic. Use an official export or curated CSV with columns such as:

```txt
disease,species,region,province,municipality,date,lat,lon
```

Run:

```bash
export DATABASE_URL="postgresql://..."
export BENV_CSV_PATH="/path/to/benv_export.csv"
python importers/import_benv_izs.py
```

or:

```bash
export BENV_CSV_URL="https://example.org/benv_export.csv"
python importers/import_benv_izs.py
```

## Important

`data/province_centroids_italy_minimal.json` is a starter file. For production, replace it with a complete ISTAT province centroid dataset.
