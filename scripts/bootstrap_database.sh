#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"

ROOT_DIR="${1:-.}"

psql "$DATABASE_URL" -f "$ROOT_DIR/vetector_database_automation_benv_cns_v1/db/schema.sql"
psql "$DATABASE_URL" -f "$ROOT_DIR/vetector_database_automation_benv_cns_v1/db/seed_data_sources.sql"
psql "$DATABASE_URL" -f "$ROOT_DIR/vetector_backend_api_v2/db/views_and_helpers.sql"

echo "[OK] database schema, sources and views installed"
