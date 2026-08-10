import os
import argparse

import psycopg
from psycopg.rows import dict_row

from update_single_event_outbreak_link import update_single_event


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")


def get_anchor_event(conn, event_id):
    row = conn.execute(
        """
        SELECT id,
               disease,
               observation_date,
               location,
               region,
               lat,
               lon
        FROM events
        WHERE id = %s
        """,
        (event_id,),
    ).fetchone()

    if not row:
        raise RuntimeError(f"Anchor event not found: {event_id}")

    if row["observation_date"] is None:
        raise RuntimeError(f"Anchor event has no observation_date: {event_id}")

    if row["lat"] is None or row["lon"] is None:
        raise RuntimeError(f"Anchor event has no coordinates: {event_id}")

    return dict(row)


def get_window_events(conn, anchor, days_before, days_after):
    rows = conn.execute(
        """
        SELECT id,
               disease,
               observation_date,
               location,
               region,
               lat,
               lon
        FROM events
        WHERE disease = %s
          AND observation_date IS NOT NULL
          AND lat IS NOT NULL
          AND lon IS NOT NULL
          AND observation_date >= (%s::date - (%s::int || ' days')::interval)
          AND observation_date <= (%s::date + (%s::int || ' days')::interval)
        ORDER BY observation_date ASC, id ASC
        """,
        (
            anchor["disease"],
            anchor["observation_date"],
            days_before,
            anchor["observation_date"],
            days_after,
        ),
    ).fetchall()

    return [dict(row) for row in rows]


def mark_window_for_review(conn, event_ids):
    if not event_ids:
        return

    conn.execute(
        """
        UPDATE event_parent_links
        SET needs_review = true,
            updated_at = now()
        WHERE event_id = ANY(%s)
        """,
        (event_ids,),
    )

    conn.execute(
        """
        UPDATE event_branch_assignments
        SET needs_review = true,
            updated_at = now()
        WHERE event_id = ANY(%s)
        """,
        (event_ids,),
    )


def recalculate_window(conn, event_id, days_before, days_after):
    anchor = get_anchor_event(conn, event_id)

    window_events = get_window_events(
        conn,
        anchor,
        days_before,
        days_after,
    )

    event_ids = [event["id"] for event in window_events]

    mark_window_for_review(conn, event_ids)

    results = []

    for event in window_events:
        result = update_single_event(conn, event["id"])
        results.append(result)

    return {
        "anchor_event_id": event_id,
        "disease": anchor["disease"],
        "anchor_date": str(anchor["observation_date"]),
        "anchor_location": anchor["location"],
        "anchor_region": anchor["region"],
        "days_before": days_before,
        "days_after": days_after,
        "events_recalculated": len(results),
        "event_ids": event_ids,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--days-before", type=int, default=30)
    parser.add_argument("--days-after", type=int, default=30)

    args = parser.parse_args()

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        result = recalculate_window(
            conn,
            args.event_id,
            args.days_before,
            args.days_after,
        )

        conn.commit()

        print(result)


if __name__ == "__main__":
    main()
