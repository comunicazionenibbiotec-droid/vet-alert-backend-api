-- vet.ector v5 - vector, parasite and West Nile surveillance database extension
-- Requires the v1 schema: data_sources, data_import_runs, territorial_layers.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS vector_species_catalog (
  id TEXT PRIMARY KEY,
  scientific_name TEXT NOT NULL,
  common_group TEXT NOT NULL,
  pathogen_focus TEXT,
  is_leishmaniasis_vector BOOLEAN DEFAULT FALSE,
  vector_status TEXT,
  priority INTEGER DEFAULT 100,
  notes TEXT,
  source TEXT,
  source_url TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vector_occurrences (
  id TEXT PRIMARY KEY,
  scientific_name TEXT NOT NULL,
  common_group TEXT,
  pathogen_focus TEXT,
  occurrence_status TEXT,
  event_date DATE,
  year INTEGER,
  country TEXT DEFAULT 'Italy',
  region TEXT,
  province TEXT,
  municipality TEXT,
  locality TEXT,
  lat DOUBLE PRECISION,
  lon DOUBLE PRECISION,
  geom GEOGRAPHY(Point, 4326),
  coordinate_uncertainty_m DOUBLE PRECISION,
  source TEXT NOT NULL,
  source_dataset TEXT,
  source_url TEXT,
  license TEXT,
  confidence_score INTEGER DEFAULT 70,
  raw_payload JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS vector_occurrences_geom_idx ON vector_occurrences USING GIST (geom);
CREATE INDEX IF NOT EXISTS vector_occurrences_species_idx ON vector_occurrences (LOWER(scientific_name));
CREATE INDEX IF NOT EXISTS vector_occurrences_focus_idx ON vector_occurrences (pathogen_focus);
CREATE INDEX IF NOT EXISTS vector_occurrences_date_idx ON vector_occurrences (event_date DESC NULLS LAST, year DESC NULLS LAST);

CREATE TABLE IF NOT EXISTS vector_import_watermarks (
  source_id TEXT PRIMARY KEY,
  last_success_at TIMESTAMP,
  last_event_date DATE,
  last_year INTEGER,
  cursor_token TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS surveillance_admin_centroids (
  id TEXT PRIMARY KEY,
  country TEXT DEFAULT 'Italy',
  region TEXT,
  province TEXT,
  municipality TEXT,
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  geom GEOGRAPHY(Point, 4326),
  source TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS surveillance_admin_centroids_geom_idx ON surveillance_admin_centroids USING GIST (geom);
CREATE INDEX IF NOT EXISTS surveillance_admin_centroids_province_idx ON surveillance_admin_centroids (LOWER(province));

CREATE OR REPLACE FUNCTION set_geom_from_lat_lon_v5() RETURNS trigger AS $$
BEGIN
  IF NEW.lat IS NOT NULL AND NEW.lon IS NOT NULL THEN
    NEW.geom = ST_SetSRID(ST_MakePoint(NEW.lon, NEW.lat), 4326)::geography;
  END IF;
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS vector_occurrences_geom_trigger ON vector_occurrences;
CREATE TRIGGER vector_occurrences_geom_trigger BEFORE INSERT OR UPDATE ON vector_occurrences
FOR EACH ROW EXECUTE FUNCTION set_geom_from_lat_lon_v5();

DROP TRIGGER IF EXISTS surveillance_admin_centroids_geom_trigger ON surveillance_admin_centroids;
CREATE TRIGGER surveillance_admin_centroids_geom_trigger BEFORE INSERT OR UPDATE ON surveillance_admin_centroids
FOR EACH ROW EXECUTE FUNCTION set_geom_from_lat_lon_v5();

-- Register/refresh data sources used by v5.
INSERT INTO data_sources (id, name, source_type, url, update_frequency, ingestion_mode, priority, notes)
VALUES
('vectornet_gbif', 'VectorNet / GBIF occurrences', 'vector_occurrence', 'https://www.vectornetdata.org/', 'weekly', 'gbif_occurrence_api', 5, 'Validated vector occurrence data; priority source for phlebotomine sand flies and leishmaniasis vector context.'),
('ecdc_vector_maps', 'ECDC VectorNet vector maps', 'vector_distribution_maps', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps', 'manual_or_quarterly', 'map_status_review', 6, 'Phlebotomine, mosquito, tick and midge distribution maps at regional administrative unit level.'),
('iss_cesme_wnv', 'ISS / CESME / IZS West Nile', 'west_nile_surveillance', 'https://www.epicentro.iss.it/westNile/bollettino', 'weekly_during_season', 'pdf_or_html_review', 10, 'Italian integrated WNV/USUV surveillance, including human, veterinary and entomological surveillance.'),
('ecdc_efsa_wnv', 'ECDC / EFSA West Nile monthly', 'west_nile_surveillance', 'https://www.ecdc.europa.eu/en/infectious-disease-topics/west-nile-virus-infection/surveillance-and-updates-west-nile-virus', 'monthly_during_season', 'report_review', 12, 'European monthly reports on humans and animals.'),
('cns_wnv', 'Centro Nazionale Sangue WNV', 'west_nile_prevention', 'https://www.centronazionalesangue.it/west-nile-virus-2025/', 'daily_during_season', 'html_scrape_with_review', 15, 'WNV blood donation prevention measures by province/area.')
ON CONFLICT (id) DO UPDATE SET
  name=EXCLUDED.name,
  source_type=EXCLUDED.source_type,
  url=EXCLUDED.url,
  update_frequency=EXCLUDED.update_frequency,
  ingestion_mode=EXCLUDED.ingestion_mode,
  priority=EXCLUDED.priority,
  notes=EXCLUDED.notes,
  updated_at=NOW();
