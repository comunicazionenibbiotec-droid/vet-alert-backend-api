# V92 main.py patch instructions

Add BDN density and EFSA risk layer endpoints to `backend/main.py`.

## 1. Add imports near other sync imports

```python
from sync.bdn_connector import BdnDensityConnector, normalize_density_row
from sync.efsa_risk_connector import EfsaRiskLayerConnector, normalize_risk_layer
from sync.risk_summary import summarize_area_risk
```

## 2. Add helper functions after `load_json` or near risk endpoints

```python
def get_bdn_density_items():
    connector = BdnDensityConnector()
    return [normalize_density_row(r) for r in connector.fetch()]

def get_efsa_risk_layers():
    connector = EfsaRiskLayerConnector()
    return [normalize_risk_layer(r) for r in connector.fetch()]
```

## 3. Replace or improve `/risk/livestock-density`

If you already have `/risk/livestock-density`, replace its body with this:

```python
@app.get("/risk/livestock-density")
def get_livestock_density(country: str = Query("Italy"), species: str = Query("all"), region: str | None = Query(None), province: str | None = Query(None)):
    data = get_bdn_density_items()
    country_l = country.lower().strip()
    species_l = species.lower().strip()
    region_l = region.lower().strip() if region else ""
    province_l = province.lower().strip() if province else ""
    out = []
    for row in data:
        if country_l and str(row.get("country", "")).lower() != country_l:
            continue
        if species_l and species_l != "all" and species_l not in str(row.get("species", "")).lower():
            continue
        if region_l and region_l not in str(row.get("region", "")).lower():
            continue
        if province_l and province_l not in str(row.get("province", "")).lower():
            continue
        out.append(row)
    return {"count": len(out), "items": out}
```

## 4. Add EFSA risk layer endpoint

```python
@app.get("/risk/efsa-layers")
def get_efsa_layers(species: str = Query("all"), disease: str | None = Query(None)):
    data = get_efsa_risk_layers()
    species_l = species.lower().strip()
    disease_l = disease.lower().strip() if disease else ""
    out = []
    for row in data:
        if disease_l and disease_l not in f"{row.get('disease','')} {row.get('disease_key','')}".lower():
            continue
        if species_l and species_l != "all":
            if not any(species_l in str(s).lower() for s in row.get("species", [])):
                continue
        out.append(row)
    return {"count": len(out), "items": out}
```

## 5. Add area summary endpoint

```python
@app.get("/risk/area-summary")
def get_area_summary(lat: float = Query(...), lon: float = Query(...), radius_km: float = Query(50, ge=1, le=2000), days: int = Query(180, ge=1, le=3650), animal_filter: str = Query("all")):
    # Reuse the same logic as /events, but without returning veterinarians.
    events_response = get_events(lat=lat, lon=lon, radius_km=radius_km, days=days, animal_filter=animal_filter)
    events = events_response.get("events", [])
    density = get_bdn_density_items()
    layers = get_efsa_risk_layers()
    return summarize_area_risk(events, density, layers, species=animal_filter)
```

## 6. Optional source registry endpoint

```python
@app.get("/sources/registry")
def get_sources_registry():
    return {
        "event_sources": [
            {"key": "WAHIS", "type": "official", "role": "global official animal disease events"},
            {"key": "ADIS", "type": "official", "role": "EU official animal disease events"},
            {"key": "user_report", "type": "user", "role": "suspect reports from platform users"},
            {"key": "rapid_test", "type": "user", "role": "rapid test positive reports"},
            {"key": "veterinarian", "type": "professional", "role": "veterinarian validated reports"},
            {"key": "Demo 365 giorni", "type": "demo", "role": "temporary prototype data"}
        ],
        "context_sources": [
            {"key": "BDN", "type": "risk_context", "role": "Italian livestock density/exposure context"},
            {"key": "EFSA", "type": "risk_context", "role": "risk/trend/scientific context, not point events"}
        ]
    }
```
