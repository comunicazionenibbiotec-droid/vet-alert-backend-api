-- Optional aggregation: rebuild province-level layers from vector_occurrences.
-- This gives a less noisy display than one circle per occurrence.
INSERT INTO territorial_layers (
  id, category, label, scientific_name, data_type, count, count_label,
  country, region, province, location, lat, lon, radius_km, aggregation_level,
  source, display_source, period_start, period_end, url_source, notes, raw_payload
)
SELECT
  'agg-vector-' || md5(lower(scientific_name) || '|' || coalesce(region,'') || '|' || coalesce(province,'')) AS id,
  'vectors' AS category,
  scientific_name AS label,
  scientific_name,
  CASE WHEN pathogen_focus ILIKE '%leish%' THEN 'Aggregated vector occurrence / leishmaniasis vector' ELSE 'Aggregated vector occurrence' END AS data_type,
  COUNT(*)::int AS count,
  'occurrence records' AS count_label,
  COALESCE(country, 'Italy') AS country,
  region,
  province,
  COALESCE(province, region, 'Italy') AS location,
  AVG(lat)::float AS lat,
  AVG(lon)::float AS lon,
  CASE WHEN COUNT(*) >= 20 THEN 25 WHEN COUNT(*) >= 5 THEN 15 ELSE 8 END AS radius_km,
  'province_or_region' AS aggregation_level,
  'VectorNet / GBIF' AS source,
  'VectorNet / GBIF aggregated' AS display_source,
  MIN(event_date) AS period_start,
  MAX(event_date) AS period_end,
  'https://www.vectornetdata.org/' AS url_source,
  CASE WHEN bool_or(pathogen_focus ILIKE '%leish%') THEN 'High-priority leishmaniasis pilot vector layer. Occurrences are context data, not disease diagnoses.' ELSE 'Aggregated vector occurrence layer; not a disease diagnosis.' END AS notes,
  jsonb_build_object('source_table','vector_occurrences','record_count',COUNT(*)) AS raw_payload
FROM vector_occurrences
WHERE lat IS NOT NULL AND lon IS NOT NULL
GROUP BY scientific_name, pathogen_focus, country, region, province
ON CONFLICT (id) DO UPDATE SET
  count=EXCLUDED.count,
  lat=EXCLUDED.lat,
  lon=EXCLUDED.lon,
  radius_km=EXCLUDED.radius_km,
  period_start=EXCLUDED.period_start,
  period_end=EXCLUDED.period_end,
  notes=EXCLUDED.notes,
  raw_payload=EXCLUDED.raw_payload,
  updated_at=NOW();
