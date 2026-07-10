from __future__ import annotations
import csv, io
from pathlib import Path
class WahisCsvConnector:
    source_name = "WAHIS_CSV"
    def __init__(self, path="data/wahis_import/wahis_events.csv", fallback_path="data/wahis_import/wahis_events_template.csv"):
        self.path=Path(path); self.fallback_path=Path(fallback_path)
    @staticmethod
    def parse_csv_text(csv_text: str):
        if not csv_text or not csv_text.strip(): return []
        if csv_text.startswith("﻿"): csv_text=csv_text.lstrip("﻿")
        rows=[]; reader=csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            cleaned={str(k).strip():(v.strip() if isinstance(v,str) else v) for k,v in row.items() if k is not None}
            if any(cleaned.values()): rows.append(cleaned)
        return rows
    def fetch(self, since: str | None = None):
        path=self.path if self.path.exists() else self.fallback_path
        if not path.exists(): return []
        return self.parse_csv_text(path.read_text(encoding="utf-8-sig"))
