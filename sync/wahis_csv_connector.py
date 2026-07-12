from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from sync.remote_csv import download_text, save_snapshot
from sync.source_schema import read_csv_text, validate_rows, normalize_source_row


class WahisCsvConnector:
    """WAHIS connector.

    Priority:
    1. WAHIS_REMOTE_CSV_URL environment variable, if configured
    2. data/wahis_import/wahis_events.csv
    3. data/wahis_import/wahis_events_template.csv

    This connector expects a normalized CSV schema. If WOAH/WAHIS provides a direct
    bulk CSV export for the selected data, configure its URL in WAHIS_REMOTE_CSV_URL.
    """

    source_name = "WAHIS_CSV"

    def __init__(self, path: str = "data/wahis_import/wahis_events.csv") -> None:
        self.path = Path(path)
        self.template_path = Path("data/wahis_import/wahis_events_template.csv")
        self.remote_url = os.getenv("WAHIS_REMOTE_CSV_URL", "").strip()
        self.last_errors: List[Dict[str, Any]] = []
        self.last_mode = "not_run"
        self.last_snapshot: str | None = None

    def fetch(self) -> List[Dict[str, Any]]:
        if self.remote_url:
            try:
                csv_text = download_text(self.remote_url, timeout=int(os.getenv("SOURCE_DOWNLOAD_TIMEOUT_SECONDS", "30")))
                self.last_snapshot = save_snapshot("wahis", csv_text)
                self.last_mode = "remote"
                return self.parse_csv_text(csv_text)
            except Exception as exc:
                self.last_errors = [{"error": "remote_download_failed", "message": str(exc)}]
                if os.getenv("SOURCE_REMOTE_STRICT", "false").lower() == "true":
                    raise
                # fall through to local fallback

        path = self.path if self.path.exists() else self.template_path
        if not path.exists():
            self.last_mode = "none"
            return []
        self.last_mode = "local_file" if path == self.path else "template"
        return self.parse_csv_text(path.read_text(encoding="utf-8-sig"))

    @staticmethod
    def parse_csv_text(csv_text: str) -> List[Dict[str, Any]]:
        rows = read_csv_text(csv_text)
        valid, _errors = validate_rows(rows)
        return [normalize_source_row(row, "WAHIS") for row in valid]
