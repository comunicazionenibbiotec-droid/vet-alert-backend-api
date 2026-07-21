import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv('DATABASE_URL')

@contextmanager
def db():
    if not DATABASE_URL:
        raise RuntimeError('DATABASE_URL is not set')
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn

def stable_id(*parts):
    text = '|'.join(str(p or '').strip().lower() for p in parts)
    return hashlib.sha1(text.encode('utf-8')).hexdigest()[:32]

def start_run(conn, source_id, metadata=None):
    row = conn.execute(
        """INSERT INTO data_import_runs (source_id, status, metadata)
           VALUES (%s, 'running', %s) RETURNING id""",
        (source_id, json.dumps(metadata or {})),
    ).fetchone()
    conn.commit()
    return row['id']

def finish_run(conn, run_id, status, fetched=0, inserted=0, updated=0, error=None):
    conn.execute(
        """UPDATE data_import_runs SET status=%s, finished_at=NOW(),
           records_fetched=%s, records_inserted=%s, records_updated=%s, error_message=%s
           WHERE id=%s""",
        (status, fetched, inserted, updated, error, run_id),
    )
    conn.commit()

def upsert_occurrence(conn, rec):
    conn.execute(
        """
        INSERT INTO vector_occurrences (
          id, scientific_name, common_group, pathogen_focus, occurrence_status,
          event_date, year, country, region, province, municipality, locality,
          lat, lon, coordinate_uncertainty_m, source, source_dataset, source_url,
          license, confidence_score, raw_payload
        ) VALUES (
          %(id)s, %(scientific_name)s, %(common_group)s, %(pathogen_focus)s,
          %(occurrence_status)s, %(event_date)s, %(year)s, %(country)s,
          %(region)s, %(province)s, %(municipality)s, %(locality)s,
          %(lat)s, %(lon)s, %(coordinate_uncertainty_m)s, %(source)s,
          %(source_dataset)s, %(source_url)s, %(license)s, %(confidence_score)s,
          %(raw_payload)s
        )
        ON CONFLICT (id) DO UPDATE SET
          scientific_name=EXCLUDED.scientific_name,
          common_group=EXCLUDED.common_group,
          pathogen_focus=EXCLUDED.pathogen_focus,
          occurrence_status=EXCLUDED.occurrence_status,
          event_date=EXCLUDED.event_date,
          year=EXCLUDED.year,
          country=EXCLUDED.country,
          region=EXCLUDED.region,
          province=EXCLUDED.province,
          municipality=EXCLUDED.municipality,
          locality=EXCLUDED.locality,
          lat=EXCLUDED.lat,
          lon=EXCLUDED.lon,
          coordinate_uncertainty_m=EXCLUDED.coordinate_uncertainty_m,
          source=EXCLUDED.source,
          source_dataset=EXCLUDED.source_dataset,
          source_url=EXCLUDED.source_url,
          license=EXCLUDED.license,
          confidence_score=EXCLUDED.confidence_score,
          raw_payload=EXCLUDED.raw_payload,
          updated_at=NOW()
        """,
        rec,
    )

def upsert_layer(conn, layer):
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
