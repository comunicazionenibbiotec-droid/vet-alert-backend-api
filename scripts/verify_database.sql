-- vet.ector database verification
SELECT 'data_sources' AS table_name, COUNT(*) FROM data_sources
UNION ALL SELECT 'cities', COUNT(*) FROM cities
UNION ALL SELECT 'events', COUNT(*) FROM events
UNION ALL SELECT 'territorial_layers', COUNT(*) FROM territorial_layers
UNION ALL SELECT 'data_import_runs', COUNT(*) FROM data_import_runs;

SELECT category, source, COUNT(*) AS n
FROM territorial_layers
GROUP BY category, source
ORDER BY category, source;

SELECT source, COUNT(*) AS n
FROM events
GROUP BY source
ORDER BY source;
