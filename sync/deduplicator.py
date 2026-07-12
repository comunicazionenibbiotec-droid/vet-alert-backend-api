from __future__ import annotations
import re
from datetime import datetime
from math import radians, sin, cos, asin, sqrt
from typing import Any, Dict, List, Tuple

EARTH_RADIUS_KM = 6371.0


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _date(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


def _distance_km(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    try:
        lat1, lon1 = float(a.get("lat")), float(a.get("lon"))
        lat2, lon2 = float(b.get("lat")), float(b.get("lon"))
    except Exception:
        return 999999.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    rlat1 = radians(lat1)
    rlat2 = radians(lat2)
    h = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))


def _is_official(event: Dict[str, Any]) -> bool:
    return str(event.get("source_type", "")).lower() == "official" or "official" in str(event.get("report_type", "")).lower()


def _is_same_event(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    # Same / similar disease
    da = _norm(a.get("disease_original") or a.get("disease"))
    db = _norm(b.get("disease_original") or b.get("disease"))
    if not da or not db or da != db:
        return False

    # Same animal group if available
    ga = _norm(a.get("animal_group") or a.get("species"))
    gb = _norm(b.get("animal_group") or b.get("species"))
    if ga and gb and ga != gb:
        return False

    # Near in time
    ad = _date(a.get("observation_date") or a.get("report_date"))
    bd = _date(b.get("observation_date") or b.get("report_date"))
    if ad and bd and abs((ad - bd).days) > 14:
        return False

    # Near in space. We keep this intentionally conservative.
    if _distance_km(a, b) > 25:
        return False

    return True


def _merge_events(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(primary)
    sources = set()
    for ev in (primary, secondary):
        raw_sources = ev.get("sources_merged") or []
        if isinstance(raw_sources, list):
            sources.update(str(x) for x in raw_sources if x)
        if ev.get("source"):
            sources.add(str(ev.get("source")))
    merged["sources_merged"] = sorted(sources)
    if len(sources) > 1:
        merged["source"] = " + ".join(sorted(sources))

    # Use the strongest status if either event is official/confirmed.
    status_text = f"{primary.get('diagnosis_status','')} {secondary.get('diagnosis_status','')} {primary.get('report_type','')} {secondary.get('report_type','')}".lower()
    if "conferm" in status_text or "confirm" in status_text or _is_official(primary) or _is_official(secondary):
        merged["diagnosis_status"] = primary.get("diagnosis_status") or secondary.get("diagnosis_status") or "Confermato"
        if _is_official(primary) or _is_official(secondary):
            merged["source_type"] = "official"
            merged["report_type"] = "official_confirmed"
    merged["duplicate_count"] = int(primary.get("duplicate_count", 1)) + int(secondary.get("duplicate_count", 1))
    return merged


def deduplicate_public_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge probable duplicates from WAHIS, ADIS and internal demo/user layers.

    This runs on the public response only, so it does not delete source records.
    Raw records remain available in the database and in sync logs.
    """
    merged: List[Dict[str, Any]] = []
    for event in events:
        current = dict(event)
        current.setdefault("sources_merged", [current.get("source")] if current.get("source") else [])
        current.setdefault("duplicate_count", 1)
        matched_index = None
        for idx, existing in enumerate(merged):
            if _is_same_event(existing, current):
                matched_index = idx
                break
        if matched_index is None:
            merged.append(current)
        else:
            a = merged[matched_index]
            # Prefer official events as primary when merging.
            primary, secondary = (a, current)
            if _is_official(current) and not _is_official(a):
                primary, secondary = current, a
            merged[matched_index] = _merge_events(primary, secondary)
    return merged
