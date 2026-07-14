# vet.ector v137 - West Nile / ISS-IZS-CESME territorial import

This patch extends the territorial layer backend with a curated West Nile / Usutu import.

Files added/updated:

- `main.py`
- `sync/west_nile_connector.py`
- `scripts/build_west_nile_layers.py`
- `data/territorial_layers/west_nile_surveillance.csv`
- `data/territorial_layers/west_nile_surveillance_template.csv`
- `.github/workflows/territorial_layers_refresh.yml`

New endpoints:

- `POST /sync/territorial-layers/west-nile/run`
- `GET /sync/territorial-layers/west-nile/status`

Why curated CSV:

Official West Nile / Usutu bulletins are primarily published as web/PDF/storymap outputs, and the stable machine-readable endpoint can vary. This connector therefore supports a controlled curated CSV extracted from ISS/IZS/CESME bulletins, with optional remote CSV via `WEST_NILE_REMOTE_CSV_URL`.

Environment variables:

- `WEST_NILE_CSV_PATH` default: `data/territorial_layers/west_nile_surveillance.csv`
- `WEST_NILE_REMOTE_CSV_URL` optional remote curated CSV URL
- `WEST_NILE_TIMEOUT_SECONDS` default: `60`

Manual run:

```bash
python scripts/build_west_nile_layers.py
python scripts/validate_territorial_layers.py data/territorial_layers/territorial_layers.csv
```

The import rewrites only `source=ISS_IZS_WNV` rows in `data/territorial_layers/territorial_layers.csv`; Mosquito Alert and VectorNet rows are preserved.

Next suggested patch: v138 ESCCAP/parasite aggregate import, after confirming permission/terms.
