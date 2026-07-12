from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class EfsaRiskLayerConnector:
    """Load EFSA-inspired disease risk layers.

    EFSA is used here as scientific/risk context, not as a point outbreak source.
    This file can later be replaced by manually curated EFSA reports or authorized APIs.
    """

    source_name = "EFSA_RISK_LAYER"

    def __init__(self, path: str = "data/risk_layers/efsa_risk_layers.json"):
        self.path = Path(path)

    def fetch(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return data["items"]
        if isinstance(data, list):
            return data
        return []


def normalize_risk_layer(row: Dict[str, Any]) -> Dict[str, Any]:
    species = row.get("species") or []
    if isinstance(species, str):
        species = [s.strip().lower() for s in species.split(";") if s.strip()]
    return {
        "disease": row.get("disease", ""),
        "disease_key": str(row.get("disease_key") or row.get("disease") or "").lower().replace(" ", "_"),
        "species": species,
        "regions": row.get("regions", []),
        "seasonality": row.get("seasonality", ""),
        "risk_level": row.get("risk_level", "unknown"),
        "risk_factor": row.get("risk_factor", ""),
        "recommended_action": row.get("recommended_action", ""),
        "source": row.get("source", "EFSA context/prototype"),
        "source_type": "risk_context",
        "notes": row.get("notes", ""),
    }
