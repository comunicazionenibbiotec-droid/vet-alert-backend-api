-- vet.ector database schema v1
-- PostgreSQL + PostGIS recommended
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS data_sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  url TEXT,
  update_frequency TEXT,
  ingestion_mode TEXT,
  enabled BOOLEAN DEFAULT TRUE,
  priority INTEGER DEFAULT 100,
  notes TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS data_import_runs (
  id BIGSERIAL PRIMARY KEY,
  source_id TEXT REFERENCES data_sources(id),
  status TEXT NOT NULL,
  started_at TIMESTAMP DEFAULT NOW(),
  finished_at TIMESTAMP,
  records_fetched INTEGER DEFAULT 0,
  records_inserted INTEGER DEFAULT 0,
  records_updated INTEGER DEFAULT 0,
  error_message TEXT,
  metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS cities (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  region TEXT,
  province TEXT,
  country TEXT DEFAULT 'Italy',
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  geom GEOGRAPHY(Point, 4326),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS cities_name_country_idx ON cities (LOWER(name), country);
CREATE INDEX IF NOT EXISTS cities_geom_idx ON cities USING GIST (geom);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  disease TEXT NOT NULL,
  species TEXT,
  animal_group TEXT,
  diagnosis_status TEXT,
  source TEXT,
  source_type TEXT,
  report_type TEXT,
  observation_date DATE,
  report_date DATE,
  location TEXT,
  region TEXT,
  province TEXT,
  country TEXT DEFAULT 'Italy',
  lat DOUBLE PRECISION,
  lon DOUBLE PRECISION,
  geom GEOGRAPHY(Point, 4326),
  risk_score INTEGER,
  confidence_label TEXT,
  url_source TEXT,
  raw_payload JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS events_geom_idx ON events USING GIST (geom);
CREATE INDEX IF NOT EXISTS events_date_idx ON events (observation_date DESC);
CREATE INDEX IF NOT EXISTS events_source_idx ON events (source);
CREATE INDEX IF NOT EXISTS events_disease_idx ON events (LOWER(disease));

CREATE TABLE IF NOT EXISTS territorial_layers (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL CHECK (category IN ('vectors','parasites','west_nile')),
  label TEXT,
  scientific_name TEXT,
  data_type TEXT,
  count INTEGER,
  count_label TEXT,
  country TEXT DEFAULT 'Italy',
  region TEXT,
  province TEXT,
  location TEXT,
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  geom GEOGRAPHY(Point, 4326),
  radius_km DOUBLE PRECISION DEFAULT 10,
  aggregation_level TEXT,
  source TEXT,
  display_source TEXT,
  period_start DATE,
  period_end DATE,
  url_source TEXT,
  notes TEXT,
  raw_payload JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS territorial_layers_geom_idx ON territorial_layers USING GIST (geom);
CREATE INDEX IF NOT EXISTS territorial_layers_category_idx ON territorial_layers (category);
CREATE INDEX IF NOT EXISTS territorial_layers_source_idx ON territorial_layers (source);
CREATE INDEX IF NOT EXISTS territorial_layers_period_idx ON territorial_layers (period_start DESC, period_end DESC);

CREATE OR REPLACE FUNCTION set_geom_from_lat_lon() RETURNS trigger AS $$
BEGIN
  IF NEW.lat IS NOT NULL AND NEW.lon IS NOT NULL THEN
    NEW.geom = ST_SetSRID(ST_MakePoint(NEW.lon, NEW.lat), 4326)::geography;
  END IF;
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS cities_geom_trigger ON cities;
CREATE TRIGGER cities_geom_trigger BEFORE INSERT OR UPDATE ON cities
FOR EACH ROW EXECUTE FUNCTION set_geom_from_lat_lon();

DROP TRIGGER IF EXISTS events_geom_trigger ON events;
CREATE TRIGGER events_geom_trigger BEFORE INSERT OR UPDATE ON events
FOR EACH ROW EXECUTE FUNCTION set_geom_from_lat_lon();

DROP TRIGGER IF EXISTS territorial_layers_geom_trigger ON territorial_layers;
CREATE TRIGGER territorial_layers_geom_trigger BEFORE INSERT OR UPDATE ON territorial_layers
FOR EACH ROW EXECUTE FUNCTION set_geom_from_lat_lon();
