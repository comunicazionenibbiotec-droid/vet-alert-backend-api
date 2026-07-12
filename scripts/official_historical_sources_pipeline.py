#!/usr/bin/env python3
"""vet.ector v97 official historical sources pipeline.

Purpose
-------
Build normalized WAHIS/ADIS CSV files that can replace synthetic demo events
for platform demonstrations.

The script supports two operating modes:
1. If WAHIS_SOURCE_CSV_URL / ADIS_SOURCE_CSV_URL are configured, it downloads
   source CSV files, normalizes them, and writes:
      backend/data/official_sources/wahis_events.csv
      backend/data/official_sources/adis_events.csv
2. If the URLs are not configured, existing CSVs are kept and only metadata is
   refreshed. This avoids breaking the automation while source agreements or
   exports are still being finalized.

Expected normalized output schema
---------------------------------
external_id,source,disease,disease_it,diagnosis_status,species,animal_group,
observation_date,report_date,country,region,location,lat,lon,url_source,notes

Important
---------
This pipeline does not scrape WAHIS or ADIS web pages. It expects normalized or
semi-normalized CSV exports from an authorized/public source URL. This is safer
and more stable for a product workflow.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

OUT_DIR = Path(os.getenv("OFFICIAL_SOURCES_DIR", "backend/data/official_sources"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR = OUT_DIR / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

MAX_VISIBLE_DAYS = int(os.getenv("MAX_VISIBLE_DAYS", "365"))
KEEP_ARCHIVE = os.getenv("KEEP_ARCHIVE", "true").lower() == "true"

FIELDS = [
    "external_id", "source", "disease", "disease_it", "diagnosis_status",
    "species", "animal_group", "observation_date", "report_date", "country",
    "region", "location", "lat", "lon", "url_source", "notes"
]

SOURCE_URLS = {
    "WAHIS": os.getenv("WAHIS_SOURCE_CSV_URL", "").strip(),
    "ADIS": os.getenv("ADIS_SOURCE_CSV_URL", "").strip(),
}

OUTPUT_FILES = {
    "WAHIS": OUT_DIR / "wahis_events.csv",
    "ADIS": OUT_DIR / "adis_events.csv",
}

SPECIES_MAP = {
    # companion
    "dog": ("Cane", "dog"), "dogs": ("Cane", "dog"), "cane": ("Cane", "dog"),
    "cat": ("Gatto", "cat"), "cats": ("Gatto", "cat"), "gatto": ("Gatto", "cat"),
    # livestock
    "bovine": ("Bovino", "bovine"), "bovino": ("Bovino", "bovine"), "bovini": ("Bovino", "bovine"), "cattle": ("Bovino", "bovine"), "cow": ("Bovino", "bovine"),
    "swine": ("Suino / cinghiale", "swine"), "suino": ("Suino / cinghiale", "swine"), "suini": ("Suino / cinghiale", "swine"), "pig": ("Suino / cinghiale", "swine"), "wild boar": ("Suino / cinghiale", "swine"), "cinghiale": ("Suino / cinghiale", "swine"),
    "ovine": ("Ovino", "ovine"), "ovino": ("Ovino", "ovine"), "ovini": ("Ovino", "ovine"), "sheep": ("Ovino", "ovine"),
    "caprine": ("Caprino", "caprine"), "caprino": ("Caprino", "caprine"), "caprini": ("Caprino", "caprine"), "goat": ("Caprino", "caprine"),
    "equine": ("Equino", "equine"), "equino": ("Equino", "equine"), "equini": ("Equino", "equine"), "horse": ("Equino", "equine"),
    "poultry": ("Avicoli / volatili", "poultry"), "avicoli": ("Avicoli / volatili", "poultry"), "avian": ("Avicoli / volatili", "poultry"), "bird": ("Avicoli / volatili", "poultry"), "volatili": ("Avicoli / volatili", "poultry"),
}

ALIASES = {
    "external_id": ["external_id", "event_id", "id", "notification_id", "report_id"],
    "disease": ["disease", "disease_name", "disease_original", "malattia"],
    "disease_it": ["disease_it", "malattia_it", "italian_name"],
    "diagnosis_status": ["diagnosis_status", "status", "event_status", "confirmation_status"],
    "species": ["species", "specie", "species_name", "animal_species"],
    "animal_group": ["animal_group", "group", "species_group", "taxon_group"],
    "observation_date": ["observation_date", "event_date", "occurrence_date", "date", "start_date"],
    "report_date": ["report_date", "notification_date", "publication_date", "reported_at"],
    "country": ["country", "country_name"],
    "region": ["region", "admin1", "province_region"],
    "location": ["location", "locality", "province", "municipality", "place"],
    "lat": ["lat", "latitude", "y"],
    "lon": ["lon", "lng", "longitude", "x"],
    "url_source": ["url_source", "source_url", "url", "link"],
    "notes": ["notes", "comment", "remarks"],
}


def today_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def read_csv_from_url(url: str) -> List[Dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "vetector-official-source-refresh/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        raw = response.read().decode("utf-8-sig")
    return list(csv.DictReader(raw.splitlines()))


def pick(row: Dict[str, str], canonical: str) -> str:
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for name in ALIASES.get(canonical, [canonical]):
        if name.lower() in lower and lower[name.lower()] not in (None, ""):
            return str(lower[name.lower()]).strip()
    return ""


def normalize_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    # Accept ISO-like dates and common dd/mm/yyyy.
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(value[:19], fmt).date().isoformat()
        except Exception:
            pass
    # Last fallback: let backend decide, but keep first 10 chars if plausible.
    return value[:10]


def normalize_species(species: str, animal_group: str = "") -> Tuple[str, str]:
    text = f"{species} {animal_group}".lower().strip()
    for key, mapped in SPECIES_MAP.items():
        if key in text:
            return mapped
    return (species.strip() or "Animale", animal_group.strip() or "unknown")


def make_external_id(source: str, row: Dict[str, str]) -> str:
    explicit = pick(row, "external_id")
    if explicit:
        return explicit
    payload = "|".join([
        source,
        pick(row, "disease"),
        pick(row, "species"),
        pick(row, "observation_date"),
        pick(row, "country"),
        pick(row, "region"),
        pick(row, "location"),
        pick(row, "lat"),
        pick(row, "lon"),
    ])
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{source}-{digest}"


def normalize_rows(source: str, rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for row in rows:
        species_label, group = normalize_species(pick(row, "species"), pick(row, "animal_group"))
        normalized = {
            "external_id": make_external_id(source, row),
            "source": source,
            "disease": pick(row, "disease"),
            "disease_it": pick(row, "disease_it") or pick(row, "disease"),
            "diagnosis_status": pick(row, "diagnosis_status") or "Confermato",
            "species": species_label,
            "animal_group": group,
            "observation_date": normalize_date(pick(row, "observation_date")),
            "report_date": normalize_date(pick(row, "report_date")) or normalize_date(pick(row, "observation_date")),
            "country": pick(row, "country") or "Italy",
            "region": pick(row, "region"),
            "location": pick(row, "location"),
            "lat": pick(row, "lat"),
            "lon": pick(row, "lon"),
            "url_source": pick(row, "url_source"),
            "notes": pick(row, "notes") or f"Official historical {source} record",
        }
        # Required fields for the backend map. Skip incomplete records.
        if not normalized["disease"] or not normalized["observation_date"] or not normalized["lat"] or not normalized["lon"]:
            continue
        out.append(normalized)
    return out


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def archive_copy(source: str, rows: List[Dict[str, str]]) -> None:
    if not KEEP_ARCHIVE:
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    archive_path = ARCHIVE_DIR / f"{source.lower()}_events_{stamp}.csv"
    write_csv(archive_path, rows)


def refresh_source(source: str, url: str) -> Dict[str, object]:
    output = OUTPUT_FILES[source]
    if not url:
        existing_count = 0
        if output.exists():
            with output.open("r", encoding="utf-8-sig") as f:
                existing_count = max(0, sum(1 for _ in f) - 1)
        return {"source": source, "mode": "kept_existing_no_url", "records": existing_count, "output": str(output)}
    raw_rows = read_csv_from_url(url)
    normalized = normalize_rows(source, raw_rows)
    write_csv(output, normalized)
    archive_copy(source, normalized)
    return {"source": source, "mode": "downloaded", "records": len(normalized), "output": str(output)}


def main() -> int:
    metadata = {
        "refreshed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "max_visible_days": MAX_VISIBLE_DAYS,
        "outputs": [],
        "note": "Backend map visibility is controlled by the days filter, for example 365 days.",
    }
    for source, url in SOURCE_URLS.items():
        try:
            result = refresh_source(source, url)
        except Exception as exc:
            # Keep existing file if a remote source fails; this avoids breaking the daily workflow.
            result = {"source": source, "mode": "error_kept_existing", "error": str(exc), "output": str(OUTPUT_FILES[source])}
        metadata["outputs"].append(result)
    (OUT_DIR / "refresh_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
