#!/usr/bin/env python3
"""Build quality/status reports for vet.ector territorial layers.

Reads:
- data/territorial_layers/territorial_layers.csv
- data/territorial_layers/refresh_status.json, if present

Writes:
- data/territorial_layers/territorial_layers_status_report.json
- data/territorial_layers/territorial_layers_status_report.csv

The report is intended to make source quality transparent:
- vectors are usually curated distribution/presence layers;
- parasites can be derived from official BENV rows when present;
- west_nile is province-level surveillance/prevention context.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path("data/territorial_layers")
INPUT = BASE / "territorial_layers.csv"
REFRESH_STATUS = BASE / "refresh_status.json"
OUT_JSON = BASE / "territorial_layers_status_report.json"
OUT_CSV = BASE / "territorial_layers_status_report.csv"

CATEGORY_NOTES = {
    "vectors": {
        "status": "curated_active",
        "interpretation": "presence/distribution context; not a clinical case count",
        "recommended_display": "one aggregated circle per area/category; opacity by evidence count",
    },
    "parasites": {
        "status": "official_or_curated_active_if_rows_present",
        "interpretation": "BENV-derived or curated parasitic context; not prevalence estimate",
        "recommended_display": "one aggregated circle per area/category; use source note in popup",
    },
    "west_nile": {
        "status": "surveillance_context_active",
        "interpretation": "province-level surveillance/prevention context; not individual veterinary diagnosis",
        "recommended_display": "province radius and contextual note",
    },
}

CSV_COLS = [
    "category",
    "rows",
    "sources",
    "regions",
    "provinces",
    "locations",
    "period_start_min",
    "period_end_max",
    "status",
    "interpretation",
]


def parse_date(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value[:10]).date().isoformat()
    except Exception:
        return value[:10]


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    if INPUT.exists():
        with INPUT.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            rows = [dict(r) for r in reader if any(str(v or "").strip() for v in r.values())]

    by_category: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_category[str(row.get("category") or "unknown").strip() or "unknown"].append(row)

    category_reports: dict[str, Any] = {}
    csv_rows: list[dict[str, Any]] = []
    for category, items in sorted(by_category.items()):
        sources = Counter(str(r.get("source") or "unknown").strip() or "unknown" for r in items)
        regions = sorted({str(r.get("region") or "").strip() for r in items if str(r.get("region") or "").strip()})
        provinces = sorted({str(r.get("province") or "").strip() for r in items if str(r.get("province") or "").strip()})
        locations = sorted({str(r.get("location") or "").strip() for r in items if str(r.get("location") or "").strip()})
        starts = sorted([d for d in (parse_date(r.get("period_start") or r.get("period") or "") for r in items) if d])
        ends = sorted([d for d in (parse_date(r.get("period_end") or r.get("period") or "") for r in items) if d])
        note = CATEGORY_NOTES.get(category, {
            "status": "active",
            "interpretation": "territorial context layer",
            "recommended_display": "category aggregation",
        })
        report = {
            "rows": len(items),
            "sources": dict(sources),
            "regions_count": len(regions),
            "provinces_count": len(provinces),
            "locations_count": len(locations),
            "period_start_min": starts[0] if starts else "",
            "period_end_max": ends[-1] if ends else "",
            **note,
        }
        category_reports[category] = report
        csv_rows.append({
            "category": category,
            "rows": len(items),
            "sources": "; ".join(f"{k}:{v}" for k, v in sources.items()),
            "regions": len(regions),
            "provinces": len(provinces),
            "locations": len(locations),
            "period_start_min": starts[0] if starts else "",
            "period_end_max": ends[-1] if ends else "",
            "status": note["status"],
            "interpretation": note["interpretation"],
        })

    refresh_status: dict[str, Any] | None = None
    if REFRESH_STATUS.exists():
        try:
            refresh_status = json.loads(REFRESH_STATUS.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            refresh_status = {"error": f"could_not_parse_refresh_status: {exc}"}

    report = {
        "version": "v165-territorial-quality-status-report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(INPUT),
        "rows_total": len(rows),
        "categories": category_reports,
        "refresh_status": refresh_status,
        "quality_notes": [
            "count/evidence_count is an evidence or row count; it is not a prevalence estimate unless explicitly stated by the source.",
            "radius_km represents display/territorial aggregation precision, not biological movement range.",
            "West Nile layers are surveillance/prevention context areas and should not be interpreted as veterinary point diagnoses.",
            "BENV parasite layers are derived from official BENV events already imported into vet.ector.",
        ],
    }

    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLS)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(json.dumps({"output_json": str(OUT_JSON), "output_csv": str(OUT_CSV), "rows_total": len(rows), "categories": list(category_reports)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
