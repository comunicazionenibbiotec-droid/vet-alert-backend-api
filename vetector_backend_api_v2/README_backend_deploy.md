# vet.ector backend API v2

This package adds the operational API layer for the database automation package v1.

## Endpoints

```txt
GET /health
GET /cities
GET /events?lat=45.0703&lon=7.6869&radius_km=50&days=180&animal_filter=all
GET /territorial-layers?lat=45.0703&lon=7.6869&radius_km=50&category=all
GET /import/status
```

## Install

```bash
npm install
cp .env.example .env
npm start
```

## Database

This API expects the schema from `vetector_database_automation_benv_cns_v1.zip`.

Run:

```bash
psql "$DATABASE_URL" -f db/schema.sql
psql "$DATABASE_URL" -f db/seed_data_sources.sql
psql "$DATABASE_URL" -f db/views_and_helpers.sql
```

## Compatibility with current front-end

The current front-end already calls:

```txt
/cities
/events
/territorial-layers
```

The response fields are shaped to match the objects consumed by `app.js` and `report-prefill-v82.js`.

## Data imports

Use the v1 importers for:

```txt
importers/import_cns_wnv.py
importers/import_benv_izs.py
```

Those importers populate `events` and `territorial_layers`, and this API exposes the data to the map.
