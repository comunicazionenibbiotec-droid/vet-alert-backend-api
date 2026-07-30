from __future__ import annotations
from typing import Any, Dict

def _float_or_none(value: Any):
    try:
        if value is None or value == "": return None
        return float(str(value).replace(",","."))
    except Exception: return None

def _first_value(raw: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = raw.get(k)
        if v not in (None, ""):
            return v
    return ""


def _boolish(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "si", "sì"}:
        return "true"
    if text in {"false", "0", "no"}:
        return "false"
    return str(value or "").strip()


def normalize_official_event(raw: Dict[str, Any], default_source: str = "OFFICIAL_UNKNOWN") -> Dict[str, Any]:
    disease_it = raw.get("disease_it") or raw.get("disease") or raw.get("Disease") or "Malattia non specificata"
    disease = raw.get("disease") or raw.get("Disease") or disease_it
    source = raw.get("source") or raw.get("Source") or default_source
    suspected_date = _first_value(raw, "suspected_date", "Data sospetto", "data_sospetto")
    confirmed_date = _first_value(raw, "confirmed_date", "Data conferma", "data_conferma")
    extinction_date = _first_value(raw, "extinction_date", "Data estinzione", "data_estinzione")
    event_status = _first_value(raw, "event_status", "stato_evento")
    is_active = _boolish(_first_value(raw, "is_active", "active"))
    if not event_status:
        if extinction_date:
            event_status = "Estinto"
        elif confirmed_date:
            event_status = "Confermato / attivo"
        elif suspected_date:
            event_status = "Sospetto"
    if not is_active and extinction_date:
        is_active = "false"
    if not is_active and (confirmed_date or suspected_date) and not extinction_date:
        is_active = "true"
    observation_date = raw.get("observation_date") or raw.get("eventDate") or raw.get("date") or confirmed_date or suspected_date or ""
    report_date = raw.get("report_date") or raw.get("reportDate") or confirmed_date or suspected_date or observation_date or ""
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
        "observation_date": observation_date,
        "report_date": report_date,
        "suspected_date": suspected_date,
        "confirmed_date": confirmed_date,
        "extinction_date": extinction_date,
        "event_status": event_status,
        "is_active": is_active,
        "country": raw.get("country") or raw.get("Country") or "Italy",
        "region": raw.get("region") or raw.get("Region") or "",
        "location": raw.get("location") or raw.get("locality") or raw.get("Location") or "",
        "lat": _float_or_none(raw.get("lat") or raw.get("latitude") or raw.get("Latitude")),
        "lon": _float_or_none(raw.get("lon") or raw.get("lng") or raw.get("longitude") or raw.get("Longitude")),
        "url_source": raw.get("url_source") or raw.get("source_url") or raw.get("url") or "https://wahis.woah.org/",
        "notes": raw.get("notes") or "",
        "raw_payload": raw,
    }
