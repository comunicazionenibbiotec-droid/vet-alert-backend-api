# vet.ector v5 - backend vector/parasitology/West Nile surveillance

## Objective

Create a database layer for territorial signals related to:

- vectors, especially leishmaniasis-relevant phlebotomine sand flies;
- parasites;
- West Nile / Usutu surveillance and prevention measures.

## Priority for pilot

The pilot should prioritise phlebotomine sand flies with leishmaniasis relevance, especially `Phlebotomus perniciosus`, and then `P. perfiliewi`, `P. neglectus`, `P. ariasi`, `P. mascitii`, `P. papatasi`, `P. sergenti`, and `P. tobbi`.

## Sources

1. VectorNet / ECDC / EFSA / GBIF for validated vector occurrence and distribution context.
2. ECDC phlebotomine maps for regional distribution states.
3. ISS / CESME / IZS and ECDC/EFSA for West Nile surveillance.
4. CNS for WNV blood-donation prevention areas.
5. BENV / IZS for official veterinary events when a stable export is available.

## Deployment

```bash
psql "$DATABASE_URL" -f db/migration_005_vector_surveillance.sql
psql "$DATABASE_URL" -f db/seed_leishmaniasis_vectors.sql
pip install -r importers/requirements.txt
python importers/import_vectornet_gbif.py
psql "$DATABASE_URL" -f importers/rebuild_vector_layers_from_occurrences.sql
python importers/import_cns_wnv_v5.py
```

## Notes

- Occurrence data are context and surveillance data, not clinical diagnoses.
- ECDC VectorNet maps are validated by experts but do not represent official country positions.
- WNV layers should distinguish prevention measures, human affected areas, animal outbreaks, and entomological detection where data are available.
