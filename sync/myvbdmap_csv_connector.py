from __future__ import annotations

import csv
import io
import os
import urllib.request
from pathlib import Path
from typing import Dict, List


class MyVbdMapCsvConnector:
    """CSV connector for MyVBDMap sentinel events.

    MyVBDMap should be treated as sentinel/epidemiological context, not as an official notification.

    Expected normalized CSV columns:
    external_id,source,disease,disease_it,diagnosis_status,species,animal_group,
    observation_date,report_date,country,region,location,lat,lon,url_source,notes
    """

    source_name = "MYVBDMAP_CSV"

    def __init__(self):
        self.remote_url = os.getenv("MYVBDMAP_REMOTE_CSV_URL", "").strip()
        self.timeout = int(os.getenv("SOURCE_DOWNLOAD_TIMEOUT_SECONDS", "30"))
        self.local_path = Path(os.getenv("MYVBDMAP_LOCAL_CSV", "data/sentinel/myvbdmap_events.csv"))
        self.template_path = Path(os.getenv("MYVBDMAP_TEMPLATE_CSV", "data/sentinel/myvbdmap_events_template.csv"))

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
            clean["source"] = clean.get("source") or "MYVBDMAP"
            clean["source_type"] = clean.get("source_type") or "sentinel"
            clean["report_type"] = clean.get("report_type") or "veterinary_sentinel"
            clean["diagnosis_status"] = clean.get("diagnosis_status") or "Dato sentinella"
            rows.append(clean)
        return rows

    def _download_remote(self) -> str | None:
        if not self.remote_url:
            return None
        try:
            req = urllib.request.Request(self.remote_url, headers={"User-Agent": "vetector-myvbdmap-sync/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8-sig")
        except Exception as exc:
            print(f"[MYVBDMAP] remote download failed: {exc}")
            return None

    def _read_file(self, path: Path) -> str | None:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            print(f"[MYVBDMAP] failed reading {path}: {exc}")
        return None

    def fetch(self) -> List[Dict[str, str]]:
        csv_text = self._download_remote()
        if csv_text is None:
            csv_text = self._read_file(self.local_path)
        if csv_text is None:
            csv_text = self._read_file(self.template_path)
        return self.parse_csv_text(csv_text or "")
