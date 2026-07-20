# API contract for vet.ector map

## GET /territorial-layers

Query parameters:

```txt
lat=45.0703
lon=7.6869
radius_km=50
category=all|vectors|parasites|west_nile
```

Response:

```json
{
  "layers": [
    {
      "id": "cns-wnv-example",
      "category": "west_nile",
      "label": "West Nile",
      "data_type": "cns_wnv_prevention_measure",
      "count": 1,
      "lat": 45.0703,
      "lon": 7.6869,
      "radius_km": 50,
      "source": "CNS WNV",
      "province": "Torino",
      "region": "Piemonte",
      "aggregation_level": "province"
    }
  ]
}
```

SQL example:

```sql
SELECT *
FROM territorial_layers
WHERE ST_DWithin(
  geom,
  ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
  (:radius_km * 1000)
)
AND (:category = 'all' OR category = :category);
```

## GET /events

Query parameters:

```txt
lat=45.0703
lon=7.6869
radius_km=50
days=180
animal_filter=all
```

Response:

```json
{
  "events": []
}
```
