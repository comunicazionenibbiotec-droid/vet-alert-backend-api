-- Priority phlebotomine sand fly species for the leishmaniasis pilot.
INSERT INTO vector_species_catalog
(id, scientific_name, common_group, pathogen_focus, is_leishmaniasis_vector, vector_status, priority, notes, source, source_url)
VALUES
('phlebotomus_perniciosus', 'Phlebotomus perniciosus', 'sand_fly', 'Leishmania infantum', TRUE, 'known_or_primary_vector', 1, 'High priority for Italy and pilot leishmaniasis surveillance.', 'ECDC VectorNet / literature', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps'),
('phlebotomus_perfiliewi', 'Phlebotomus perfiliewi', 'sand_fly', 'Leishmania infantum', TRUE, 'known_or_suspected_vector', 2, 'Priority sand fly species included in ECDC maps.', 'ECDC VectorNet', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps'),
('phlebotomus_neglectus', 'Phlebotomus neglectus', 'sand_fly', 'Leishmania infantum', TRUE, 'known_or_suspected_vector', 3, 'Priority sand fly species included in ECDC maps and northern Italy literature.', 'ECDC VectorNet / literature', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps'),
('phlebotomus_ariasi', 'Phlebotomus ariasi', 'sand_fly', 'Leishmania infantum', TRUE, 'known_or_suspected_vector', 4, 'Priority sand fly species included in ECDC maps.', 'ECDC VectorNet', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps'),
('phlebotomus_mascitii', 'Phlebotomus mascitii', 'sand_fly', 'Leishmania infantum', TRUE, 'possible_vector_or_presence_indicator', 5, 'Included in ECDC phlebotomine maps; use as context layer until veterinary validation.', 'ECDC VectorNet', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps'),
('phlebotomus_papatasi', 'Phlebotomus papatasi', 'sand_fly', 'Leishmania spp. / phleboviruses', TRUE, 'vector_relevance_mediterranean', 6, 'Included in ECDC maps; relevant for Mediterranean vector surveillance context.', 'ECDC VectorNet', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps'),
('phlebotomus_sergenti', 'Phlebotomus sergenti', 'sand_fly', 'Leishmania tropica', TRUE, 'vector_relevance_mediterranean', 7, 'Included in ECDC maps; monitor for broader leishmaniasis context.', 'ECDC VectorNet', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps'),
('phlebotomus_tobbi', 'Phlebotomus tobbi', 'sand_fly', 'Leishmania infantum', TRUE, 'vector_relevance_mediterranean', 8, 'Included in ECDC maps; monitor for wider Mediterranean context.', 'ECDC VectorNet', 'https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/phlebotomine-maps')
ON CONFLICT (id) DO UPDATE SET
  scientific_name=EXCLUDED.scientific_name,
  common_group=EXCLUDED.common_group,
  pathogen_focus=EXCLUDED.pathogen_focus,
  is_leishmaniasis_vector=EXCLUDED.is_leishmaniasis_vector,
  vector_status=EXCLUDED.vector_status,
  priority=EXCLUDED.priority,
  notes=EXCLUDED.notes,
  source=EXCLUDED.source,
  source_url=EXCLUDED.source_url,
  updated_at=NOW();
