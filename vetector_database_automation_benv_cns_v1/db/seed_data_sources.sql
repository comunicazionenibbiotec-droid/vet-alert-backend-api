INSERT INTO data_sources (id, name, source_type, url, update_frequency, ingestion_mode, priority, notes)
VALUES
('benv_izs', 'BENV / IZS', 'official_veterinary', 'https://www.izs.it/BENV_NEW/datiemappe.html', 'daily_or_weekly', 'csv_or_html_import', 10, 'Bollettino Epidemiologico Nazionale Veterinario: focolai e dati veterinari territoriali italiani'),
('cns_wnv', 'CNS WNV', 'west_nile_prevention', 'https://www.centronazionalesangue.it/west-nile-virus-2025/', 'daily_during_vector_season', 'html_scrape_with_manual_review', 15, 'Centro Nazionale Sangue: misure di prevenzione WNV per province/aree interessate')
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  source_type = EXCLUDED.source_type,
  url = EXCLUDED.url,
  update_frequency = EXCLUDED.update_frequency,
  ingestion_mode = EXCLUDED.ingestion_mode,
  priority = EXCLUDED.priority,
  notes = EXCLUDED.notes,
  updated_at = NOW();
