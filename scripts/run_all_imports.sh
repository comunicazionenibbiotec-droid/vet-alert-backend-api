#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"

cd "${VETECTOR_IMPORT_DIR:-vetector_database_automation_benv_cns_v1}"

python importers/import_cns_wnv.py

if [[ -n "${BENV_CSV_URL:-}" || -n "${BENV_CSV_PATH:-}" ]]; then
  python importers/import_benv_izs.py
else
  echo "[WARN] BENV_CSV_URL/BENV_CSV_PATH not set; skipping BENV / IZS import"
fi
