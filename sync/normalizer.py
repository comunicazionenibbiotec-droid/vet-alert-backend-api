from __future__ import annotations
from typing import Any, Dict

def _float_or_none(value: Any):
    try:
        if value is None or value == "": return None
        return float(str(value).replace(",","."))
    except Exception: return None

def normalize_official_event(raw: Dict[str, Any], default_source: str = "OFFICIAL_UNKNOWN") -> Dict[str, Any]:
    disease_it = raw.get("disease_it") or raw.get("disease") or raw.get("Disease") or "Malattia non specificata"
    disease = raw.get("disease") or raw.get("Disease") or disease_it
    source = raw.get("source") or raw.get("Source") or default_source
    return {
        "external_id": raw.get("external_id") or raw.get("id") or raw.get("epiEventId") or raw.get("reportId"),
        "source": source,
        "source_type": raw.get("source_type") or "official",
        "report_type": raw.get("report_type") or "official_confirmed",
        "disease": disease,
        "disease_it": disease_it,
        "diagnosis_status": raw.get("diagnosis_status") or raw.get("status") or raw.get("eventStatus") or "Confermato",
        "species": raw.get("species") or raw.get("Species") or raw.get("animalSpecies") or "Specie non specificata",
        "animal_group": raw.get("animal_group") or raw.get("animalGroup") or "unknown",
        "observation_date": raw.get("observation_date") or raw.get("eventDate") or raw.get("date") or "",
        "report_date": raw.get("report_date") or raw.get("reportDate") or raw.get("observation_date") or raw.get("eventDate") or "",
        "country": raw.get("country") or raw.get("Country") or "Italy",
        "region": raw.get("region") or raw.get("Region") or "",
        "location": raw.get("location") or raw.get("locality") or raw.get("Location") or "",
        "lat": _float_or_none(raw.get("lat") or raw.get("latitude") or raw.get("Latitude")),
        "lon": _float_or_none(raw.get("lon") or raw.get("lng") or raw.get("longitude") or raw.get("Longitude")),
        "url_source": raw.get("url_source") or raw.get("source_url") or raw.get("url") or "https://wahis.woah.org/",
        "notes": raw.get("notes") or "",
        "raw_payload": raw,
    }
