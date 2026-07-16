#!/usr/bin/env python3
"""Merge territorial layer CSV files into data/territorial_layers/territorial_layers.csv.

v164 compatibility fix:
- Writes both the newer columns (disease, evidence_count, data_type, period_start/end)
  and the legacy columns still expected by existing validators/backend/frontend
  (label, count, period, color, scientific_name).
- Skips malformed rows instead of failing the whole refresh.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable

BASE = Path("data/territorial_layers")
OUT = BASE / "territorial_layers.csv"
STATUS = BASE / "refresh_status.json"

# Superset schema: keeps backward compatibility with existing validator requiring label/count.
COLUMNS = [
    "external_id",
    "category",
    "source",
    "label",
    "disease",
    "scientific_name",
    "data_type",
    "count",
    "evidence_count",
    "count_label",
    "period",
    "period_start",
    "period_end",
    "country",
    "region",
    "province",
    "location",
    "lat",
    "lon",
    "radius_km",
    "color",
    "url_source",
    "notes",
]

SOURCE_FILES = [
    BASE / "mosquito_alert_layers.csv",
    BASE / "vectornet_gbif_layers.csv",
    BASE / "extended_vector_layers.csv",
    BASE / "benv_parasite_layers.csv",
    BASE / "esccap_parasites.csv",
    BASE / "west_nile_surveillance.csv",
]

CATEGORY_COLORS = {
    "vectors": "#7C3AED",
    "parasites": "#059669",
    "west_nile": "#F59E0B",
}


def first_nonempty(row: Dict[str, str], names: Iterable[str], default: str = "") -> str:
    for name in names:
        value = str(row.get(name, "") or "").strip()
        if value:
            return value
    return default


def normalize_row(row: Dict[str, str], source_name: str, index: int) -> Dict[str, str] | None:
    category = first_nonempty(row, ["category"], "vectors")
    lat = first_nonempty(row, ["lat", "latitude"])
    lon = first_nonempty(row, ["lon", "lng", "longitude"])
    if not lat or not lon:
        return None
    try:
        float(lat.replace(",", "."))
        float(lon.replace(",", "."))
    except Exception:
        return None

    label = first_nonempty(row, ["label", "disease", "scientific_name", "name"], "Dato territoriale")
    disease = first_nonempty(row, ["disease", "label", "scientific_name", "name"], label)
    scientific_name = first_nonempty(row, ["scientific_name", "scientificName"], "")
    count = first_nonempty(row, ["count", "evidence_count", "observations", "records"], "1")
    period_start = first_nonempty(row, ["period_start", "observation_date", "start_date", "date"], "")
    period_end = first_nonempty(row, ["period_end", "report_date", "end_date"], period_start)
    period = first_nonempty(row, ["period"], " - ".join([x for x in [period_start, period_end] if x]))

    external_id = first_nonempty(row, ["external_id", "id"])
    if not external_id:
        # deterministic enough for a generated merge; preserves uniqueness inside current run
        safe_label = "".join(ch if ch.isalnum() else "-" for ch in label.upper()).strip("-")[:60]
        external_id = f"{source_name}-{index:05d}-{safe_label}"

    out = {col: "" for col in COLUMNS}
    out.update(
        {
            "external_id": external_id,
            "category": category,
            "source": first_nonempty(row, ["source"], source_name),
            "label": label,
            "disease": disease,
            "scientific_name": scientific_name,
            "data_type": first_nonempty(row, ["data_type", "type", "dataType"], "territorial_context"),
            "count": count,
            "evidence_count": count,
            "count_label": first_nonempty(row, ["count_label", "countLabel"], "evidenze"),
            "period": period,
            "period_start": period_start,
            "period_end": period_end,
            "country": first_nonempty(row, ["country"], "Italy"),
            "region": first_nonempty(row, ["region", "Regione"], ""),
            "province": first_nonempty(row, ["province", "provincia", "Provincia"], ""),
            "location": first_nonempty(row, ["location", "area_label", "area", "city", "Comune", "comune"], ""),
            "lat": lat.replace(",", "."),
            "lon": lon.replace(",", "."),
            "radius_km": first_nonempty(row, ["radius_km", "radius", "radiusKm"], "50"),
            "color": first_nonempty(row, ["color"], CATEGORY_COLORS.get(category, "#64748B")),
            "url_source": first_nonempty(row, ["url_source", "source_url", "url"], ""),
            "notes": first_nonempty(row, ["notes", "note"], "Dato territoriale aggregato; non rappresenta diagnosi puntuale."),
        }
    )
    return out


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    rows = []
    seen = set()
    status = {
        "version": "v164-territorial-legacy-schema-compatibility",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [],
    }

    for path in SOURCE_FILES:
        source_status = {"path": str(path), "exists": path.exists(), "rows": 0, "skipped": 0, "status": "skipped"}
        if not path.exists():
            status["sources"].append(source_status)
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                for idx, raw in enumerate(reader, start=1):
                    if not raw or not any(str(v or "").strip() for v in raw.values()):
                        continue
                    row = normalize_row(raw, path.stem.upper(), idx)
                    if not row:
                        source_status["skipped"] += 1
                        continue
                    if row["external_id"] in seen:
                        source_status["skipped"] += 1
                        continue
                    seen.add(row["external_id"])
                    rows.append(row)
                    source_status["rows"] += 1
            source_status["status"] = "success"
        except Exception as exc:  # noqa: BLE001
            source_status["status"] = "error"
            source_status["error"] = str(exc)
        status["sources"].append(source_status)

    with OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    categories: Dict[str, int] = {}
    for row in rows:
        categories[row["category"]] = categories.get(row["category"], 0) + 1
    status.update({"output": str(OUT), "rows_total": len(rows), "categories": categories})
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
