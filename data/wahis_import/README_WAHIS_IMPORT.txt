Carica qui il file CSV esportato/normalizzato da WAHIS.

Nome file atteso dal backend:
wahis_events.csv

Se il file wahis_events.csv non esiste, il backend usa wahis_events_template.csv come esempio.

Colonne supportate:
external_id, source, disease, disease_it, diagnosis_status, species, animal_group,
observation_date, report_date, country, region, location, lat, lon, url_source, notes

Nota: per uso reale, l'export WAHIS deve essere ottenuto nel rispetto dei termini d'uso della fonte.
