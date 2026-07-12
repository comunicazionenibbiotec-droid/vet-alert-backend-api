WAHIS import for vet.ector

Use data/wahis_import/wahis_events.csv for real normalized WAHIS rows.
If this file is not present, wahis_events_template.csv is used for demo/testing.

Required columns:
external_id,disease,species,animal_group,observation_date,lat,lon

Recommended columns:
source,disease_it,diagnosis_status,report_date,country,region,location,url_source,notes
