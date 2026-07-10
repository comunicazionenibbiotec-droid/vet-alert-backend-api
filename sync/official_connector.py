from __future__ import annotations
import json
from pathlib import Path
class OfficialDemoConnector:
    source_name = "OFFICIAL_DEMO"
    def __init__(self, path: str = "data/official_events_seed.json"):
        self.path = Path(path)
    def fetch(self, since: str | None = None):
        if not self.path.exists(): return []
        rows=json.loads(self.path.read_text(encoding="utf-8"))
        return rows if isinstance(rows,list) else []
