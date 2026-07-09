from __future__ import annotations

from typing import Any, Dict


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def normalize_official_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one official-source event into the backend schema."""
    disease_it = raw.get("disease_it") or raw.get("disease") or "Malattia non specificata"
    disease = raw.get("disease") or disease_it

    return {
        "external_id": raw.get("external_id") or raw.get("id"),
        "source": raw.get("source") or "OFFICIAL_UNKNOWN",
        "source_type": raw.get("source_type") or "official",
        "report_type": raw.get("report_type") or "official_confirmed",
        "disease": disease,
        "disease_it": disease_it,
        "diagnosis_status": raw.get("diagnosis_status") or "Confermato",
        "species": raw.get("species") or "Specie non specificata",
        "animal_group": raw.get("animal_group") or "unknown",
        "observation_date": raw.get("observation_date") or raw.get("date") or "",
        "report_date": raw.get("report_date") or raw.get("observation_date") or raw.get("date") or "",
        "country": raw.get("country") or "Italy",
        "region": raw.get("region") or "",
        "location": raw.get("location") or raw.get("locality") or "",
        "lat": _float_or_none(raw.get("lat") or raw.get("latitude")),
        "lon": _float_or_none(raw.get("lon") or raw.get("lng") or raw.get("longitude")),
        "url_source": raw.get("url_source") or raw.get("source_url") or "",
        "notes": raw.get("notes") or "",
        "raw_payload": raw,
    }
