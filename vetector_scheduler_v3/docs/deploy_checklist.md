# vet.ector v3 scheduler/deploy checklist

## Required packages

Use these together:

1. `vetector_database_automation_benv_cns_v1.zip`
2. `vetector_backend_api_v2.zip`
3. `vetector_scheduler_v3.zip`

## Environment variables

### Backend API

```bash
DATABASE_URL=postgresql://...
CORS_ORIGIN=https://vet.ector.nibbiotec.com
NODE_ENV=production
DEFAULT_RADIUS_KM=50
MAX_RADIUS_KM=250
DEFAULT_DAYS=180
MAX_DAYS=730
MAX_RESULTS=1000
```

### Importers

```bash
DATABASE_URL=postgresql://...
PROVINCE_CENTROIDS_JSON=data/province_centroids_italy_minimal.json
BENV_CSV_URL=https://example.org/benv_export.csv
```

`BENV_CSV_URL` is optional until a stable BENV / IZS export is configured.

## Database bootstrap

```bash
./scripts/bootstrap_database.sh /path/to/project/root
```

## Manual import

```bash
export DATABASE_URL="postgresql://..."
export VETECTOR_IMPORT_DIR="/path/to/vetector_database_automation_benv_cns_v1"
./scripts/run_all_imports.sh
```

## Smoke test

```bash
export API_BASE_URL="https://your-api.example.com"
./scripts/smoke_test_api.sh
```

## Front-end config

In `/js/config.js`, point the map to the deployed backend:

```js
window.API_BASE_URL_DEFAULT = 'https://your-vetector-api.onrender.com';
```

## Recommended schedule

- CNS WNV: daily at 03:15 UTC during vector season.
- BENV / IZS: weekly on Monday at 04:45 UTC, or daily if official export supports it.
- API smoke test: every 30 minutes.
