#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ADIS_URL = os.getenv("ADIS_CURRENT_YEAR_URL", "https://webgate.ec.europa.eu/tracesnt/adis/public/notification/outbreaks-current-year-report").strip()
COUNTRY = os.getenv("ADIS_COUNTRY", "Italy").strip()
OUT_DIR = Path(os.getenv("OFFICIAL_SOURCES_DIR", "data/official_sources"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
GEOCODING_FILE = Path(os.getenv("GEOCODING_FILE", "data/official_sources/geocoding_it.csv"))
ALLOW_COUNTRY_CENTROID = os.getenv("ADIS_ALLOW_COUNTRY_CENTROID", "false").lower() == "true"

FIELDS = ["external_id", "source", "disease", "disease_it", "diagnosis_status", "species", "animal_group", "observation_date", "report_date", "country", "region", "location", "lat", "lon", "url_source", "notes"]

COUNTRY_CENTROIDS = {"Italy": (41.8719, 12.5674)}

DISEASE_RULES = [
    ("A.S.F. in domestic pigs", "A.S.F. in domestic pigs", "Peste suina africana", "Suino / cinghiale", "swine"),
    ("A.S.F. in wild boar", "A.S.F. in wild boar", "Peste suina africana", "Suino / cinghiale", "swine"),
    ("Enzootic bovine leukosis", "Enzootic bovine leukosis", "Leucosi bovina enzootica", "Bovino", "bovine"),
    ("High pathogenicity avian influenza", "High pathogenicity avian influenza viruses (poultry) (Inf. with) / H5N1", "Influenza aviaria ad alta patogenicita - pollame H5N1", "Avicoli / volatili", "poultry"),
    ("HPAI(P)", "High pathogenicity avian influenza viruses (poultry) (Inf. with) / H5N1", "Influenza aviaria ad alta patogenicita - pollame H5N1", "Avicoli / volatili", "poultry"),
    ("HPAI(NON-P)", "HPAI(NON-P) in Wild Birds / H5N1", "Influenza aviaria ad alta patogenicita - uccelli selvatici", "Avicoli / volatili", "poultry"),
    ("Lumpy skin disease", "Lumpy skin disease virus (Inf. with)", "Dermatite nodulare contagiosa", "Bovino", "bovine"),
    ("Mycobacterium tuberculosis complex", "Mycobacterium tuberculosis complex (Inf. with)(2019-)", "Tubercolosi bovina / complesso Mycobacterium tuberculosis", "Bovino", "bovine"),
    ("Rabies virus", "Rabies virus (Inf. with) / RABV", "Rabbia", "Cane", "dog"),
    ("West Nile", "West Nile Fever", "West Nile Fever", "Avicoli / volatili", "poultry"),
    ("Aethina tumida", "Aethina tumida (Inf. with)(Small hive beetle)(2006-)", "Aethina tumida / piccolo coleottero dell alveare", "Altro", "other"),
]

SPECIES_NOISE = {"Swine", "Wild boar", "Cattle", "Birds", "Poultry", "Dog", "Duck", "Goose", "Falcon", "Wild birds"}

@dataclass
class DiseaseCtx:
    disease: str
    disease_it: str
    species: str
    animal_group: str
    ids: list[str]
    locations: list[str]


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "vetector-adis-current-year-sync/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def html_to_lines(raw: str) -> list[str]:
    text = re.sub(r"<script.*?</script>", " ", raw, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [line for line in lines if line]


def report_date_from_text(raw: str) -> str:
    patterns = [
        r"Reporting period:\s*\d{2}/\d{2}/\d{4}\s*-\s*(\d{2}/\d{2}/\d{4})",
        r"created on\s+(\d{2}/\d{2}/\d{4})",
    ]
    for pattern in patterns:
        m = re.search(pattern, raw, flags=re.I)
        if m:
            try:
                return dt.datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat()
            except Exception:
                pass
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def classify_disease(line: str) -> tuple[str, str, str, str] | None:
    low = line.lower()
    for token, disease, disease_it, species, group in DISEASE_RULES:
        if token.lower() in low:
            return disease, disease_it, species, group
    return None


def looks_like_location(line: str) -> bool:
    if not line or line in SPECIES_NOISE:
        return False
    if len(line) > 80:
        return False
    if re.search(r"IT-[A-Z0-9().-]+-20\d{2}-\d{4,5}", line):
        return False
    if classify_disease(line):
        return False
    if line.startswith("|") or line in {"---", "Italy", "### Italy"}:
        return False
    # municipality names generally contain letters and no sentence punctuation
    return bool(re.search(r"[A-Za-zÀ-ÿ]", line))


def load_geocoding(path: Path) -> dict[str, tuple[str, float, float]]:
    data: dict[str, tuple[str, float, float]] = {}
    if not path.exists():
        return data
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            loc = (row.get("location") or "").strip()
            if not loc:
                continue
            data[loc.lower()] = (row.get("region", ""), float(row.get("lat", "0")), float(row.get("lon", "0")))
    return data


def italy_section(lines: list[str]) -> list[str]:
    # Prefer markdown heading transformed by web extraction if present; otherwise first Italy marker.
    start = None
    for i, line in enumerate(lines):
        if line.strip() in {"Italy", "### Italy"}:
            start = i
            break
    if start is None:
        return lines
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("### ") and lines[j] not in {"### Italy"}:
            end = j
            break
    return lines[start:end]


def parse_italy_events(lines: list[str]) -> list[DiseaseCtx]:
    contexts: list[DiseaseCtx] = []
    current: DiseaseCtx | None = None

    def flush():
        nonlocal current
        if current and current.ids:
            contexts.append(current)
        current = None

    for line in lines:
        found = classify_disease(line)
        if found:
            flush()
            disease, disease_it, species, group = found
            current = DiseaseCtx(disease=disease, disease_it=disease_it, species=species, animal_group=group, ids=[], locations=[])
            # IDs may be on same line.
            current.ids.extend(re.findall(r"IT-[A-Z0-9().-]+-20\d{2}-\d{4,5}", line))
            continue
        if current is None:
            continue
        ids = re.findall(r"IT-[A-Z0-9().-]+-20\d{2}-\d{4,5}", line)
        if ids:
            current.ids.extend(ids)
            continue
        if looks_like_location(line):
            # Split simple lists that survive HTML stripping on one line.
            parts = [p.strip() for p in re.split(r"\s{2,}|;", line) if p.strip()]
            for part in parts:
                if looks_like_location(part):
                    current.locations.append(part)
    flush()

    # Deduplicate IDs and locations while preserving order.
    for ctx in contexts:
        seen_ids = set(); ctx.ids = [x for x in ctx.ids if not (x in seen_ids or seen_ids.add(x))]
        seen_loc = set(); ctx.locations = [x for x in ctx.locations if not (x.lower() in seen_loc or seen_loc.add(x.lower()))]
    return contexts


def build_rows(contexts: Iterable[DiseaseCtx], report_date: str, geocoding: dict[str, tuple[str, float, float]]) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    skipped: list[dict] = []
    for ctx in contexts:
        if not ctx.ids:
            continue
        if not ctx.locations:
            ctx.locations = [COUNTRY]
        for idx, event_id in enumerate(ctx.ids):
            loc = ctx.locations[idx % len(ctx.locations)]
            geokey = loc.lower()
            if geokey in geocoding:
                region, lat, lon = geocoding[geokey]
            elif ALLOW_COUNTRY_CENTROID:
                region, lat, lon = "", COUNTRY_CENTROIDS.get(COUNTRY, (0.0, 0.0))[0], COUNTRY_CENTROIDS.get(COUNTRY, (0.0, 0.0))[1]
            else:
                skipped.append({"external_id": event_id, "reason": "missing_geocode", "location": loc, "disease": ctx.disease})
                continue
            rows.append({
                "external_id": event_id,
                "source": "ADIS",
                "disease": ctx.disease,
                "disease_it": ctx.disease_it,
                "diagnosis_status": "Confermato",
                "species": ctx.species,
                "animal_group": ctx.animal_group,
                "observation_date": report_date,
                "report_date": report_date,
                "country": COUNTRY,
                "region": region,
                "location": loc,
                "lat": f"{lat:.6f}",
                "lon": f"{lon:.6f}",
                "url_source": ADIS_URL,
                "notes": "Official ADIS current-year public report; location approximated at municipality centroid; event date set to report end date when individual date is not exposed in public detail.",
            })
    # Deduplicate by external_id.
    unique = {row["external_id"]: row for row in rows}
    return sorted(unique.values(), key=lambda r: r["external_id"]), skipped


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    raw = fetch_text(ADIS_URL)
    lines = html_to_lines(raw)
    section = italy_section(lines)
    report_date = report_date_from_text(raw)
    geocoding = load_geocoding(GEOCODING_FILE)
    contexts = parse_italy_events(section)
    rows, skipped = build_rows(contexts, report_date, geocoding)
    output = OUT_DIR / "adis_events.csv"
    write_csv(output, rows)
    metadata = {
        "source": "ADIS",
        "url": ADIS_URL,
        "country": COUNTRY,
        "report_date": report_date,
        "contexts_detected": len(contexts),
        "rows_written": len(rows),
        "rows_skipped": len(skipped),
        "skipped_sample": skipped[:50],
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    (OUT_DIR / "adis_refresh_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    if not rows:
        raise SystemExit("No ADIS rows generated. Check parser or source format.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
