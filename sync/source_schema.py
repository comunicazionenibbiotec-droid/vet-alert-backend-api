from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Tuple

REQUIRED_COLUMNS = {
    "external_id",
    "disease",
    "species",
    "animal_group",
    "observation_date",
    "lat",
    "lon",
}

OPTIONAL_COLUMNS = {
    "source",
    "source_type",
    "report_type",
    "disease_it",
    "diagnosis_status",
    "report_date",
    "country",
    "region",
    "location",
    "url_source",
    "notes",
}

ALL_COLUMNS = list(REQUIRED_COLUMNS | OPTIONAL_COLUMNS)


def read_csv_text(csv_text: str) -> List[Dict[str, Any]]:
    if not csv_text or not csv_text.strip():
        return []
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    return [dict(row) for row in reader]


def validate_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    valid: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows, start=2):
        missing = [c for c in REQUIRED_COLUMNS if not str(row.get(c, "")).strip()]
        if missing:
            errors.append({"line": idx, "error": "missing_required_columns", "columns": missing, "row": row})
            continue
        try:
            float(row.get("lat"))
            float(row.get("lon"))
        except Exception:
            errors.append({"line": idx, "error": "invalid_coordinates", "row": row})
            continue
        valid.append(row)
    return valid, errors


def normalize_source_row(row: Dict[str, Any], default_source: str) -> Dict[str, Any]:
    out = dict(row)
    out["source"] = out.get("source") or default_source
    out.setdefault("source_type", "official")
    out.setdefault("report_type", "official_confirmed")
    out.setdefault("diagnosis_status", "Confermato")
    out.setdefault("country", "Italy")
    out.setdefault("raw_payload", dict(row))
    return out
