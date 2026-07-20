# vet.ector configuration runbook v4

This package configures the three generated components:

1. `vetector_database_automation_benv_cns_v1`
2. `vetector_backend_api_v2`
3. `vetector_scheduler_v3`

## Step 1 — Prepare project layout

Extract the packages into one root directory:

```txt
project-root/
  vetector_database_automation_benv_cns_v1/
  vetector_backend_api_v2/
  vetector_scheduler_v3/
  vetector_config_v4/
```

## Step 2 — Configure database

Create PostgreSQL with PostGIS. Then run:

```bash
export DATABASE_URL="postgresql://..."
./vetector_scheduler_v3/scripts/bootstrap_database.sh .
psql "$DATABASE_URL" -f vetector_config_v4/scripts/verify_database.sql
```

## Step 3 — Configure backend API

Copy the environment template:

```bash
cd vetector_backend_api_v2
cp ../vetector_config_v4/env/backend-api.env.example .env
```

Edit `.env` and set:

```bash
DATABASE_URL=...
CORS_ORIGIN=https://vet.ector.nibbiotec.com
```

Start API:

```bash
npm install
npm start
```

## Step 4 — Configure importers

```bash
cd vetector_database_automation_benv_cns_v1
cp ../vetector_config_v4/env/importers.env.example .env
```

For CNS WNV, `CNS_WNV_URL` is already set to the CNS page.
For BENV / IZS, set `BENV_CSV_URL` only after a stable export or curated CSV is available.

Manual import:

```bash
export DATABASE_URL="postgresql://..."
python importers/import_cns_wnv.py
```

## Step 5 — Configure front-end

Set your API URL in `/js/config.js`:

```js
window.API_BASE_URL_DEFAULT = 'https://your-vetector-api.onrender.com';
```

Use the provided template:

```txt
frontend/config.production.js
```

Recommended script references:

```html
<script src="/js/config.js?v=200"></script>
<script src="/js/map.js?v=34"></script>
<script src="/js/app.js?v=166"></script>
<script src="/js/report-prefill-v82.js?v=174"></script>
```

## Step 6 — Configure scheduler

Choose one mode:

### Render

Use:

```txt
vetector_scheduler_v3/render/render.yaml
```

### GitHub Actions

Copy workflows to:

```txt
.github/workflows/vetector-data-import.yml
.github/workflows/vetector-api-smoke-test.yml
```

Set:

```txt
DATABASE_URL secret
API_BASE_URL variable
BENV_CSV_URL variable, optional
```

### Linux cron

Use:

```txt
vetector_scheduler_v3/cron/crontab.example
```

## Step 7 — Verify

```bash
export API_BASE_URL="https://your-vetector-api.onrender.com"
./vetector_config_v4/scripts/verify_api.sh
```

Expected results:

- `/health` returns `{ "ok": true }`
- `/cities` returns a `cities` array
- `/events` returns an `events` array
- `/territorial-layers` returns a `layers` array
- `/import/status` returns data source and import run metadata
