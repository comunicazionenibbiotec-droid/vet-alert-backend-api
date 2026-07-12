#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REQUIRED = {"external_id", "source", "disease", "disease_it", "diagnosis_status", "species", "animal_group", "observation_date", "country", "location", "lat", "lon"}


def validate_file(path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not path.exists():
        return False, [f"missing file: {path}"]
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])
        missing = REQUIRED - fields
        if missing:
            errors.append(f"{path}: missing required columns: {sorted(missing)}")
        rows = list(reader)
    seen = set()
    for i, row in enumerate(rows, start=2):
        ext = str(row.get("external_id", "")).strip()
        if ext in seen:
            errors.append(f"{path}:{i}: duplicate external_id {ext}")
        seen.add(ext)
        for col in REQUIRED:
            if not str(row.get(col, "")).strip():
                errors.append(f"{path}:{i}: empty required column {col}")
        try:
            lat = float(str(row.get("lat", "")).strip())
            lon = float(str(row.get("lon", "")).strip())
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                errors.append(f"{path}:{i}: invalid coordinates lat={lat} lon={lon}")
        except Exception:
            errors.append(f"{path}:{i}: lat/lon must be numeric")
    print(f"{path}: {len(rows)} rows checked")
    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--dir", default="data/official_sources")
    args = parser.parse_args()
    files = [Path(x) for x in args.file] if args.file else [Path(args.dir) / "wahis_events.csv", Path(args.dir) / "adis_events.csv"]
    all_errors: list[str] = []
    for path in files:
        ok, errors = validate_file(path)
        all_errors.extend(errors)
        if ok:
            print(f"OK {path}")
    if all_errors:
        for err in all_errors:
            print("ERROR", err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
