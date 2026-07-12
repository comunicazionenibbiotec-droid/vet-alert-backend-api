"""
vet.ector backend v86 - demo events control helpers.

Purpose:
- Keep demo events visible during prototype phase.
- Allow hiding demo events in the public/pilot phase using SHOW_DEMO_EVENTS=false.
- Allow purging old demo events using PURGE_DEMO_OLDER_THAN_DAYS.

This module is intentionally dependency-light and can be imported from main.py.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable, Mapping

DEMO_SOURCE_NAMES = {
    "demo 365 giorni",
    "demo",
    "demo_365",
    "demo365",
}


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def show_demo_events() -> bool:
    """Return whether demo events should be returned by public event endpoints."""
    return _truthy(os.getenv("SHOW_DEMO_EVENTS"), default=True)


def auto_populate_demo_365() -> bool:
    """Return whether demo 365 events should be generated at startup/sync."""
    return _truthy(os.getenv("AUTO_POPULATE_DEMO_365"), default=True)


def purge_demo_older_than_days() -> int:
    """Return the purge threshold for demo events. Default: 365 days."""
    try:
        return int(os.getenv("PURGE_DEMO_OLDER_THAN_DAYS", "365"))
    except Exception:
        return 365


def is_demo_event(event: Mapping[str, Any]) -> bool:
    """Detect whether an event is a temporary demo event."""
    source = str(event.get("source", "")).strip().lower()
    source_type = str(event.get("source_type", "")).strip().lower()
    report_type = str(event.get("report_type", "")).strip().lower()
    external_id = str(event.get("external_id", event.get("id", ""))).strip().lower()

    if source in DEMO_SOURCE_NAMES:
        return True
    if "demo" in source:
        return True
    if source_type == "demo":
        return True
    if "demo" in report_type:
        return True
    if external_id.startswith("demo365-") or external_id.startswith("demo-"):
        return True
    return False


def filter_demo_events(events: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Return events, optionally excluding demo records depending on SHOW_DEMO_EVENTS."""
    events_list = list(events)
    if show_demo_events():
        return events_list
    return [event for event in events_list if not is_demo_event(event)]


def demo_status() -> dict[str, Any]:
    """Return current demo configuration for status endpoints."""
    return {
        "show_demo_events": show_demo_events(),
        "auto_populate_demo_365": auto_populate_demo_365(),
        "purge_demo_older_than_days": purge_demo_older_than_days(),
        "demo_sources": sorted(DEMO_SOURCE_NAMES),
        "recommended_public_settings": {
            "SHOW_DEMO_EVENTS": "false",
            "AUTO_POPULATE_DEMO_365": "false",
            "PURGE_DEMO_OLDER_THAN_DAYS": "365",
        },
        "recommended_prototype_settings": {
            "SHOW_DEMO_EVENTS": "true",
            "AUTO_POPULATE_DEMO_365": "true",
            "PURGE_DEMO_OLDER_THAN_DAYS": "365",
        },
    }


def _cutoff_iso(days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff.date().isoformat()


def purge_demo_events_sqlite(conn: Any, table_name: str = "events", older_than_days: int | None = None) -> dict[str, Any]:
    """
    Purge demo events from a SQLite table.

    Expected columns in the events table may include:
    - source
    - source_type
    - report_type
    - external_id
    - observation_date

    The function is defensive: it tries common column names and returns a report.
    If your backend stores demo records in another table, call this function with
    the correct table name or adapt the DELETE condition in main.py.
    """
    days = older_than_days if older_than_days is not None else purge_demo_older_than_days()
    cutoff = _cutoff_iso(days)
    cur = conn.cursor()

    delete_sql = f"""
    DELETE FROM {table_name}
    WHERE (
        lower(coalesce(source, '')) LIKE '%demo%'
        OR lower(coalesce(source_type, '')) = 'demo'
        OR lower(coalesce(report_type, '')) LIKE '%demo%'
        OR lower(coalesce(external_id, '')) LIKE 'demo365-%'
        OR lower(coalesce(external_id, '')) LIKE 'demo-%'
    )
    AND date(coalesce(observation_date, report_date, created_at, '1900-01-01')) < date(?)
    """
    try:
        cur.execute(delete_sql, (cutoff,))
        deleted = cur.rowcount if cur.rowcount is not None else 0
        conn.commit()
        return {"status": "ok", "deleted": deleted, "cutoff_date": cutoff, "table": table_name}
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"status": "error", "error": str(exc), "cutoff_date": cutoff, "table": table_name}
