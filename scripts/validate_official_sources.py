#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path

REQUIRED = {"external_id", "disease", "species", "animal_group", "observation_date", "lat", "lon"}
RECOMMENDED = {"source", "disease_it", "diagnosis_status", "report_date", "country", "region", "location", "url_source", "notes"}

def validate_file(path: Path) -> tuple[bool, list[str]]:
    errors = []
    if not path.exists():
        return False, [f"missing file: {path}"]
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])
        missing = REQUIRED - fields
        if missing:
            errors.append(f"{path}: missing required columns: {sorted(missing)}")
        rows = list(reader)
    for i, row in enumerate(rows, start=2):
        for col in REQUIRED:
            if not str(row.get(col, "")).strip():
                errors.append(f"{path}:{i}: empty required column {col}")
        try:
            lat = float(row.get("lat", ""))
            lon = float(row.get("lon", ""))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                errors.append(f"{path}:{i}: invalid coordinates lat={lat} lon={lon}")
        except Exception:
            errors.append(f"{path}:{i}: lat/lon must be numeric")
    return len(errors) == 0, errors

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="backend/data/official_sources")
    args = parser.parse_args()
    base = Path(args.dir)
    files = [base / "wahis_events.csv", base / "adis_events.csv"]
    all_errors = []
    for file in files:
        ok, errors = validate_file(file)
        all_errors.extend(errors)
        if ok:
            print(f"OK {file}")
    if all_errors:
        for e in all_errors:
            print("ERROR", e, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
