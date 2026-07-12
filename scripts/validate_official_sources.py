#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List

REQUIRED_COLUMNS = {
    "external_id",
    "disease",
    "species",
    "animal_group",
    "observation_date",
    "lat",
    "lon",
}

RECOMMENDED_COLUMNS = {
    "source",
    "disease_it",
    "diagnosis_status",
    "report_date",
    "country",
    "region",
    "location",
    "url_source",
    "notes",
}

VALID_ANIMAL_GROUPS = {
    "dog",
    "cat",
    "bovine",
    "swine",
    "ovine",
    "equine",
    "caprine",
    "poultry",
    "wildlife",
    "unknown",
}

DEFAULT_FILES = [
    Path("data/official_sources/wahis_events.csv"),
    Path("data/official_sources/adis_events.csv"),
]


def read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"No header found in {path}")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{path}: missing required columns: {sorted(missing)}")
        return [dict(r) for r in reader]


def validate_float(value: str, field: str, path: Path, line_no: int) -> None:
    try:
        float(value)
    except Exception as exc:
        raise ValueError(f"{path}: line {line_no}: invalid {field}={value!r}") from exc


def validate_rows(path: Path, rows: Iterable[Dict[str, str]]) -> int:
    count = 0
    ids = set()
    for idx, row in enumerate(rows, start=2):
        count += 1
        external_id = (row.get("external_id") or "").strip()
        if not external_id:
            raise ValueError(f"{path}: line {idx}: external_id is required")
        if external_id in ids:
            raise ValueError(f"{path}: line {idx}: duplicate external_id={external_id}")
        ids.add(external_id)

        for col in REQUIRED_COLUMNS:
            if not (row.get(col) or "").strip():
                raise ValueError(f"{path}: line {idx}: {col} is required")

        validate_float(row.get("lat", ""), "lat", path, idx)
        validate_float(row.get("lon", ""), "lon", path, idx)

        group = (row.get("animal_group") or "").strip().lower()
        if group not in VALID_ANIMAL_GROUPS:
            raise ValueError(
                f"{path}: line {idx}: animal_group={group!r} not in {sorted(VALID_ANIMAL_GROUPS)}"
            )
    return count


def main() -> int:
    files = [Path(p) for p in sys.argv[1:]] if len(sys.argv) > 1 else DEFAULT_FILES
    total = 0
    for path in files:
        rows = read_rows(path)
        count = validate_rows(path, rows)
        total += count
        print(f"[OK] {path}: {count} rows valid")
    print(f"[OK] total valid rows: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
