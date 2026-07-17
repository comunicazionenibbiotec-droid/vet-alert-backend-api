from __future__ import annotations
import csv
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.getenv("VETECTOR_REPO_ROOT", "."))
OUT_DIR = ROOT / "data" / "status"
OUT_JSON = OUT_DIR / "data_sources_status.json"
OUT_CSV = OUT_DIR / "data_sources_status.csv"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_csv_rows(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path: Path):
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def file_meta(path: Path):
    if not path.exists():
        return {"exists": False, "path": str(path)}
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def summarize_official_csv(path: Path, source_key: str):
    rows = read_csv_rows(path)
    diseases = Counter((r.get("disease_it") or r.get("disease") or "unknown").strip() for r in rows)
    animals = Counter((r.get("animal_group") or r.get("species") or "unknown").strip() for r in rows)
    regions = Counter((r.get("region") or "unknown").strip() for r in rows)
    companion = sum(1 for r in rows if (r.get("animal_group") or "").lower() in {"dog", "cat", "companion"} or (r.get("species") or "").lower() in {"cane", "gatto"})
    dates = sorted([d for d in (r.get("observation_date") or r.get("report_date") for r in rows) if d])
    return {
        "key": source_key,
        "status": "active" if rows else "empty_or_missing",
        "records": len(rows),
        "file": file_meta(path),
        "top_diseases": diseases.most_common(20),
        "animal_groups": dict(animals),
        "regions": dict(regions),
        "companion_records": companion,
        "period_start": dates[0] if dates else None,
        "period_end": dates[-1] if dates else None,
    }


def summarize_territorial(path: Path):
    rows = read_csv_rows(path)
    by_cat = Counter((r.get("category") or "unknown").strip() for r in rows)
    by_source = Counter((r.get("source") or "unknown").strip() for r in rows)
    by_region = Counter((r.get("region") or "unknown").strip() for r in rows)
    by_province = Counter((r.get("province") or "unknown").strip() for r in rows)
    labels_by_cat = defaultdict(Counter)
    for r in rows:
        cat = (r.get("category") or "unknown").strip()
        label = (r.get("label") or r.get("disease") or r.get("scientific_name") or "unknown").strip()
        labels_by_cat[cat][label] += 1
    return {
        "status": "active" if rows else "empty_or_missing",
        "records": len(rows),
        "file": file_meta(path),
        "categories": dict(by_cat),
        "sources": dict(by_source),
        "regions": dict(by_region),
        "provinces": dict(by_province),
        "top_labels_by_category": {k: v.most_common(20) for k, v in labels_by_cat.items()},
        "interpretation": {
            "radius_km": "territorial precision / aggregation radius, not biological movement range",
            "count_or_evidence_count": "number of evidence records or curated evidence units, not prevalence",
            "territorial_layers": "context layers, not point diagnoses or confirmed clinical cases",
        },
    }


def summarize_json_catalog(path: Path, key: str):
    data = read_json(path)
    records = 0
    if isinstance(data, list):
        records = len(data)
    elif isinstance(data, dict):
        for candidate in ("items", "diseases", "products", "tests", "catalog"):
            if isinstance(data.get(candidate), list):
                records = len(data[candidate])
                break
        else:
            records = len(data)
    return {"key": key, "records": records, "file": file_meta(path), "status": "active" if records else "empty_or_missing"}


def summarize_sync_status():
    candidates = {
        "benv_refresh_metadata": ROOT / "data" / "official_sources" / "benv_refresh_metadata.json",
        "territorial_refresh_status": ROOT / "data" / "territorial_layers" / "refresh_status.json",
        "territorial_layers_status_report": ROOT / "data" / "territorial_layers" / "territorial_layers_status_report.json",
        "benv_backend_sync_status": ROOT / "data" / "official_sources" / "benv_backend_sync_status.json",
    }
    return {k: {"file": file_meta(p), "content": read_json(p)} for k, p in candidates.items()}


def flatten_for_csv(status: dict):
    rows = []
    def add(section, key, records=None, status_value=None, file_path=None, notes=None):
        rows.append({
            "section": section,
            "key": key,
            "records": "" if records is None else records,
            "status": status_value or "",
            "file_path": file_path or "",
            "notes": notes or "",
        })

    for key, value in status.get("official_events", {}).items():
        add("official_events", key, value.get("records"), value.get("status"), value.get("file", {}).get("path"), f"companion_records={value.get('companion_records', '')}")
    terr = status.get("territorial_layers", {})
    add("territorial_layers", "all", terr.get("records"), terr.get("status"), terr.get("file", {}).get("path"), json.dumps(terr.get("categories", {}), ensure_ascii=False))
    for key, value in status.get("catalogs", {}).items():
        add("catalogs", key, value.get("records"), value.get("status"), value.get("file", {}).get("path"))
    return rows


def build_status():
    official_dir = ROOT / "data" / "official_sources"
    status = {
        "version": "v170-data-sources-status",
        "generated_at": now_iso(),
        "official_events": {
            "adis": summarize_official_csv(official_dir / "adis_events.csv", "ADIS"),
            "wahis": summarize_official_csv(official_dir / "wahis_events.csv", "WAHIS"),
            "izs_benv": summarize_official_csv(official_dir / "izs_benv_events.csv", "IZS_BENV"),
        },
        "territorial_layers": summarize_territorial(ROOT / "data" / "territorial_layers" / "territorial_layers.csv"),
        "catalogs": {
            "diseases": summarize_json_catalog(ROOT / "public_html" / "data" / "diseases.json", "diseases"),
            "diagnostic_tests": summarize_json_catalog(ROOT / "public_html" / "data" / "diagnostic_tests.json", "diagnostic_tests"),
            "foods_supplements": summarize_json_catalog(ROOT / "public_html" / "data" / "foods_supplements.json", "foods_supplements"),
        },
        "refresh_artifacts": summarize_sync_status(),
    }
    return status


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    status = build_status()
    OUT_JSON.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = flatten_for_csv(status)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["section", "key", "records", "status", "file_path", "notes"])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"status": "success", "json": str(OUT_JSON), "csv": str(OUT_CSV), "rows": len(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
