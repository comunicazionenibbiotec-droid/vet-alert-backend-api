#!/usr/bin/env python3
from __future__ import annotations

import os
import urllib.request
from pathlib import Path

from validate_official_sources import main as validate_main

SOURCES = [
    ("WAHIS_SOURCE_CSV_URL", Path("data/official_sources/wahis_events.csv")),
    ("ADIS_SOURCE_CSV_URL", Path("data/official_sources/adis_events.csv")),
]


def download(url: str, dest: Path) -> None:
    print(f"Downloading {url} -> {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "vetector-source-sync/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        data = response.read()
    if not data.strip():
        raise RuntimeError(f"Downloaded empty file from {url}")
    dest.write_bytes(data)
    print(f"[OK] wrote {dest} ({len(data)} bytes)")


def main() -> int:
    for env_name, dest in SOURCES:
        url = os.getenv(env_name, "").strip()
        if url:
            download(url, dest)
        else:
            print(f"[INFO] {env_name} not set; keeping existing {dest}")
    return validate_main()


if __name__ == "__main__":
    raise SystemExit(main())
