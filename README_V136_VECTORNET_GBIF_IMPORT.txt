# vet.ector v136 - VectorNet / GBIF territorial import

This patch extends the v135 backend with a VectorNet/GBIF import for vector occurrence layers.

Files added/updated:

- `main.py`
- `sync/vectornet_gbif_connector.py`
- `scripts/build_vectornet_gbif_layers.py`
- `.github/workflows/territorial_layers_refresh.yml`

New endpoint:

- `POST /sync/territorial-layers/vectornet-gbif/run`

The connector uses the GBIF occurrence API to search VectorNet datasets for Italian coordinated occurrences, recognizes key vector taxa/families, aggregates them around Italian reference centres, and rewrites the `VECTORNET` rows in `data/territorial_layers/territorial_layers.csv`.

Environment variables:

- `VECTORNET_GBIF_DATASET_KEYS` default: `4abd984b-122c-44a0-8c92-b37e2f5299b1,e497586a-1bdf-4f69-90eb-645d615762c8`
- `VECTORNET_GBIF_MAX_RECORDS` default: `4000`
- `VECTORNET_GBIF_LIMIT` default: `300`
- `VECTORNET_DAYS` default: `3650`
- `VECTORNET_MIN_COUNT` default: `1`
- `VECTORNET_TIMEOUT_SECONDS` default: `60`

Manual run:

```bash
python scripts/build_vectornet_gbif_layers.py
python scripts/validate_territorial_layers.py data/territorial_layers/territorial_layers.csv
```

Next suggested patch: v137 West Nile / ISS-IZS-CESME import.
