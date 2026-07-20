#!/usr/bin/env python3
"""vet.ector v178 — Full Database Refresh Controller.

This script orchestrates the refresh of all major local/curated databases used by
vet.ector. It is intentionally robust: optional external imports may fail without
blocking the entire run, while validation of generated canonical CSV/JSON files is
critical when those files exist.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path.cwd()
STATUS_DIR = ROOT / "data" / "status"
STATUS_DIR.mkdir(parents=True, exist_ok=True)

REPORT_JSON = STATUS_DIR / "full_refresh_report.json"
REPORT_CSV = STATUS_DIR / "full_refresh_report.csv"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_bool(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def run_step(name: str, command: List[str], critical: bool = False, skip_if_missing: str | None = None) -> Dict[str, Any]:
    started = now_iso()
    step: Dict[str, Any] = {
        "name": name,
        "command": " ".join(command),
        "critical": critical,
        "started_at": started,
    }
    if skip_if_missing and not (ROOT / skip_if_missing).exists():
        step.update({
            "status": "skipped",
            "message": f"missing {skip_if_missing}",
            "finished_at": now_iso(),
        })
        return step

    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        step.update({
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "finished_at": now_iso(),
        })
        if proc.returncode == 0:
            step["status"] = "success"
        else:
            step["status"] = "error"
            if critical:
                step["fatal"] = True
    except Exception as exc:  # pragma: no cover
        step.update({
            "status": "error",
            "exception": repr(exc),
            "finished_at": now_iso(),
        })
        if critical:
            step["fatal"] = True
    return step


def count_csv(path: str) -> int | None:
    p = ROOT / path
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            return max(0, sum(1 for _ in csv.DictReader(f)))
    except Exception:
        return None


def count_json_records(path: str) -> int | None:
    p = ROOT / path
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            if isinstance(data.get("diseases"), list):
                return len(data.get("diseases", []))
            if isinstance(data.get("entities"), list):
                return len(data.get("entities", []))
        return None
    except Exception:
        return None


def build_summary() -> Dict[str, Any]:
    return {
        "official_events": {
            "adis": count_csv("data/official_sources/adis_events.csv"),
            "wahis": count_csv("data/official_sources/wahis_events.csv"),
            "izs_benv": count_csv("data/official_sources/izs_benv_events.csv"),
        },
        "territorial_layers": {
            "total": count_csv("data/territorial_layers/territorial_layers.csv"),
            "mosquito_alert_layers": count_csv("data/territorial_layers/mosquito_alert_layers.csv"),
            "vectornet_gbif_layers": count_csv("data/territorial_layers/vectornet_gbif_layers.csv"),
            "extended_vector_layers": count_csv("data/territorial_layers/extended_vector_layers.csv"),
            "benv_parasite_layers": count_csv("data/territorial_layers/benv_parasite_layers.csv"),
            "west_nile_surveillance": count_csv("data/territorial_layers/west_nile_surveillance.csv"),
            "esccap_parasites": count_csv("data/territorial_layers/esccap_parasites.csv"),
        },
        "catalogs": {
            "diseases_public_html": count_json_records("public_html/data/diseases.json"),
            "diseases_data": count_json_records("data/diseases.json"),
        },
        "reports": {
            "data_sources_status_json": (ROOT / "data/status/data_sources_status.json").exists(),
            "territorial_status_report_json": (ROOT / "data/territorial_layers/territorial_layers_status_report.json").exists(),
            "benv_import_report_csv": (ROOT / "data/official_sources/benv_import_report.csv").exists(),
            "benv_companion_report_csv": (ROOT / "data/official_sources/benv_companion_report.csv").exists(),
        },
    }


def write_csv_report(report: Dict[str, Any]) -> None:
    rows = []
    for step in report.get("steps", []):
        rows.append({
            "section": "step",
            "name": step.get("name"),
            "status": step.get("status"),
            "critical": step.get("critical"),
            "returncode": step.get("returncode"),
            "message": step.get("message", "") or step.get("exception", ""),
        })
    summary = report.get("summary", {})
    for group, values in summary.items():
        if isinstance(values, dict):
            for key, value in values.items():
                rows.append({
                    "section": group,
                    "name": key,
                    "status": "value",
                    "critical": "",
                    "returncode": "",
                    "message": value,
                })
    with REPORT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["section", "name", "status", "critical", "returncode", "message"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    steps: List[Dict[str, Any]] = []

    run_benv = env_bool("VETECTOR_FULL_REFRESH_RUN_BENV", True)
    run_territorial = env_bool("VETECTOR_FULL_REFRESH_RUN_TERRITORIAL", True)
    run_diseases = env_bool("VETECTOR_FULL_REFRESH_RUN_DISEASES", True)
    run_status = env_bool("VETECTOR_FULL_REFRESH_RUN_STATUS", True)

    py = sys.executable

    if run_benv:
        steps.append(run_step("benv_build", [py, "scripts/benv_xlsx_to_vetector_csv.py"], critical=True, skip_if_missing="scripts/benv_xlsx_to_vetector_csv.py"))
        if (ROOT / "data/official_sources/izs_benv_events.csv").exists():
            steps.append(run_step("benv_validate", [py, "scripts/validate_italy_sources.py", "data/official_sources/izs_benv_events.csv"], critical=True, skip_if_missing="scripts/validate_italy_sources.py"))

    if run_territorial:
        # Local/curated source builders should not depend on remote endpoints.
        steps.append(run_step("vectors_invasive_local", [py, "scripts/build_invasive_mosquito_layers.py"], critical=False, skip_if_missing="scripts/build_invasive_mosquito_layers.py"))
        steps.append(run_step("vectors_extended_local", [py, "scripts/build_extended_vector_layers.py"], critical=False, skip_if_missing="scripts/build_extended_vector_layers.py"))
        steps.append(run_step("parasites_from_benv", [py, "scripts/build_benv_parasite_layers.py"], critical=False, skip_if_missing="scripts/build_benv_parasite_layers.py"))
        steps.append(run_step("territorial_merge", [py, "scripts/refresh_territorial_layers_all.py"], critical=True, skip_if_missing="scripts/refresh_territorial_layers_all.py"))
        if (ROOT / "data/territorial_layers/territorial_layers.csv").exists():
            steps.append(run_step("territorial_validate", [py, "scripts/validate_territorial_layers.py", "data/territorial_layers/territorial_layers.csv"], critical=True, skip_if_missing="scripts/validate_territorial_layers.py"))
        steps.append(run_step("territorial_status_report", [py, "scripts/build_territorial_layers_status_report.py"], critical=False, skip_if_missing="scripts/build_territorial_layers_status_report.py"))

    if run_diseases:
        if (ROOT / "public_html/data/diseases.json").exists():
            steps.append(run_step("diseases_validate_public_html", [py, "scripts/validate_diseases_catalog.py", "public_html/data/diseases.json"], critical=True, skip_if_missing="scripts/validate_diseases_catalog.py"))
        elif (ROOT / "data/diseases.json").exists():
            steps.append(run_step("diseases_validate_data", [py, "scripts/validate_diseases_catalog.py", "data/diseases.json"], critical=True, skip_if_missing="scripts/validate_diseases_catalog.py"))
        else:
            steps.append({"name": "diseases_validate", "status": "skipped", "critical": False, "message": "diseases.json not found", "started_at": now_iso(), "finished_at": now_iso()})

    if run_status:
        steps.append(run_step("data_sources_status", [py, "scripts/build_data_sources_status.py"], critical=False, skip_if_missing="scripts/build_data_sources_status.py"))

    fatal = any(step.get("fatal") for step in steps)
    report = {
        "version": "v178-full-database-refresh-controller",
        "generated_at": now_iso(),
        "status": "error" if fatal else "ok",
        "steps": steps,
        "summary": build_summary(),
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if fatal else 0


if __name__ == "__main__":
    raise SystemExit(main())
