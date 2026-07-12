from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from sync.source_schema import read_csv_text, validate_rows, normalize_source_row


class AdisCsvConnector:
    source_name = "ADIS_CSV"

    def __init__(self, path: str = "data/adis_import/adis_events.csv") -> None:
        self.path = Path(path)
        self.template_path = Path("data/adis_import/adis_events_template.csv")
        self.last_errors: List[Dict[str, Any]] = []

    def fetch(self) -> List[Dict[str, Any]]:
        path = self.path if self.path.exists() else self.template_path
        if not path.exists():
            self.last_errors = []
            return []
        rows = self.parse_csv_text(path.read_text(encoding="utf-8-sig"))
        return rows

    @staticmethod
    def parse_csv_text(csv_text: str) -> List[Dict[str, Any]]:
        rows = read_csv_text(csv_text)
        valid, _errors = validate_rows(rows)
        return [normalize_source_row(row, "ADIS") for row in valid]
