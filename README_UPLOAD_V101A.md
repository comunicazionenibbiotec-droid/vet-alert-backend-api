# vet.ector v101A - Italy sources backend scaffold

This patch adds backend scaffolding for:

- BENV / IZS as an official Italian veterinary outbreak source
- MyVBDMap as a veterinary sentinel source for canine vector-borne diseases

## Files to upload

If your repository has files at root level, upload:

```text
sync/izs_benv_csv_connector.py
sync/myvbdmap_csv_connector.py

data/official_sources/izs_benv_events.csv
data/official_sources/izs_benv_events_template.csv

data/sentinel/myvbdmap_events.csv
data/sentinel/myvbdmap_events_template.csv

scripts/validate_italy_sources.py
.github/workflows/italy_sources_refresh.yml
```

If your repository uses a `backend/` directory, place the same files under `backend/` where appropriate.

## Manual patches

Apply the instructions in:

```text
V101A_MAIN_PATCH.md
V101A_EVENT_ENRICHMENT_PATCH.md
```

## Render variables, optional for future remote CSVs

```text
IZS_BENV_REMOTE_CSV_URL=https://raw.githubusercontent.com/.../data/official_sources/izs_benv_events.csv
MYVBDMAP_REMOTE_CSV_URL=https://raw.githubusercontent.com/.../data/sentinel/myvbdmap_events.csv
```

You can also skip these variables; the backend will read local repository CSVs.

## Test after deploy

```text
/health
/sync/izs-benv/run
/sync/izs-benv/status
/sync/myvbdmap/run
/sync/myvbdmap/status
/sync/log?limit=10
```

Initially the CSVs are header-only, so `records_received` may be 0. That is expected.
