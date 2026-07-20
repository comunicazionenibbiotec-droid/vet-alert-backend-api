# Render environment checklist

## Web service: `vetector-backend-api`

Set these variables:

```bash
DATABASE_URL=<from Render PostgreSQL internal connection string>
NODE_ENV=production
CORS_ORIGIN=https://vet.ector.nibbiotec.com
DEFAULT_RADIUS_KM=50
MAX_RADIUS_KM=250
DEFAULT_DAYS=180
MAX_DAYS=730
MAX_RESULTS=1000
```

## Cron service: `vetector-import-cns-wnv-daily`

```bash
DATABASE_URL=<same database URL>
PROVINCE_CENTROIDS_JSON=data/province_centroids_italy_minimal.json
CNS_WNV_URL=https://www.centronazionalesangue.it/west-nile-virus-2025/
```

## Cron service: `vetector-import-benv-weekly`

```bash
DATABASE_URL=<same database URL>
PROVINCE_CENTROIDS_JSON=data/province_centroids_italy_minimal.json
BENV_CSV_URL=<stable official or curated BENV CSV URL>
```

If `BENV_CSV_URL` is not available yet, keep the BENV cron disabled or expect the importer to fail with a clear configuration error.
