import os
import math
import argparse
from datetime import date

import psycopg
from psycopg.rows import dict_row


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))

    a = math.sin(dp / 2) ** 2
    a += math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2

    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def days_between(a, b):
    if not a or not b:
        return None

    if isinstance(a, date) and isinstance(b, date):
        return (b - a).days

    return None


def get_event(conn, event_id):
    row = conn.execute(
        """
        SELECT id,
               disease,
               source,
               source_type,
               observation_date,
               location,
               region,
               province,
               lat,
               lon
        FROM events
        WHERE id = %s
        """,
        (event_id,),
    ).fetchone()

    if not row:
        raise RuntimeError(f"Event not found: {event_id}")

    if row["observation_date"] is None:
        raise RuntimeError(f"Event has no observation_date: {event_id}")

    if row["lat"] is None or row["lon"] is None:
        raise RuntimeError(f"Event has no coordinates: {event_id}")

    return dict(row)


def load_config(conn, disease):
    row = conn.execute(
        """
        SELECT max_parent_distance_km,
               max_parent_time_gap_days
        FROM disease_branching_config
        WHERE disease = %s
        """,
        (disease,),
    ).fetchone()

    if not row:
        return {
            "max_distance": 100.0,
            "max_days": 90,
        }

    return {
        "max_distance": float(row["max_parent_distance_km"]),
        "max_days": int(row["max_parent_time_gap_days"]),
    }


def get_chronological_previous(conn, event):
    row = conn.execute(
        """
        SELECT id
        FROM events
        WHERE disease = %s
          AND observation_date IS NOT NULL
          AND (
            observation_date < %s
            OR (
              observation_date = %s
              AND id < %s
            )
          )
        ORDER BY observation_date DESC, id DESC
        LIMIT 1
        """,
        (
            event["disease"],
            event["observation_date"],
            event["observation_date"],
            event["id"],
        ),
    ).fetchone()

    return row["id"] if row else None


def get_candidates(conn, event, config):
    rows = conn.execute(
        """
        SELECT e.id,
               e.disease,
               e.source,
               e.source_type,
               e.observation_date,
               e.location,
               e.region,
               e.province,
               e.lat,
               e.lon,
               a.series_id,
               a.branch_id
        FROM events e
        LEFT JOIN event_branch_assignments a
          ON a.event_id = e.id
        WHERE e.disease = %s
          AND e.id <> %s
          AND e.observation_date IS NOT NULL
          AND e.lat IS NOT NULL
          AND e.lon IS NOT NULL
          AND e.observation_date <= %s
          AND e.observation_date >= (%s::date - (%s::int || ' days')::interval)
        ORDER BY e.observation_date DESC, e.id DESC
        """,
        (
            event["disease"],
            event["id"],
            event["observation_date"],
            event["observation_date"],
            int(config["max_days"]),
        ),
    ).fetchall()

    return [dict(row) for row in rows]


def score_candidate(candidate, event, config):
    delta_days = days_between(candidate["observation_date"], event["observation_date"])

    if delta_days is None:
        return None

    if delta_days < 0:
        return None

    if delta_days > config["max_days"]:
        return None

    distance = haversine_km(candidate["lat"], candidate["lon"], event["lat"], event["lon"])

    if distance > config["max_distance"]:
        return None

    spatial_score = 1.0 - distance / config["max_distance"]
    temporal_score = 1.0 - delta_days / config["max_days"]
    branch_score = 1.0 if candidate.get("branch_id") else 0.35
    evidence_score = 1.0 if event.get("source_type") == "official" else 0.5

    score = 0.40 * spatial_score
    score += 0.30 * temporal_score
    score += 0.20 * branch_score
    score += 0.10 * evidence_score

    return {
        "candidate": candidate,
        "score": score,
        "distance": distance,
        "days": delta_days,
    }


def classify_link(score):
    if score is None:
        return "no_parent"

    if score >= 0.75:
        return "probable_parent"

    if score >= 0.50:
        return "possible_parent"

    return "no_parent"


def create_series(conn, event):
    disease_slug = event["disease"].lower().replace(" ", "-")

    row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM outbreak_series
        WHERE disease = %s
        """,
        (event["disease"],),
    ).fetchone()

    number = int(row["c"]) + 1

    series_id = f"series-{disease_slug}-{number:04d}"
    series_code = f"{disease_slug.upper()}-INCREMENTAL-S{number:04d}"

    conn.execute(
        """
        INSERT INTO outbreak_series (
          id,
          disease,
          series_code,
          root_event_id,
          root_date,
          root_location,
          root_region,
          status,
          first_event_date,
          last_event_date,
          event_count,
          created_at,
          updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s, %s, 1, now(), now())
        """,
        (
            series_id,
            event["disease"],
            series_code,
            event["id"],
            event["observation_date"],
            event["location"],
            event["region"],
            event["observation_date"],
            event["observation_date"],
        ),
    )

    return series_id


def get_or_create_branch(conn, series_id, event):
    row = conn.execute(
        """
        SELECT id
        FROM outbreak_branches
        WHERE series_id = %s
        ORDER BY branch_code
        LIMIT 1
        """,
        (series_id,),
    ).fetchone()

    if row:
        return row["id"]

    branch_id = f"branch-{series_id}-b01"

    conn.execute(
        """
        INSERT INTO outbreak_branches (
          id,
          series_id,
          branch_code,
          branch_name,
          branch_level,
          root_event_id,
          direction_label,
          first_event_date,
          last_event_date,
          event_count,
          confidence_score,
          created_at,
          updated_at
        )
        VALUES (%s, %s, 'B01', 'Root area', 1, %s, 'ROOT', %s, %s, 1, 0.70, now(), now())
        """,
        (
            branch_id,
            series_id,
            event["id"],
            event["observation_date"],
            event["observation_date"],
        ),
    )

    return branch_id


def upsert_assignment(conn, event_id, series_id, branch_id):
    conn.execute(
        """
        INSERT INTO event_branch_assignments (
          event_id,
          series_id,
          branch_id,
          assignment_score,
          assignment_method,
          created_at,
          updated_at
        )
        VALUES (%s, %s, %s, 0.70, 'incremental_single_event_update', now(), now())
        ON CONFLICT (event_id)
        DO UPDATE SET
          series_id = EXCLUDED.series_id,
          branch_id = EXCLUDED.branch_id,
          assignment_score = EXCLUDED.assignment_score,
          assignment_method = EXCLUDED.assignment_method,
          updated_at = now()
        """,
        (event_id, series_id, branch_id),
    )


def upsert_parent_link(conn, link):
    conn.execute(
        """
        INSERT INTO event_parent_links (
          event_id,
          series_id,
          probable_parent_event_id,
          chronological_previous_event_id,
          parent_score,
          distance_from_parent_km,
          days_from_parent,
          estimated_spread_speed_km_day,
          link_type,
          created_at,
          updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (event_id)
        DO UPDATE SET
          series_id = EXCLUDED.series_id,
          probable_parent_event_id = EXCLUDED.probable_parent_event_id,
          chronological_previous_event_id = EXCLUDED.chronological_previous_event_id,
          parent_score = EXCLUDED.parent_score,
          distance_from_parent_km = EXCLUDED.distance_from_parent_km,
          days_from_parent = EXCLUDED.days_from_parent,
          estimated_spread_speed_km_day = EXCLUDED.estimated_spread_speed_km_day,
          link_type = EXCLUDED.link_type,
          updated_at = now()
        """,
        (
            link["event_id"],
            link["series_id"],
            link["probable_parent_event_id"],
            link["chronological_previous_event_id"],
            link["parent_score"],
            link["distance_from_parent_km"],
            link["days_from_parent"],
            link["estimated_spread_speed_km_day"],
            link["link_type"],
        ),
    )


def update_single_event(conn, event_id):
    event = get_event(conn, event_id)
    config = load_config(conn, event["disease"])
    chronological_previous = get_chronological_previous(conn, event)
    candidates = get_candidates(conn, event, config)

    best = None

    for candidate in candidates:
        scored = score_candidate(candidate, event, config)

        if scored is None:
            continue

        if best is None or scored["score"] > best["score"]:
            best = scored

    parent_id = None
    parent_score = None
    distance = None
    days = None
    speed = None
    current_link_type = "no_parent"

    if best:
        parent_score = best["score"]
        current_link_type = classify_link(parent_score)
        distance = best["distance"]
        days = best["days"]

        if days and days > 0:
            speed = distance / days

        if current_link_type != "no_parent":
            parent_id = best["candidate"]["id"]

    existing = conn.execute(
        """
        SELECT series_id,
               branch_id
        FROM event_branch_assignments
        WHERE event_id = %s
        """,
        (event_id,),
    ).fetchone()

    if existing:
        series_id = existing["series_id"]
    elif best and best["candidate"].get("series_id") and current_link_type != "no_parent":
        series_id = best["candidate"]["series_id"]
    else:
        series_id = create_series(conn, event)

    branch_id = get_or_create_branch(conn, series_id, event)

    upsert_assignment(conn, event_id, series_id, branch_id)

    upsert_parent_link(
        conn,
        {
            "event_id": event_id,
            "series_id": series_id,
            "probable_parent_event_id": parent_id,
            "chronological_previous_event_id": chronological_previous,
            "parent_score": parent_score,
            "distance_from_parent_km": distance,
            "days_from_parent": days,
            "estimated_spread_speed_km_day": speed,
            "link_type": current_link_type,
        },
    )

    return {
        "event_id": event_id,
        "disease": event["disease"],
        "series_id": series_id,
        "branch_id": branch_id,
        "probable_parent_event_id": parent_id,
        "chronological_previous_event_id": chronological_previous,
        "link_type": current_link_type,
        "parent_score": parent_score,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    args = parser.parse_args()

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        result = update_single_event(conn, args.event_id)
        conn.commit()
        print(result)


if __name__ == "__main__":
    main()
