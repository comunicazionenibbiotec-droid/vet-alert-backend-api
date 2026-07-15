from __future__ import annotations

import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sync.esccap_connector import EsccapConnector, SOURCE

TERRITORIAL_CSV = ROOT / "data/territorial_layers/territorial_layers.csv"
FIELDNAMES = [
    "external_id","category","source","label","scientific_name","data_type","count",
    "period_start","period_end","country","region","province","location","lat","lon",
    "radius_km","color","url_source","notes"
]


def read_existing_without_source(path: Path, source: str):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [r for r in reader if (r.get("source") or "").strip().upper() != source.upper()]


def write_rows(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def main():
    existing = read_existing_without_source(TERRITORIAL_CSV, SOURCE)
    esccap_rows = EsccapConnector().fetch()
    rows = existing + esccap_rows
    write_rows(TERRITORIAL_CSV, rows)
    print(f"OK ESCCAP rows={len(esccap_rows)} total_territorial_rows={len(rows)}")


if __name__ == "__main__":
    main()
