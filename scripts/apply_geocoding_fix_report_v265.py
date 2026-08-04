#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import sqlite3
from pathlib import Path
from typing import Iterable

DB_PATH = os.getenv("DB_PATH", "vet_alert.db")
DEFAULT_CANDIDATES = [
    os.getenv("GEOCODING_FIX_REPORT_CSV", ""),
    "data/official_sources/geocoding_fix_report_v256.csv",
    "data/geocoding_fix_report_v256.csv",
    "geocoding_fix_report_v256.csv",
    "data/official_sources/geocoding_fix_report.csv",
    "data/geocoding_fix_report.csv",
]


def _existing_report_paths() -> list[Path]:
    paths: list[Path] = []
    for raw in DEFAULT_CANDIDATES:
        if raw:
            p = Path(raw)
            if p.exists() and p.is_file():
                paths.append(p)
    for pattern in ("**/geocoding_fix_report*.csv", "**/*geocoding*fix*.csv"):
        for p in Path(".").glob(pattern):
            if p.is_file() and p not in paths:
                paths.append(p)
    return paths


def _boolish(value) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "si", "sì"}


def _float_or_none(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def _ensure_columns(conn: sqlite3.Connection, table: str) -> None:
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    additions = {
        "geocoding_match": "TEXT",
        "geocoding_corrected": "INTEGER DEFAULT 0",
        "geocoding_shift_km": "REAL",
        "geocoding_quality": "TEXT",
        "geocoding_updated_at": "TEXT",
    }
    for name, ddl in additions.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _apply_report(conn: sqlite3.Connection, report_path: Path) -> dict:
    updated = {"official_events": 0, "events": 0}
    skipped = 0
    considered = 0
    max_shift_km = 0.0

    with report_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not _boolish(row.get("changed")):
                continue
            considered += 1
            external_id = str(row.get("external_id") or "").strip()
            new_lat = _float_or_none(row.get("new_lat"))
            new_lon = _float_or_none(row.get("new_lon"))
            shift = _float_or_none(row.get("distance_shift_km"))
            if shift is not None:
                max_shift_km = max(max_shift_km, shift)
            if not external_id or new_lat is None or new_lon is None:
                skipped += 1
                continue
            match = str(row.get("match") or "").strip()
            quality = "corrected_municipality" if "municipality" in match.lower() else "corrected_geocoding"
            params = (
                new_lat,
                new_lon,
                match,
                1,
                shift,
                quality,
                external_id,
            )
            for table in ("official_events", "events"):
                conn.execute(f"""
                    UPDATE {table}
                    SET lat = ?,
                        lon = ?,
                        geocoding_match = ?,
                        geocoding_corrected = ?,
                        geocoding_shift_km = ?,
                        geocoding_quality = ?,
                        geocoding_updated_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE external_id = ?
                """, params)
                updated[table] += conn.total_changes - sum(updated.values())
                # total_changes is cumulative, so adjust below by using cursor rowcount in next loop would be cleaner.

    return {
        "report_path": str(report_path),
        "considered_changed_rows": considered,
        "skipped": skipped,
        "max_shift_km": round(max_shift_km, 3),
    }


def apply_geocoding_fixes(db_path: str = DB_PATH, report_path: str | None = None) -> dict:
    paths = [Path(report_path)] if report_path else _existing_report_paths()
    paths = [p for p in paths if p and p.exists()]
    if not paths:
        return {"status": "missing_report", "db_path": db_path, "searched": DEFAULT_CANDIDATES}
    chosen = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    conn = sqlite3.connect(db_path)
    try:
        for table in ("official_events", "events"):
            _ensure_columns(conn, table)
        updated_official = 0
        updated_events = 0
        skipped = 0
        considered = 0
        max_shift_km = 0.0
        with chosen.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not _boolish(row.get("changed")):
                    continue
                considered += 1
                external_id = str(row.get("external_id") or "").strip()
                new_lat = _float_or_none(row.get("new_lat"))
                new_lon = _float_or_none(row.get("new_lon"))
                shift = _float_or_none(row.get("distance_shift_km"))
                if shift is not None:
                    max_shift_km = max(max_shift_km, shift)
                if not external_id or new_lat is None or new_lon is None:
                    skipped += 1
                    continue
                match = str(row.get("match") or "").strip()
                quality = "corrected_municipality" if "municipality" in match.lower() else "corrected_geocoding"
                params = (new_lat, new_lon, match, 1, shift, quality, external_id)
                cur = conn.execute("""
                    UPDATE official_events
                    SET lat = ?, lon = ?, geocoding_match = ?, geocoding_corrected = ?,
                        geocoding_shift_km = ?, geocoding_quality = ?,
                        geocoding_updated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE external_id = ?
                """, params)
                updated_official += cur.rowcount
                cur = conn.execute("""
                    UPDATE events
                    SET lat = ?, lon = ?, geocoding_match = ?, geocoding_corrected = ?,
                        geocoding_shift_km = ?, geocoding_quality = ?,
                        geocoding_updated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE external_id = ?
                """, params)
                updated_events += cur.rowcount
        conn.commit()
        return {
            "status": "success",
            "db_path": db_path,
            "report_path": str(chosen),
            "considered_changed_rows": considered,
            "updated_official_events": updated_official,
            "updated_events": updated_events,
            "skipped": skipped,
            "max_shift_km": round(max_shift_km, 3),
        }
    finally:
        conn.close()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--report", default=None)
    args = parser.parse_args()
    print(json.dumps(apply_geocoding_fixes(args.db, args.report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
