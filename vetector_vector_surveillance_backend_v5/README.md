# vet.ector vector surveillance backend v5

This package extends the existing vet.ector database/backend with vector, parasite and West Nile surveillance tables and import jobs.

## Main files

```txt
db/migration_005_vector_surveillance.sql
db/seed_leishmaniasis_vectors.sql
importers/import_vectornet_gbif.py
importers/import_cns_wnv_v5.py
importers/rebuild_vector_layers_from_occurrences.sql
scheduler/github_actions_vector_surveillance.yml
data/province_centroids_italy_minimal.json
docs/implementation_plan.md
```

## Quick start

```bash
export DATABASE_URL="postgresql://..."
psql "$DATABASE_URL" -f db/migration_005_vector_surveillance.sql
psql "$DATABASE_URL" -f db/seed_leishmaniasis_vectors.sql
pip install -r importers/requirements.txt
python importers/import_vectornet_gbif.py
psql "$DATABASE_URL" -f importers/rebuild_vector_layers_from_occurrences.sql
python importers/import_cns_wnv_v5.py
```

## Important production settings

```bash
VECTORNET_PUBLISHER_KEY=8f9f9814-a595-4bc3-8631-776ba3c9c62e
VECTORNET_LIMIT_PER_SPECIES=500
PROVINCE_CENTROIDS_JSON=data/province_centroids_italy_minimal.json
```

Replace the minimal centroid file with a complete ISTAT/official province and municipality centroid dataset before production.
