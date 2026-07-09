from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Dict, List


class WahisCsvConnector:
    """CSV connector for WAHIS exports or WAHIS-normalised bulk downloads.

    Expected columns:
    external_id, source, disease, disease_it, diagnosis_status, species,
    animal_group, observation_date, report_date, country, region, location,
    lat, lon, url_source, notes.
    """

    source_name = "WAHIS_CSV"

    def __init__(
        self,
        path: str = "data/wahis_import/wahis_events.csv",
        fallback_path: str = "data/wahis_import/wahis_events_template.csv",
    ):
        self.path = Path(path)
        self.fallback_path = Path(fallback_path)

    @staticmethod
    def parse_csv_text(csv_text: str) -> List[Dict[str, Any]]:
        if not csv_text or not csv_text.strip():
            return []
        if csv_text.startswith("\ufeff"):
            csv_text = csv_text.lstrip("\ufeff")
        reader = csv.DictReader(io.StringIO(csv_text))
        rows: List[Dict[str, Any]] = []
        for row in reader:
            cleaned = {
                str(k).strip(): (v.strip() if isinstance(v, str) else v)
                for k, v in row.items()
                if k is not None
            }
            if any(cleaned.values()):
                rows.append(cleaned)
        return rows

    def fetch(self, since: str | None = None) -> List[Dict[str, Any]]:
        path = self.path if self.path.exists() else self.fallback_path
        if not path.exists():
            return []
        return self.parse_csv_text(path.read_text(encoding="utf-8-sig"))
