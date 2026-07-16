#!/usr/bin/env python3
from __future__ import annotations
import csv, json
from pathlib import Path
from datetime import date

OUT = Path("data/territorial_layers/vectornet_gbif_layers.csv")
META = Path("data/territorial_layers/invasive_mosquito_layers_metadata.json")
HEADERS = ["external_id","category","source","label","scientific_name","data_type","count","period_start","period_end","country","region","province","location","lat","lon","radius_km","color","url_source","notes"]

FALLBACK_CITIES = {
    "Torino": ("Piemonte", "Torino", 45.0703, 7.6869),
    "Cuneo": ("Piemonte", "Cuneo", 44.3845, 7.5427),
    "Milano": ("Lombardia", "Milano", 45.4642, 9.1900),
    "Pavia": ("Lombardia", "Pavia", 45.1847, 9.1582),
    "Brescia": ("Lombardia", "Brescia", 45.5416, 10.2118),
    "Genova": ("Liguria", "Genova", 44.4048, 8.9444),
    "Verona": ("Veneto", "Verona", 45.4384, 10.9916),
    "Padova": ("Veneto", "Padova", 45.4064, 11.8768),
    "Bologna": ("Emilia-Romagna", "Bologna", 44.4949, 11.3426),
    "Parma": ("Emilia-Romagna", "Parma", 44.8015, 10.3279),
    "Firenze": ("Toscana", "Firenze", 43.7696, 11.2558),
    "Grosseto": ("Toscana", "Grosseto", 42.7635, 11.1124),
    "Roma": ("Lazio", "Roma", 41.9028, 12.4964),
    "Napoli": ("Campania", "Napoli", 40.8518, 14.2681),
    "Caserta": ("Campania", "Caserta", 41.0747, 14.3324),
    "Bari": ("Puglia", "Bari", 41.1171, 16.8719),
    "Palermo": ("Sicilia", "Palermo", 38.1157, 13.3615),
    "Cagliari": ("Sardegna", "Cagliari", 39.2238, 9.1217),
}

ALBOPICTUS = list(FALLBACK_CITIES.keys())
JAPONICUS = ["Torino","Cuneo","Verona","Padova","Brescia","Milano","Pavia"]
KOREICUS = ["Torino","Cuneo","Milano","Brescia","Genova","Verona","Padova","Pavia","Bologna"]
VECTOR_SPECS = [
    ("Aedes albopictus", "Aedes albopictus", ALBOPICTUS),
    ("Aedes japonicus", "Aedes japonicus", JAPONICUS),
    ("Aedes koreicus", "Aedes koreicus", KOREICUS),
]

def slug(s: str) -> str:
    return "-".join(str(s).upper().replace(".", "").replace("/", " ").split())

def build_rows():
    rows = []
    today = date.today().isoformat()
    for label, sci, city_names in VECTOR_SPECS:
        for city in city_names:
            if city not in FALLBACK_CITIES:
                continue
            region, province, lat, lon = FALLBACK_CITIES[city]
            rows.append({
                "external_id": f"VECTORNET-IT-2026-{slug(sci)}-{slug(city)}",
                "category": "vectors",
                "source": "VECTORNET_CURATED",
                "label": label,
                "scientific_name": sci,
                "data_type": "established_distribution_area",
                "count": "1",
                "period_start": "2026-01-01",
                "period_end": today,
                "country": "Italy",
                "region": region,
                "province": province,
                "location": city,
                "lat": f"{lat:.4f}",
                "lon": f"{lon:.4f}",
                "radius_km": "35",
                "color": "#7C3AED",
                "url_source": "https://www.ecdc.europa.eu/en/disease-vectors/surveillance-and-disease-data/mosquito-maps",
                "notes": "Curated territorial vector layer based on documented established distribution area. Count=1 indicates presence/distribution area, not a single observation. This is contextual vector information, not a disease diagnosis or outbreak.",
            })
    return rows

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    META.write_text(json.dumps({
        "version": "v148-curated-invasive-mosquito-layers",
        "generated_rows": len(rows),
        "categories": {"vectors": len(rows)},
        "sources": ["VECTORNET_CURATED"],
        "interpretation": "count=1 means established or documented distribution area, not a single observation",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print({"status": "success", "rows": len(rows), "output": str(OUT)})

if __name__ == "__main__":
    main()
