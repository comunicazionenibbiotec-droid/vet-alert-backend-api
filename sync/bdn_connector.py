from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List


class BdnDensityConnector:
    """Load Italian livestock density data for risk context.

    This connector is designed for aggregated public or authorized BDN-derived data.
    It is NOT an outbreak connector. It provides denominator/exposure context:
    region, province, species, heads, farms, density level.
    """

    source_name = "BDN_DENSITY_IT"

    def __init__(self, json_path: str = "data/bdn/livestock_density_it.json", csv_path: str = "data/bdn/livestock_density_it.csv"):
        self.json_path = Path(json_path)
        self.csv_path = Path(csv_path)

    def fetch(self) -> List[Dict[str, Any]]:
        if self.json_path.exists():
            with self.json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data["items"]
            if isinstance(data, list):
                return data
            return []

        if self.csv_path.exists():
            with self.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
                return list(csv.DictReader(f))

        return []


def normalize_density_row(row: Dict[str, Any]) -> Dict[str, Any]:
    def to_int(value: Any) -> int | None:
        try:
            if value in (None, ""):
                return None
            return int(float(str(value).replace(",", ".")))
        except Exception:
            return None

    species = str(row.get("species") or row.get("animal_group") or "").lower().strip()
    return {
        "country": row.get("country", "Italy"),
        "region": row.get("region", ""),
        "province": row.get("province", ""),
        "species": species,
        "species_label": row.get("species_label", row.get("species_it", species)),
        "farms_count": to_int(row.get("farms_count")),
        "heads_count": to_int(row.get("heads_count")),
        "density_level": row.get("density_level", "unknown"),
        "risk_relevance": row.get("risk_relevance", ""),
        "notes": row.get("notes", ""),
        "source": row.get("source", "BDN aggregated/prototype"),
        "source_type": "risk_context",
    }
