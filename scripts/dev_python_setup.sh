#!/usr/bin/env bash
set -e

cd /workspaces/vet-alert-backend-api

echo "[1/4] Python version"
python --version

echo "[2/4] Upgrade pip"
python -m pip install --upgrade pip

echo "[3/4] Install Python dependencies"
pip install "psycopg[binary]" pandas openpyxl

echo "[4/4] Verify imports"
python -c "import psycopg; print('psycopg OK')"
python -c "import pandas; import openpyxl; print('pandas openpyxl OK')"

echo "Python setup completed"
