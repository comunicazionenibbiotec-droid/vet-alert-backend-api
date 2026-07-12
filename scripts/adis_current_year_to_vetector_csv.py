#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

CSV_FIELDS = [
    "external_id", "source", "disease", "disease_it", "diagnosis_status",
    "species", "animal_group", "observation_date", "report_date", "country",
    "region", "location", "lat", "lon", "url_source", "notes"
]

DISEASE_MAP = {
    "A.S.F. in domestic pigs": ("Peste suina africana", "Suino / cinghiale", "swine"),
    "A.S.F. in wild boar": ("Peste suina africana", "Suino / cinghiale", "swine"),
    "African swine fever": ("Peste suina africana", "Suino / cinghiale", "swine"),
    "Highly pathogenic avian influenza": ("Influenza aviaria ad alta patogenicita", "Avicoli / volatili", "poultry"),
    "Enzootic bovine leukosis": ("Leucosi bovina enzootica", "Bovino", "bovine"),
    "Lumpy skin disease": ("Dermatite nodulare contagiosa", "Bovino", "bovine"),
    "Mycobacterium tuberculosis complex": ("Tubercolosi bovina", "Bovino", "bovine"),
    "West Nile fever": ("West Nile Fever", "Equino", "equine"),
    "Bluetongue": ("Bluetongue", "Ovino", "ovine"),
    "Rabies": ("Rabbia", "Cane", "dog"),
    "Aethina tumida": ("Aethina tumida", "Avicoli / volatili", "poultry"),
}

# Minimal fallback geocoding for recurrent Italian locations in ADIS public reports.
GEOCODE_FALLBACK = {
    "Comano": ("Toscana", 44.29335, 10.13109),
    "Genova": ("Liguria", 44.40478, 8.94439),
    "Rapallo": ("Liguria", 44.34960, 9.22796),
    "Fivizzano": ("Toscana", 44.23784, 10.12650),
    "Bagnone": ("Toscana", 44.31500, 9.99500),
    "Barga": ("Toscana", 44.07310, 10.48050),
    "Licciana Nardi": ("Toscana", 44.26490, 10.03870),
    "San Marcello Pistoiese": ("Toscana", 44.05560, 10.79060),
    "Collagna": ("Emilia-Romagna", 44.34700, 10.27400),
    "Busana": ("Emilia-Romagna", 44.36770, 10.32040),
    "Monchio Delle Corti": ("Emilia-Romagna", 44.40910, 10.12430),
    "Ligonchio": ("Emilia-Romagna", 44.31600, 10.33800),
    "Felino": ("Emilia-Romagna", 44.69230, 10.24100),
    "Langhirano": ("Emilia-Romagna", 44.61240, 10.26600),
    "Rivergaro": ("Emilia-Romagna", 44.91130, 9.59700),
    "Medesano": ("Emilia-Romagna", 44.75650, 10.14000),
    "San Marco In Lamis": ("Puglia", 41.71210, 15.63825),
    "San Marco in Lamis": ("Puglia", 41.71210, 15.63825),
}


def read_existing(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in CSV_FIELDS})


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 vet.ector ADIS CSV automation (+https://vet.ector.nibbiotec.com)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_tags(html: str) -> str:
    # Remove scripts/styles first, then HTML tags. This is deliberately simple/best-effort.
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text


def detect_report_date(text: str) -> str:
    # Prefer current date if report date is difficult to parse.
    # ADIS public report sometimes renders dates via scripts or dynamic UI.
    return datetime.now(timezone.utc).date().isoformat()


def parse_best_effort(text: str, country: str, url: str) -> Tuple[List[Dict[str, str]], List[str]]:
    rows: List[Dict[str, str]] = []
    skipped: List[str] = []
    report_date = detect_report_date(text)

    # Best-effort pattern for explicit outbreak IDs like IT-ASF-2026-00826 nearby context.
    ids = re.findall(r"\bIT-[A-Z0-9]+-2026-\d{5}\b", text)
    unique_ids = []
    seen = set()
    for item in ids:
        if item not in seen:
            unique_ids.append(item)
            seen.add(item)

    # If the public HTML is rendered dynamically, there may be no IDs in raw HTML.
    # In that case return zero rows and let the workflow keep the existing CSV.
    if not unique_ids:
        return [], skipped

    for outbreak_id in unique_ids:
        # Inspect a window around the ID to infer disease/location.
        idx = text.find(outbreak_id)
        window = text[max(0, idx - 500): idx + 1000]

        disease = ""
        for d in DISEASE_MAP:
            if d.lower() in window.lower():
                disease = d
                break
        if not disease:
            if "ASF" in outbreak_id:
                disease = "A.S.F. in wild boar"
            else:
                skipped.append(f"{outbreak_id}: disease not detected")
                continue

        disease_it, species, animal_group = DISEASE_MAP.get(disease, (disease, "Animale", "unknown"))

        location = ""
        region = ""
        lat = lon = None
        for loc, geo in GEOCODE_FALLBACK.items():
            if re.search(r"\b" + re.escape(loc) + r"\b", window, flags=re.I):
                location = loc
                region, lat, lon = geo
                break

        if lat is None or lon is None:
            skipped.append(f"{outbreak_id}: location not geocoded")
            continue

        rows.append({
            "external_id": outbreak_id,
            "source": "ADIS",
            "disease": disease,
            "disease_it": disease_it,
            "diagnosis_status": "Confermato",
            "species": species,
            "animal_group": animal_group,
            "observation_date": report_date,
            "report_date": report_date,
            "country": country,
            "region": region,
            "location": location,
            "lat": f"{float(lat):.5f}",
            "lon": f"{float(lon):.5f}",
            "url_source": url,
            "notes": "Official ADIS public current-year report; parsed best-effort; location approximated at municipality centroid",
        })

    return rows, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.getenv("OFFICIAL_SOURCES_DIR", "data/official_sources"))
    ap.add_argument("--url", default=os.getenv("ADIS_PUBLIC_REPORT_URL", "https://webgate.ec.europa.eu/tracesnt/adis/public/notification/outbreaks-current-year-report"))
    ap.add_argument("--country", default=os.getenv("ADIS_COUNTRY", "Italy"))
    args = ap.parse_args()

    out_dir = Path(args.dir)
    csv_path = out_dir / "adis_events.csv"
    metadata_path = out_dir / "adis_refresh_metadata.json"
    preview_path = out_dir / "adis_last_response_preview.txt"

    existing = read_existing(csv_path)
    rows: List[Dict[str, str]] = []
    skipped: List[str] = []
    error = None
    raw_text = ""
    contexts_detected = 0

    try:
        html = fetch_text(args.url)
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(html[:20000], encoding="utf-8")
        raw_text = strip_tags(html)
        rows, skipped = parse_best_effort(raw_text, args.country, args.url)
        contexts_detected = len(re.findall(r"\bIT-[A-Z0-9]+-2026-\d{5}\b", raw_text))
    except Exception as exc:
        error = str(exc)

    fail_on_zero = os.getenv("ADIS_FAIL_ON_ZERO_ROWS", "false").lower() == "true"

    if rows:
        write_csv(csv_path, rows)
        action = "generated_new_csv"
    else:
        # Keep existing ADIS CSV. This is intentional: the ADIS public report is not a stable API
        # and can render rows dynamically, so zero parsed rows should not break the daily workflow.
        if not existing:
            # Create a valid empty CSV if nothing exists, so validation can still explain the issue clearly.
            write_csv(csv_path, [])
        action = "kept_existing_csv_zero_rows"
        if fail_on_zero:
            print("No ADIS rows generated and ADIS_FAIL_ON_ZERO_ROWS=true.", file=sys.stderr)

    metadata = {
        "source": "ADIS",
        "url": args.url,
        "country": args.country,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contexts_detected": contexts_detected,
        "rows_generated": len(rows),
        "existing_rows_before": len(existing),
        "rows_skipped": len(skipped),
        "skipped_sample": skipped[:20],
        "action": action,
        "warning": None if rows else "No rows generated from public ADIS page; existing CSV kept. Use normalized source CSV or update parser/geocoding.",
        "error": error,
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))

    if fail_on_zero and not rows:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
