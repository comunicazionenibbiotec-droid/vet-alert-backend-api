"""
vet.ector backend v85 - safer public-event deduplication.

Purpose
-------
Deduplicate ONLY when doing so is safe for map display:
- official + official: deduplicate with normal thresholds
- official + user/demo/test/vet: deduplicate only when very close and same/similar date
- user + user / demo + demo / non-official + non-official: do NOT deduplicate

This module is designed as a drop-in replacement if main.py already imports
`deduplicate_events` from `sync.deduplicator`.
"""
from __future__ import annotations

from datetime import datetime, date
from math import radians, sin, cos, asin, sqrt
from typing import Any, Dict, Iterable, List, Optional, Tuple

Event = Dict[str, Any]


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _norm_disease(event: Event) -> str:
    return _norm(event.get("disease_normalized") or event.get("disease") or event.get("disease_it") or event.get("disease_original"))


def _norm_animal_group(event: Event) -> str:
    return _norm(event.get("animal_group") or event.get("species"))


def _source_type(event: Event) -> str:
    return _norm(event.get("source_type") or event.get("report_type") or event.get("source"))


def _is_official(event: Event) -> bool:
    source_type = _source_type(event)
    source = _norm(event.get("source"))
    report_type = _norm(event.get("report_type"))
    return (
        "official" in source_type
        or "official" in report_type
        or source in {"wahis", "adis", "woah", "official_demo"}
        or source.startswith("wahis")
        or source.startswith("adis")
    )


def _is_non_official_demo_or_user(event: Event) -> bool:
    source_type = _source_type(event)
    source = _norm(event.get("source"))
    report_type = _norm(event.get("report_type"))
    return (
        "user" in source_type
        or "user" in report_type
        or "demo" in source
        or source in {"demo 365 giorni", "demo365"}
        or "test" in report_type
        or "vet" in source_type
    )


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(text[:19] if "T" in text else text, fmt).date()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
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


def _same_area(a: Event, b: Event) -> bool:
    # Prefer administrative fields when available.
    for key in ("country", "region", "province", "location"):
        av = _norm(a.get(key))
        bv = _norm(b.get(key))
        if av and bv and av == bv:
            return True
    d = _distance_km(a, b)
    return d is not None and d <= 25.0


def _same_species_or_group(a: Event, b: Event) -> bool:
    ga = _norm_animal_group(a)
    gb = _norm_animal_group(b)
    if ga and gb and ga == gb:
        return True
    sa = _norm(a.get("species"))
    sb = _norm(b.get("species"))
    return bool(sa and sb and sa == sb)


def _can_merge(a: Event, b: Event) -> bool:
    # Must be the same disease and compatible species/group.
    if not _norm_disease(a) or _norm_disease(a) != _norm_disease(b):
        return False
    if not _same_species_or_group(a, b):
        return False

    a_off = _is_official(a)
    b_off = _is_official(b)

    # Never merge non-official with non-official. Multiple user/demo reports may be independent cases.
    if not a_off and not b_off:
        return False

    date_gap = _date_diff_days(a, b)
    dist = _distance_km(a, b)

    # Official + official: normal threshold.
    if a_off and b_off:
        if date_gap is not None and date_gap > 14:
            return False
        if dist is not None and dist > 50:
            return False
        return _same_area(a, b) or dist is None

    # Official + non-official: only merge when very likely the same event.
    # Very close geographically AND close in time.
    if date_gap is not None and date_gap > 3:
        return False
    if dist is not None and dist > 10:
        return False
    return True


def _event_sort_key(event: Event) -> Tuple[int, float, str]:
    # Prefer official, then higher risk, then newer date.
    official_rank = 0 if _is_official(event) else 1
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
    """Return public-display events with safer deduplication.

    This function does not delete or mutate database rows. It only prepares the API response.
    """
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
    # Keep the same rough ordering expected by the frontend.
    merged.sort(key=lambda e: -(_float_or_none(e.get("risk_score")) or 0.0))
    return merged


# Backward-compatible alias for possible previous imports.
def deduplicate_public_events(events: Iterable[Event]) -> List[Event]:
    return deduplicate_events(events)
