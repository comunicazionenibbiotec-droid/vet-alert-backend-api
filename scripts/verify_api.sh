#!/usr/bin/env bash
set -euo pipefail
: "${API_BASE_URL:?API_BASE_URL required}"

printf '\n[1/5] health\n'
curl -fsS "$API_BASE_URL/health" | python -m json.tool

printf '\n[2/5] cities\n'
curl -fsS "$API_BASE_URL/cities" | python -m json.tool | head -n 40

printf '\n[3/5] events Torino\n'
curl -fsS "$API_BASE_URL/events?lat=45.0703&lon=7.6869&radius_km=50&days=180&animal_filter=all" | python -m json.tool | head -n 80

printf '\n[4/5] territorial layers Torino\n'
curl -fsS "$API_BASE_URL/territorial-layers?lat=45.0703&lon=7.6869&radius_km=50&category=all" | python -m json.tool | head -n 120

printf '\n[5/5] import status\n'
curl -fsS "$API_BASE_URL/import/status" | python -m json.tool | head -n 120
