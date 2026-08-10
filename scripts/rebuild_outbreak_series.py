import os
import math
import re
from collections import defaultdict
from datetime import date

import psycopg
from psycopg.rows import dict_row


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")


SOURCE_FILTER = "BENV / IZS"

DEFAULT_MAX_DISTANCE_KM = 100.0
DEFAULT_MAX_DAYS = 90


def slugify(value):
    value = str(value).lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-")


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


def load_configs(conn):
    rows = conn.execute(
        """
        SELECT disease,
               max_parent_distance_km,
               max_parent_time_gap_days
        FROM disease_branching_config
        """
    ).fetchall()

    configs = {}

    for row in rows:
        configs[row["disease"]] = {
            "max_distance": float(row["max_parent_distance_km"]),
            "max_days": int(row["max_parent_time_gap_days"]),
        }

    return configs


def load_events(conn):
    rows = conn.execute(
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
        WHERE source = %s
          AND observation_date IS NOT NULL
          AND lat IS NOT NULL
          AND lon IS NOT NULL
        ORDER BY disease, observation_date, id
        """,
        (SOURCE_FILTER,),
    ).fetchall()

    grouped = defaultdict(list)

    for row in rows:
        grouped[row["disease"]].append(dict(row))

    return grouped


def reset_tables(conn):
    conn.execute("DELETE FROM event_parent_links")
    conn.execute("DELETE FROM event_branch_assignments")
    conn.execute("DELETE FROM outbreak_rebuild_audit")
    conn.execute("DELETE FROM outbreak_branches")
    conn.execute("DELETE FROM outbreak_series")


def insert_series(conn, item):
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
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s, %s, %s, now(), now())
        """,
        (
            item["id"],
            item["disease"],
            item["series_code"],
            item["root_event_id"],
            item["root_date"],
            item["root_location"],
            item["root_region"],
            item["first_event_date"],
            item["last_event_date"],
            item["event_count"],
        ),
    )


def insert_branch(conn, item):
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
        VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, %s, 0.70, now(), now())
        """,
        (
            item["id"],
            item["series_id"],
            item["branch_code"],
            item["branch_name"],
            item["root_event_id"],
            item["direction_label"],
            item["first_event_date"],
            item["last_event_date"],
            item["event_count"],
        ),
    )


def insert_assignment(conn, event_id, series_id, branch_id):
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
        VALUES (%s, %s, %s, 0.70, 'full_rebuild_directional_v1', now(), now())
        """,
        (
            event_id,
            series_id,
            branch_id,
        ),
    )


def insert_parent_link(conn, item):
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
        """,
        (
            item["event_id"],
            item["series_id"],
            item["probable_parent_event_id"],
            item["chronological_previous_event_id"],
            item["parent_score"],
            item["distance_from_parent_km"],
            item["days_from_parent"],
            item["estimated_spread_speed_km_day"],
            item["link_type"],
        ),
    )


def score_parent(candidate, event, config):
    max_distance = config["max_distance"]
    max_days = config["max_days"]

    delta_days = days_between(candidate["observation_date"], event["observation_date"])

    if delta_days is None:
        return None

    if delta_days < 0 or delta_days > max_days:
        return None

    distance = haversine_km(candidate["lat"], candidate["lon"], event["lat"], event["lon"])

    if distance > max_distance:
        return None

    spatial_score = 1.0 - distance / max_distance
    temporal_score = 1.0 - delta_days / max_days

    score = 0.55 * spatial_score
    score += 0.45 * temporal_score

    return {
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


def rebuild_disease(conn, disease, events, config):
    disease_slug = slugify(disease)
    max_distance = config["max_distance"]
    max_days = config["max_days"]

    event_to_series = {}
    series_events = defaultdict(list)
    series_counter = 0

    for index, event in enumerate(events):
        best_series = None
        best_score = -1

        for previous in events[:index]:
            if previous["id"] not in event_to_series:
                continue

            delta_days = days_between(previous["observation_date"], event["observation_date"])

            if delta_days is None or delta_days > max_days:
                continue

            distance = haversine_km(previous["lat"], previous["lon"], event["lat"], event["lon"])

            if distance > max_distance:
                continue

            score = 0.60 * (1.0 - distance / max_distance)
            score += 0.40 * (1.0 - delta_days / max_days)

            if score > best_score:
                best_score = score
                best_series = event_to_series[previous["id"]]

        if best_series is None:
            series_counter += 1
            best_series = f"series-{disease_slug}-{series_counter:04d}"

        event_to_series[event["id"]] = best_series
        series_events[best_series].append(event)

    total_links = 0

    for series_id, items in series_events.items():
        items = sorted(items, key=lambda x: (x["observation_date"], x["id"]))
        root = items[0]

        series_number = series_id.split("-")[-1]
        series_code = f"{disease_slug.upper()}-2025-2026-S{series_number}"

        branch_id = f"branch-{series_id}-b01"

        insert_series(
            conn,
            {
                "id": series_id,
                "disease": disease,
                "series_code": series_code,
                "root_event_id": root["id"],
                "root_date": root["observation_date"],
                "root_location": root["location"],
                "root_region": root["region"],
                "first_event_date": items[0]["observation_date"],
                "last_event_date": items[-1]["observation_date"],
                "event_count": len(items),
            },
        )

        insert_branch(
            conn,
            {
                "id": branch_id,
                "series_id": series_id,
                "branch_code": "B01",
                "branch_name": "Root area",
                "root_event_id": root["id"],
                "direction_label": "ROOT",
                "first_event_date": items[0]["observation_date"],
                "last_event_date": items[-1]["observation_date"],
                "event_count": len(items),
            },
        )

        for event in items:
            insert_assignment(conn, event["id"], series_id, branch_id)

        for index, event in enumerate(items):
            chronological_previous_event_id = None

            if index > 0:
                chronological_previous_event_id = items[index - 1]["id"]

            best_parent_id = None
            best_score = None
            best_distance = None
            best_days = None

            for candidate in items[:index]:
                scored = score_parent(candidate, event, config)

                if scored is None:
                    continue

                if best_score is None or scored["score"] > best_score:
                    best_score = scored["score"]
                    best_parent_id = candidate["id"]
                    best_distance = scored["distance"]
                    best_days = scored["days"]

            current_link_type = classify_link(best_score)

            speed = None

            if best_distance is not None and best_days is not None and best_days > 0:
                speed = best_distance / best_days

            insert_parent_link(
                conn,
                {
                    "event_id": event["id"],
                    "series_id": series_id,
                    "probable_parent_event_id": best_parent_id if current_link_type != "no_parent" else None,
                    "chronological_previous_event_id": chronological_previous_event_id,
                    "parent_score": best_score,
                    "distance_from_parent_km": best_distance,
                    "days_from_parent": best_days,
                    "estimated_spread_speed_km_day": speed,
                    "link_type": current_link_type,
                },
            )

            total_links += 1

    return {
        "disease": disease,
        "events": len(events),
        "series": len(series_events),
        "links": total_links,
    }


def main():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        configs = load_configs(conn)
        grouped_events = load_events(conn)

        reset_tables(conn)

        results = []

        for disease in sorted(grouped_events.keys()):
            config = configs.get(
                disease,
                {
                    "max_distance": DEFAULT_MAX_DISTANCE_KM,
                    "max_days": DEFAULT_MAX_DAYS,
                },
            )

            result = rebuild_disease(conn, disease, grouped_events[disease], config)
            results.append(result)
            print(result)

        conn.commit()

        print({
            "status": "completed",
            "diseases": len(results),
            "total_events": sum(item["events"] for item in results),
            "total_series": sum(item["series"] for item in results),
            "total_links": sum(item["links"] for item in results),
        })


if __name__ == "__main__":
    main()
