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
