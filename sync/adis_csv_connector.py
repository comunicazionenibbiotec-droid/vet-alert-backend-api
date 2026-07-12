from __future__ import annotations
import csv
from pathlib import Path
from typing import Any, Dict, List


class AdisCsvConnector:
    """CSV import connector for ADIS public/export data.

    It expects the same normalized columns used by the WAHIS CSV import:
    external_id, source, disease, disease_it, diagnosis_status, species,
    animal_group, observation_date, report_date, country, region, location,
    lat, lon, url_source, notes.

    If data/adis_import/adis_events.csv is not present, the connector falls back
    to data/adis_import/adis_events_template.csv so the sync endpoint remains safe.
    """

    source_name = "ADIS_CSV"

    def __init__(self, path: str = "data/adis_import/adis_events.csv") -> None:
        self.path = Path(path)
        self.template_path = Path("data/adis_import/adis_events_template.csv")

    def fetch(self) -> List[Dict[str, Any]]:
        path = self.path if self.path.exists() else self.template_path
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            row.setdefault("source", "ADIS")
            row.setdefault("source_type", "official")
            row.setdefault("report_type", "official_confirmed")
            row.setdefault("diagnosis_status", "Confermato")
        return rows
