import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL")

@contextmanager
def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def start_run(conn, source_id, metadata=None):
    row = conn.execute(
        """
        INSERT INTO data_import_runs (source_id, status, metadata)
        VALUES (%s, 'running', %s)
        RETURNING id
        """,
        (source_id, json.dumps(metadata or {})),
    ).fetchone()
    conn.commit()
    return row["id"]


def finish_run(conn, run_id, status, fetched=0, inserted=0, updated=0, error=None):
    conn.execute(
        """
        UPDATE data_import_runs
        SET status=%s, finished_at=NOW(), records_fetched=%s,
            records_inserted=%s, records_updated=%s, error_message=%s
        WHERE id=%s
        """,
        (status, fetched, inserted, updated, error, run_id),
    )
    conn.commit()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def stable_id(*parts):
    text = "|".join(str(p or "").strip().lower() for p in parts)
    import hashlib
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:24]


def upsert_territorial_layer(conn, layer):
    conn.execute(
        """
        INSERT INTO territorial_layers (
          id, category, label, scientific_name, data_type, count, count_label,
          country, region, province, location, lat, lon, radius_km,
          aggregation_level, source, display_source, period_start, period_end,
          url_source, notes, raw_payload
        ) VALUES (
          %(id)s, %(category)s, %(label)s, %(scientific_name)s, %(data_type)s,
          %(count)s, %(count_label)s, %(country)s, %(region)s, %(province)s,
          %(location)s, %(lat)s, %(lon)s, %(radius_km)s, %(aggregation_level)s,
          %(source)s, %(display_source)s, %(period_start)s, %(period_end)s,
          %(url_source)s, %(notes)s, %(raw_payload)s
        )
        ON CONFLICT (id) DO UPDATE SET
          category=EXCLUDED.category,
          label=EXCLUDED.label,
          scientific_name=EXCLUDED.scientific_name,
          data_type=EXCLUDED.data_type,
          count=EXCLUDED.count,
          count_label=EXCLUDED.count_label,
          country=EXCLUDED.country,
          region=EXCLUDED.region,
          province=EXCLUDED.province,
          location=EXCLUDED.location,
          lat=EXCLUDED.lat,
          lon=EXCLUDED.lon,
          radius_km=EXCLUDED.radius_km,
          aggregation_level=EXCLUDED.aggregation_level,
          source=EXCLUDED.source,
          display_source=EXCLUDED.display_source,
          period_start=EXCLUDED.period_start,
          period_end=EXCLUDED.period_end,
          url_source=EXCLUDED.url_source,
          notes=EXCLUDED.notes,
          raw_payload=EXCLUDED.raw_payload,
          updated_at=NOW()
        """,
        layer,
    )


def upsert_event(conn, event):
    conn.execute(
        """
        INSERT INTO events (
          id, disease, species, animal_group, diagnosis_status, source, source_type,
          report_type, observation_date, report_date, location, region, province,
          country, lat, lon, risk_score, confidence_label, url_source, raw_payload
        ) VALUES (
          %(id)s, %(disease)s, %(species)s, %(animal_group)s,
          %(diagnosis_status)s, %(source)s, %(source_type)s, %(report_type)s,
          %(observation_date)s, %(report_date)s, %(location)s, %(region)s,
          %(province)s, %(country)s, %(lat)s, %(lon)s, %(risk_score)s,
          %(confidence_label)s, %(url_source)s, %(raw_payload)s
        )
        ON CONFLICT (id) DO UPDATE SET
          disease=EXCLUDED.disease,
          species=EXCLUDED.species,
          animal_group=EXCLUDED.animal_group,
          diagnosis_status=EXCLUDED.diagnosis_status,
          source=EXCLUDED.source,
          source_type=EXCLUDED.source_type,
          report_type=EXCLUDED.report_type,
          observation_date=EXCLUDED.observation_date,
          report_date=EXCLUDED.report_date,
          location=EXCLUDED.location,
          region=EXCLUDED.region,
          province=EXCLUDED.province,
          country=EXCLUDED.country,
          lat=EXCLUDED.lat,
          lon=EXCLUDED.lon,
          risk_score=EXCLUDED.risk_score,
          confidence_label=EXCLUDED.confidence_label,
          url_source=EXCLUDED.url_source,
          raw_payload=EXCLUDED.raw_payload,
          updated_at=NOW()
        """,
        event,
    )
