from __future__ import annotations

import csv
import io
import os
import urllib.request
from pathlib import Path
from typing import Dict, List


class IzsBenvCsvConnector:
    """CSV connector for BENV / IZS events.

    Expected normalized CSV columns:
    external_id,source,disease,disease_it,diagnosis_status,species,animal_group,
    observation_date,report_date,country,region,location,lat,lon,url_source,notes

    Priority order:
    1. IZS_BENV_REMOTE_CSV_URL if configured
    2. data/official_sources/izs_benv_events.csv
    3. data/official_sources/izs_benv_events_template.csv
    """

    source_name = "IZS_BENV_CSV"

    def __init__(self):
        self.remote_url = os.getenv("IZS_BENV_REMOTE_CSV_URL", "").strip()
        self.timeout = int(os.getenv("SOURCE_DOWNLOAD_TIMEOUT_SECONDS", "30"))
        self.local_path = Path(os.getenv("IZS_BENV_LOCAL_CSV", "data/official_sources/izs_benv_events.csv"))
        self.template_path = Path(os.getenv("IZS_BENV_TEMPLATE_CSV", "data/official_sources/izs_benv_events_template.csv"))

    @staticmethod
    def parse_csv_text(csv_text: str) -> List[Dict[str, str]]:
        if not csv_text or not csv_text.strip():
            return []
        reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
        rows: List[Dict[str, str]] = []
        for row in reader:
            if not row:
                continue
            clean = {str(k).strip(): ("" if v is None else str(v).strip()) for k, v in row.items() if k is not None}
            if not clean.get("external_id") and not clean.get("disease"):
                continue
            clean.setdefault("source", "IZS_BENV")
            if not clean.get("source"):
                clean["source"] = "IZS_BENV"
            clean.setdefault("source_type", "official")
            clean.setdefault("report_type", "official_confirmed")
            clean.setdefault("diagnosis_status", "Confermato")
            rows.append(clean)
        return rows

    def _download_remote(self) -> str | None:
        if not self.remote_url:
            return None
        try:
            req = urllib.request.Request(self.remote_url, headers={"User-Agent": "vetector-benv-sync/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8-sig")
        except Exception as exc:
            print(f"[IZS_BENV] remote download failed: {exc}")
            return None

    def _read_file(self, path: Path) -> str | None:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            print(f"[IZS_BENV] failed reading {path}: {exc}")
        return None

    def fetch(self) -> List[Dict[str, str]]:
        csv_text = self._download_remote()
        if csv_text is None:
            csv_text = self._read_file(self.local_path)
        if csv_text is None:
            csv_text = self._read_file(self.template_path)
        return self.parse_csv_text(csv_text or "")
