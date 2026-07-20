#!/usr/bin/env bash
set -euo pipefail

: "${API_BASE_URL:?API_BASE_URL is required}"

curl -fsS "$API_BASE_URL/health" | python -m json.tool
curl -fsS "$API_BASE_URL/cities" | python -m json.tool >/tmp/vetector-cities.json
curl -fsS "$API_BASE_URL/events?lat=45.0703&lon=7.6869&radius_km=50&days=180&animal_filter=all" | python -m json.tool >/tmp/vetector-events.json
curl -fsS "$API_BASE_URL/territorial-layers?lat=45.0703&lon=7.6869&radius_km=50&category=all" | python -m json.tool >/tmp/vetector-layers.json

echo "[OK] smoke tests completed"
