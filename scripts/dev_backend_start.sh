#!/usr/bin/env bash
set -e

cd /workspaces/vet-alert-backend-api

echo "[1/6] Working directory:"
pwd

echo "[2/6] Checking env/backend-api.env..."
if [ ! -f env/backend-api.env ]; then
  echo "ERROR: env/backend-api.env not found."
  echo "Create it from env/backend-api.env.example and add the real DATABASE_URL."
  exit 1
fi

echo "[3/6] Loading backend environment..."
set -a
source env/backend-api.env
set +a

if [ -z "$DATABASE_URL" ]; then
  echo "ERROR: DATABASE_URL is empty."
  exit 1
fi

echo "[4/6] Installing Node dependencies..."
npm install

echo "[5/6] Checking backend files..."
node --check api/server.js
node --check api/routes/adminOutbreaks.js
node --check api/services/outbreakJobs.js

echo "[6/6] Starting backend on port 3000..."
npm run dev
