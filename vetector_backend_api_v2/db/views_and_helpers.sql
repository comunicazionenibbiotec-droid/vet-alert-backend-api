-- Optional helper view for front-end-compatible territorial layers.
CREATE OR REPLACE VIEW api_territorial_layers AS
SELECT
  id,
  category,
  label,
  scientific_name,
  data_type,
  count,
  count_label,
  country,
  region,
  province,
  location,
  lat,
  lon,
  radius_km,
  aggregation_level,
  source,
  COALESCE(display_source, source) AS display_source,
  period_start,
  period_end,
  url_source,
  notes
FROM territorial_layers;

CREATE OR REPLACE VIEW api_events AS
SELECT
  id,
  disease,
  species,
  animal_group,
  diagnosis_status,
  source,
  source_type,
  report_type,
  observation_date,
  report_date,
  location,
  region,
  province,
  country,
  lat,
  lon,
  risk_score,
  confidence_label,
  url_source
FROM events;
