#!/usr/bin/env python3
"""Validate territorial layers CSV with backward and forward compatible schema."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

REQUIRED_BASE = {"external_id", "category", "lat", "lon"}
# Legacy frontend/backend still use label/count; new pipeline can use disease/evidence_count.
LABEL_ALIASES = ("label", "disease", "scientific_name")
COUNT_ALIASES = ("count", "evidence_count")


def has_any(fields: set[str], aliases: tuple[str, ...]) -> bool:
    return any(a in fields for a in aliases)


def validate(path: Path) -> int:
    if not path.exists():
        print(f"ERROR missing file: {path}")
        return 1
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = set(reader.fieldnames or [])
        missing = REQUIRED_BASE - fields
        if missing:
            print(f"ERROR missing columns: {sorted(missing)}")
            return 1
        if not has_any(fields, LABEL_ALIASES):
            print(f"ERROR missing one of label aliases: {LABEL_ALIASES}")
            return 1
        if not has_any(fields, COUNT_ALIASES):
            print(f"ERROR missing one of count aliases: {COUNT_ALIASES}")
            return 1
        errors = 0
        rows = 0
        categories: dict[str, int] = {}
        for line, row in enumerate(reader, start=2):
            if not any(str(v or "").strip() for v in row.values()):
                continue
            rows += 1
            category = str(row.get("category", "") or "").strip()
            categories[category] = categories.get(category, 0) + 1
            label = next((str(row.get(a, "") or "").strip() for a in LABEL_ALIASES if str(row.get(a, "") or "").strip()), "")
            count = next((str(row.get(a, "") or "").strip() for a in COUNT_ALIASES if str(row.get(a, "") or "").strip()), "")
            if not label:
                print(f"ERROR {path}:{line}: missing label/disease/scientific_name")
                errors += 1
            if not count:
                print(f"ERROR {path}:{line}: missing count/evidence_count")
                errors += 1
            try:
                lat = float(str(row.get("lat", "")).replace(",", "."))
                lon = float(str(row.get("lon", "")).replace(",", "."))
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError("coordinates out of range")
            except Exception:
                print(f"ERROR {path}:{line}: invalid lat/lon")
                errors += 1
        print(f"OK {path}: {rows} rows; categories={categories}")
        return 1 if errors else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file")
    args = ap.parse_args()
    return validate(Path(args.csv_file))


if __name__ == "__main__":
    raise SystemExit(main())
