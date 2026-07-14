# vet.ector v133 - Territorial layers backend scaffold

Upload/merge these files into the backend repository:

- main.py
- sync/territorial_layers_connector.py
- data/territorial_layers/territorial_layers.csv
- data/territorial_layers/territorial_layers_template.csv
- scripts/validate_territorial_layers.py
- .github/workflows/territorial_layers_refresh.yml

New endpoints:

- GET /territorial-layers
- GET /territorial-layers/export
- POST /sync/territorial-layers/run
- GET /sync/territorial-layers/status

The real data CSV is intentionally created with headers only. Populate it with approved/licensed aggregate rows from Mosquito Alert, VectorNet/GBIF, ESCCAP, and ISS/IZS WNV. Use territorial_layers_template.csv as the controlled schema guide.


## v135 Mosquito Alert import

New files/endpoints:

- `sync/mosquito_alert_connector.py`
- `scripts/build_mosquito_alert_layers.py`
- `POST /sync/territorial-layers/mosquito-alert/run`

The connector downloads the Mosquito Alert public reports zip, extracts JSON/GeoJSON records, filters Italian observations for target mosquito vector species, aggregates observations around Italian reference centres, and rewrites the MOSQUITO_ALERT rows in `data/territorial_layers/territorial_layers.csv`.

Environment variables:

- `MOSQUITO_ALERT_REPORTS_URL` default: `https://github.com/MosquitoAlert/Data/raw/master/all_reports.zip`
- `MOSQUITO_ALERT_DAYS` default: `730`
- `MOSQUITO_ALERT_MIN_COUNT` default: `1`
- `MOSQUITO_ALERT_TIMEOUT_SECONDS` default: `90`

Run manually:

```bash
python scripts/build_mosquito_alert_layers.py
```

Then validate:

```bash
python scripts/validate_territorial_layers.py data/territorial_layers/territorial_layers.csv
```
