from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REQUIRED = {"external_id", "source", "disease", "species", "animal_group", "observation_date", "lat", "lon"}
DEFAULT_FILES = [
    "data/official_sources/izs_benv_events.csv",
    "data/sentinel/myvbdmap_events.csv",
]


def validate_file(path: Path) -> int:
    if not path.exists():
        print(f"ERROR missing file: {path}")
        return 1
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print(f"ERROR empty or invalid CSV header: {path}")
            return 1
        fields = {x.strip() for x in reader.fieldnames if x}
        missing = REQUIRED - fields
        if missing:
            print(f"ERROR {path}: missing required columns: {sorted(missing)}")
            return 1
        errors = 0
        count = 0
        for i, row in enumerate(reader, start=2):
            if not any((v or "").strip() for v in row.values()):
                continue
            count += 1
            for col in ["external_id", "source", "disease", "species", "animal_group", "observation_date"]:
                if not (row.get(col) or "").strip():
                    print(f"ERROR {path}:{i}: missing {col}")
                    errors += 1
            try:
                float((row.get("lat") or "").strip())
                float((row.get("lon") or "").strip())
            except Exception:
                print(f"ERROR {path}:{i}: invalid lat/lon")
                errors += 1
        print(f"OK {path}: {count} rows")
        return 1 if errors else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", default=DEFAULT_FILES)
    args = ap.parse_args()
    status = 0
    for name in args.files:
        status |= validate_file(Path(name))
    return status


if __name__ == "__main__":
    sys.exit(main())
