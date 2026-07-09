#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import urllib.request

BACKEND_URL = os.getenv("VETECTOR_BACKEND_URL", "").rstrip("/")
CSV_URL = os.getenv("WAHIS_CSV_URL", "")
SYNC_TOKEN = os.getenv("WAHIS_SYNC_TOKEN", "")
LOCAL_CSV_PATH = os.getenv("WAHIS_LOCAL_CSV_PATH", "backend/data/wahis_import/wahis_events.csv")


def read_csv_bytes() -> bytes:
    if CSV_URL:
        print(f"Downloading WAHIS CSV from {CSV_URL}")
        with urllib.request.urlopen(CSV_URL, timeout=120) as response:
            return response.read()
    print(f"Reading local CSV from {LOCAL_CSV_PATH}")
    with open(LOCAL_CSV_PATH, "rb") as f:
        return f.read()


def post_csv(csv_bytes: bytes) -> None:
    if not BACKEND_URL:
        raise SystemExit("Missing VETECTOR_BACKEND_URL secret/env variable")
    url = f"{BACKEND_URL}/sync/wahis/upload"
    request = urllib.request.Request(url, data=csv_bytes, method="POST")
    request.add_header("Content-Type", "text/csv; charset=utf-8")
    if SYNC_TOKEN:
        request.add_header("X-Sync-Token", SYNC_TOKEN)
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read().decode("utf-8")
        print(body)


def main() -> int:
    csv_bytes = read_csv_bytes()
    if not csv_bytes.strip():
        raise SystemExit("CSV is empty")
    post_csv(csv_bytes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
