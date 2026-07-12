ADIS CSV import for vet.ector

Use adis_events.csv for real/exported data. If adis_events.csv is absent, the backend falls back to adis_events_template.csv.

Expected columns:
external_id,source,disease,disease_it,diagnosis_status,species,animal_group,observation_date,report_date,country,region,location,lat,lon,url_source,notes

Recommended values:
source = ADIS
source_type = official (set by connector)
report_type = official_confirmed (set by connector)
