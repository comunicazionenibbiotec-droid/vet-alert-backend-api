#!/usr/bin/env python3
"""
Import precise vector occurrence records from GBIF into vet.ector territorial_layers.csv.

Focus: precise point records (lat/lon), not administrative centroids.
Default filters:
- country=IT
- hasCoordinate=true
- hasGeospatialIssue=false
- occurrenceStatus=PRESENT
- local coordinateUncertaintyInMeters filter <= PRECISE_VECTOR_MAX_UNCERTAINTY_M

Writes/updates data/territorial_layers.csv.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

GBIF_API = os.getenv("GBIF_OCCURRENCE_API", "https://api.gbif.org/v1/occurrence/search")
COUNTRY = os.getenv("PRECISE_VECTOR_COUNTRY", "IT")
CSV_PATH = Path(os.getenv("TERRITORIAL_LAYERS_CSV_PATH", "data/territorial_layers.csv"))
MAX_PER_SPECIES = int(os.getenv("PRECISE_VECTOR_MAX_PER_SPECIES", "300"))
MAX_PAGES = int(os.getenv("PRECISE_VECTOR_MAX_PAGES", "3"))
PAGE_SIZE = int(os.getenv("PRECISE_VECTOR_PAGE_SIZE", "300"))
MAX_UNCERTAINTY_M = float(os.getenv("PRECISE_VECTOR_MAX_UNCERTAINTY_M", "10000"))
INCLUDE_MOSQUITO_ALERT = os.getenv("PRECISE_VECTOR_INCLUDE_MOSQUITO_ALERT", "true").lower() == "true"
USER_AGENT = os.getenv("GBIF_USER_AGENT", "vetector-precise-vector-importer/220 contact=nibbiotec.com")

MOSQUITO_ALERT_DATASET_KEY = "1fef1ead-3d02-495e-8ff1-6aeb01123408"

DEFAULT_SPECIES = [
    # Flebotomi / leishmaniosi
    "Phlebotomus perniciosus",
    "Phlebotomus perfiliewi",
    "Phlebotomus neglectus",
    "Phlebotomus ariasi",
    "Phlebotomus mascitii",
    "Phlebotomus papatasi",
    "Phlebotomus sergenti",
    "Phlebotomus tobbi",
    # Zecche
    "Ixodes ricinus",
    "Dermacentor reticulatus",
    "Hyalomma marginatum",
    "Hyalomma lusitanicum",
    "Rhipicephalus sanguineus",
    "Ornithodoros erraticus",
    "Ixodes persulcatus",
    # Zanzare / altri vettori
    "Aedes albopictus",
    "Aedes aegypti",
    "Aedes japonicus",
    "Aedes koreicus",
    "Culex pipiens",
    "Anopheles maculipennis",
    "Culicoides imicola",
]

FIELDNAMES = [
    "id", "external_id", "category", "source", "display_source", "label", "scientific_name",
    "data_type", "count", "count_label", "period_start", "period_end", "country", "region",
    "province", "municipality", "location", "lat", "lon", "radius_km", "color", "url_source",
    "notes", "ui_group", "ui_group_label", "subcategory", "localization_precision", "display_radius_km",
    "coordinate_uncertainty_m", "license", "source_dataset", "updated_at"
]

GROUP_LABELS = {
    "sand_flies": "Flebotomi",
    "ticks": "Zecche",
    "mosquitoes_other_vectors": "Zanzare / altri vettori",
}
GROUP_COLORS = {
    "sand_flies": "#F26522",
    "ticks": "#7C3AED",
    "mosquitoes_other_vectors": "#2563EB",
}


def species_from_env() -> list[str]:
    raw = os.getenv("PRECISE_VECTOR_SPECIES") or os.getenv("VECTORNET_SPECIES")
    if raw:
        return [s.strip() for s in raw.split(",") if s.strip()]
    return DEFAULT_SPECIES


def ui_group_for_name(name: str, extra: str = "") -> str:
    text = f"{name} {extra}".lower()
    if "phlebotomus" in text or "phlebotomine" in text or "sand fly" in text or "sandfly" in text or "leish" in text:
        return "sand_flies"
    if any(x in text for x in ["ixodes", "dermacentor", "hyalomma", "rhipicephalus", "ornithodoros", "amblyomma", "tick"]):
        return "ticks"
    return "mosquitoes_other_vectors"


def stable_id(*parts) -> str:
    return hashlib.sha1("|".join(str(p or "").strip().lower() for p in parts).encode("utf-8")).hexdigest()[:32]


def gbif_json(params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{GBIF_API}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def good_precision(item: dict) -> bool:
    if item.get("decimalLatitude") is None or item.get("decimalLongitude") is None:
        return False
    try:
        float(item.get("decimalLatitude")); float(item.get("decimalLongitude"))
    except Exception:
        return False
    unc = item.get("coordinateUncertaintyInMeters")
    if unc in (None, ""):
        # Coordinate exists but no uncertainty declared: keep, but mark notes accordingly.
        return True
    try:
        return float(unc) <= MAX_UNCERTAINTY_M
    except Exception:
        return True


def normalise_occurrence(item: dict, requested_species: str, source_label: str) -> dict | None:
    if not good_precision(item):
        return None
    lat = float(item.get("decimalLatitude"))
    lon = float(item.get("decimalLongitude"))
    scientific = item.get("scientificName") or requested_species
    gbif_key = item.get("key") or item.get("gbifID") or item.get("occurrenceID")
    event_date = str(item.get("eventDate") or "")[:10] or ""
    year = item.get("year")
    period = event_date or (str(year) if year else "")
    group = ui_group_for_name(scientific)
    uncertainty = item.get("coordinateUncertaintyInMeters")
    uncertainty_note = f" Coordinate uncertainty: {uncertainty} m." if uncertainty not in (None, "") else " Coordinate uncertainty not declared by source."
    row_id = "precise-vector-gbif-" + stable_id(gbif_key, scientific, lat, lon)
    return {
        "id": row_id,
        "external_id": str(gbif_key or row_id),
        "category": "vectors",
        "source": source_label,
        "display_source": source_label,
        "label": scientific,
        "scientific_name": scientific,
        "data_type": "Precise vector occurrence",
        "count": "1",
        "count_label": "occurrence record",
        "period_start": period,
        "period_end": period,
        "country": item.get("country") or COUNTRY,
        "region": item.get("stateProvince") or "",
        "province": item.get("county") or "",
        "municipality": item.get("municipality") or "",
        "location": item.get("locality") or item.get("municipality") or item.get("county") or item.get("stateProvince") or "",
        "lat": f"{lat:.7f}",
        "lon": f"{lon:.7f}",
        "radius_km": "10",
        "color": GROUP_COLORS[group],
        "url_source": "https://www.gbif.org/occurrence/" + str(gbif_key) if gbif_key else "https://www.gbif.org/",
        "notes": "Precise point occurrence imported from GBIF. Contextual vector presence, not a clinical diagnosis." + uncertainty_note,
        "ui_group": group,
        "ui_group_label": GROUP_LABELS[group],
        "subcategory": group,
        "localization_precision": "coordinate / puntuale",
        "display_radius_km": "10",
        "coordinate_uncertainty_m": "" if uncertainty is None else str(uncertainty),
        "license": item.get("license") or "",
        "source_dataset": item.get("datasetName") or item.get("datasetKey") or "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_species(species: str) -> list[dict]:
    rows = []
    fetched = 0
    offset = 0
    page = 0
    while fetched < MAX_PER_SPECIES and page < MAX_PAGES:
        limit = min(PAGE_SIZE, MAX_PER_SPECIES - fetched)
        params = {
            "country": COUNTRY,
            "scientificName": species,
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT",
            "limit": limit,
            "offset": offset,
        }
        payload = gbif_json(params)
        batch = payload.get("results", [])
        if not batch:
            break
        for item in batch:
            row = normalise_occurrence(item, species, "GBIF precise occurrence")
            if row:
                rows.append(row)
        fetched += len(batch)
        offset += len(batch)
        page += 1
        if payload.get("endOfRecords"):
            break
        time.sleep(0.15)
    return rows


def fetch_mosquito_alert() -> list[dict]:
    if not INCLUDE_MOSQUITO_ALERT:
        return []
    rows = []
    fetched = 0
    offset = 0
    page = 0
    while fetched < MAX_PER_SPECIES and page < MAX_PAGES:
        limit = min(PAGE_SIZE, MAX_PER_SPECIES - fetched)
        params = {
            "country": COUNTRY,
            "datasetKey": MOSQUITO_ALERT_DATASET_KEY,
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT",
            "limit": limit,
            "offset": offset,
        }
        payload = gbif_json(params)
        batch = payload.get("results", [])
        if not batch:
            break
        for item in batch:
            row = normalise_occurrence(item, item.get("scientificName") or "Mosquito Alert occurrence", "Mosquito Alert / GBIF")
            if row:
                rows.append(row)
        fetched += len(batch)
        offset += len(batch)
        page += 1
        if payload.get("endOfRecords"):
            break
        time.sleep(0.15)
    return rows


def read_existing(path: Path) -> tuple[list[dict], list[str]]:
    if not path.exists():
        return [], FIELDNAMES[:]
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    for f in FIELDNAMES:
        if f not in fields:
            fields.append(f)
    return rows, fields


def write_rows(path: Path, rows: list[dict], fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    species_list = species_from_env()
    new_rows = []
    per_species = {}
    for species in species_list:
        try:
            rows = fetch_species(species)
            per_species[species] = len(rows)
            new_rows.extend(rows)
        except Exception as e:
            per_species[species] = f"error: {e}"
    try:
        ma_rows = fetch_mosquito_alert()
        per_species["Mosquito Alert dataset"] = len(ma_rows)
        new_rows.extend(ma_rows)
    except Exception as e:
        per_species["Mosquito Alert dataset"] = f"error: {e}"

    existing, fields = read_existing(CSV_PATH)
    by_id = {r.get("id"): r for r in existing if r.get("id")}
    inserted = updated = 0
    for row in new_rows:
        rid = row.get("id")
        if rid in by_id:
            by_id[rid].update(row)
            updated += 1
        else:
            existing.append(row)
            by_id[rid] = row
            inserted += 1
    write_rows(CSV_PATH, existing, fields)
    summary = {
        "status": "success",
        "csv_path": str(CSV_PATH),
        "country": COUNTRY,
        "max_uncertainty_m": MAX_UNCERTAINTY_M,
        "new_candidate_rows": len(new_rows),
        "inserted": inserted,
        "updated": updated,
        "total_csv_rows": len(existing),
        "per_species": per_species,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
