from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class OfficialDemoConnector:
    """Demo connector for official animal disease events.

    This connector intentionally reads from a local JSON seed file. It mirrors the
    shape expected from official public sources such as WAHIS/ADIS, but does not
    scrape or call external services. Replace fetch() with a real authorised
    connector when credentials / approved source access are available.
    """

    source_name = "OFFICIAL_DEMO"

    def __init__(self, path: str = "data/official_events_seed.json"):
        self.path = Path(path)

    def fetch(self, since: str | None = None) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            return []
        return rows
