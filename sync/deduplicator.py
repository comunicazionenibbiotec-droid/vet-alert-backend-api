"""
vet.ector backend v99 - conservative official-event deduplication.

Purpose
-------
This module deduplicates only when doing so is safe for public map display.

Rules implemented in v99:
- Never merge demo/prototype records with real official records.
- Never merge ADIS with ADIS: each ADIS external_id remains a distinct event.
- Never merge WAHIS with WAHIS: each WAHIS external_id remains a distinct event.
- Merge ADIS + WAHIS only when they are very likely the same outbreak
  (same disease, same animal group, very close date, very close location).
- Never merge user/demo reports with other user/demo reports.
- This function does not mutate or delete database rows. It only prepares the API response.
"""
from __future__ import annotations

from datetime import datetime, date
from math import radians, sin, cos, asin, sqrt
from typing import Any, Dict, Iterable, List, Optional, Tuple

Event = Dict[str, Any]


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _norm_disease(event: Event) -> str:
    return _norm(
        event.get("disease_normalized")
        or event.get("disease")
        or event.get("disease_it")
        or event.get("disease_original")
    )


def _norm_animal_group(event: Event) -> str:
    return _norm(event.get("animal_group") or event.get("species"))


def _source_text(event: Event) -> str:
    parts: List[str] = []
    for key in ("source", "source_type", "report_type"):
        value = event.get(key)
        if value:
            parts.append(str(value))
    merged = event.get("sources_merged")
    if isinstance(merged, list):
        parts.extend(str(x) for x in merged if x)
    return " ".join(parts).lower()


def _source_family(event: Event) -> str:
    """Return a normalized broad source family."""
    text = _source_text(event)
    source = _norm(event.get("source"))

    if "demo 365" in text or "official_demo" in text or "seed_demo" in text or source in {"demo", "demo365", "demo 365 giorni", "official_demo"}:
        return "demo"
    if "adis" in text:
        return "adis"
    if "wahis" in text or "woah" in text:
        return "wahis"
    if "veterin" in text or " vet" in f" {text}" or "vet_" in text:
        return "vet"
    if "rapid" in text or "leggi test" in text or "test" in _norm(event.get("report_type")):
        return "rapid_test"
    if "user" in text or "utente" in text:
        return "user"
    if "company" in text or "azienda" in text:
        return "company"
    if "association" in text or "associazione" in text:
        return "association"
    if "official" in text:
        return "other_official"
    return "other"


def _is_demo(event: Event) -> bool:
    return _source_family(event) == "demo"


def _is_real_official(event: Event) -> bool:
    return _source_family(event) in {"adis", "wahis", "other_official"}


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")[:10]).date()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except Exception:
            continue
    return None


def _event_date(event: Event) -> Optional[date]:
    return _parse_date(event.get("observation_date") or event.get("event_date") or event.get("report_date"))


def _date_diff_days(a: Event, b: Event) -> Optional[int]:
    da = _event_date(a)
    db = _event_date(b)
    if not da or not db:
        return None
    return abs((da - db).days)


def _float_or_none(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _distance_km(a: Event, b: Event) -> Optional[float]:
    lat1 = _float_or_none(a.get("lat"))
    lon1 = _float_or_none(a.get("lon"))
    lat2 = _float_or_none(b.get("lat"))
    lon2 = _float_or_none(b.get("lon"))
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(h))


def _same_species_or_group(a: Event, b: Event) -> bool:
    ga = _norm_animal_group(a)
    gb = _norm_animal_group(b)
    if ga and gb and ga == gb:
        return True
    sa = _norm(a.get("species"))
    sb = _norm(b.get("species"))
    return bool(sa and sb and sa == sb)


def _can_merge(a: Event, b: Event) -> bool:
    """Return True only when two public events should be represented as one marker."""
    if not _norm_disease(a) or _norm_disease(a) != _norm_disease(b):
        return False
    if not _same_species_or_group(a, b):
        return False

    family_a = _source_family(a)
    family_b = _source_family(b)

    # Demo/prototype data must never collapse real ADIS/WAHIS records.
    if family_a == "demo" or family_b == "demo":
        return False

    # Preserve ADIS outbreak granularity: each external_id is a distinct notification.
    if family_a == family_b and family_a in {"adis", "wahis"}:
        return False

    # Do not merge non-official/community events together.
    if not _is_real_official(a) and not _is_real_official(b):
        return False

    date_gap = _date_diff_days(a, b)
    dist = _distance_km(a, b)

    # ADIS + WAHIS can be merged, but only with strict criteria.
    if {family_a, family_b} == {"adis", "wahis"}:
        if date_gap is not None and date_gap > 7:
            return False
        if dist is None:
            return False
        return dist <= 5.0

    # Other official cross-source merge: conservative.
    if _is_real_official(a) and _is_real_official(b):
        if date_gap is not None and date_gap > 7:
            return False
        if dist is None:
            return False
        return dist <= 5.0

    # Official + user/test/vet: do not merge in v99. Keep evidence layers visible.
    return False


def _event_sort_key(event: Event) -> Tuple[int, float, str]:
    family = _source_family(event)
    official_rank = 0 if family in {"adis", "wahis", "other_official"} else 1
    risk = _float_or_none(event.get("risk_score")) or 0.0
    date_str = str(event.get("observation_date") or event.get("report_date") or "")
    return (official_rank, -risk, date_str)


def _merge_cluster(cluster: List[Event]) -> Event:
    if not cluster:
        return {}
    cluster_sorted = sorted(cluster, key=_event_sort_key)
    primary = dict(cluster_sorted[0])

    sources: List[str] = []
    source_event_ids: List[str] = []
    for ev in cluster_sorted:
        source = str(ev.get("source") or "").strip()
        if source and source not in sources:
            sources.append(source)
        external_id = str(ev.get("external_id") or ev.get("id") or "").strip()
        if external_id and external_id not in source_event_ids:
            source_event_ids.append(external_id)

    primary["sources_merged"] = sources or [str(primary.get("source") or "")]
    primary["source_event_ids_merged"] = source_event_ids
    primary["duplicate_count"] = len(cluster_sorted)
    primary["deduplication_applied"] = len(cluster_sorted) > 1

    if len(sources) > 1:
        primary["source"] = " + ".join(sources)

    return primary


def deduplicate_events(events: Iterable[Event]) -> List[Event]:
    remaining = [dict(e) for e in events]
    clusters: List[List[Event]] = []

    while remaining:
        current = remaining.pop(0)
        cluster = [current]
        keep: List[Event] = []
        for candidate in remaining:
            if any(_can_merge(member, candidate) for member in cluster):
                cluster.append(candidate)
            else:
                keep.append(candidate)
        clusters.append(cluster)
        remaining = keep

    merged = [_merge_cluster(cluster) for cluster in clusters]
    merged.sort(key=lambda e: -(_float_or_none(e.get("risk_score")) or 0.0))
    return merged


def deduplicate_public_events(events: Iterable[Event]) -> List[Event]:
    return deduplicate_events(events)
