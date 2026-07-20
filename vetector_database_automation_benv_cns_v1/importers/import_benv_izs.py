import csv
import json
import os
from pathlib import Path

import requests

from common import db, finish_run, load_json, stable_id, start_run, upsert_event

SOURCE_ID = "benv_izs"
BENV_PAGE = "https://www.izs.it/BENV_NEW/datiemappe.html"
PROVINCES_PATH = os.getenv("PROVINCE_CENTROIDS_JSON", "data/province_centroids_italy_minimal.json")


def read_rows_from_csv(path_or_url):
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        content = requests.get(path_or_url, timeout=45, headers={"User-Agent": "vetector-importer/1.0"}).text
        lines = content.splitlines()
    else:
        lines = Path(path_or_url).read_text(encoding="utf-8-sig").splitlines()
    return list(csv.DictReader(lines))


def normalize_benv_row(row, centroids):
    disease = row.get("disease") or row.get("malattia") or row.get("Malattia") or row.get("patologia")
    province = row.get("province") or row.get("Provincia") or row.get("provincia")
    location = row.get("municipality") or row.get("Comune") or row.get("comune") or province
    species = row.get("species") or row.get("Specie") or row.get("specie")
    event_date = row.get("date") or row.get("Data") or row.get("mese") or row.get("Mese")
    meta = centroids.get(province or "", {})
    lat = row.get("lat") or row.get("latitude") or meta.get("lat")
    lon = row.get("lon") or row.get("lng") or row.get("longitude") or meta.get("lon")
    if not disease or not lat or not lon:
        return None
    event_id = "benv-" + stable_id(disease, species, province, location, event_date, row)
    return {
        "id": event_id,
        "disease": disease,
        "species": species,
        "animal_group": row.get("animal_group") or row.get("gruppo_animale"),
        "diagnosis_status": row.get("diagnosis_status") or "Confermato ufficiale",
        "source": "BENV / IZS",
        "source_type": "official",
        "report_type": "official_outbreak",
        "observation_date": event_date if event_date and len(event_date) >= 10 else None,
        "report_date": None,
        "location": location,
        "region": row.get("region") or row.get("Regione") or meta.get("region"),
        "province": province,
        "country": "Italy",
        "lat": float(lat),
        "lon": float(lon),
        "risk_score": 85,
        "confidence_label": "Fonte veterinaria ufficiale",
        "url_source": BENV_PAGE,
        "raw_payload": json.dumps(row, ensure_ascii=False),
    }


def main():
    csv_source = os.getenv("BENV_CSV_URL") or os.getenv("BENV_CSV_PATH")
    if not csv_source:
        raise RuntimeError("Set BENV_CSV_URL or BENV_CSV_PATH. BENV page is dynamic; use an official export or curated CSV.")
    centroids = load_json(PROVINCES_PATH)
    rows = read_rows_from_csv(csv_source)
    events = [normalize_benv_row(row, centroids) for row in rows]
    events = [e for e in events if e]
    with db() as conn:
        run_id = start_run(conn, SOURCE_ID, {"csv_source": csv_source})
        try:
            for event in events:
                upsert_event(conn, event)
            conn.commit()
            finish_run(conn, run_id, "success", fetched=len(rows), inserted=len(events), updated=0)
        except Exception as exc:
            conn.rollback()
            finish_run(conn, run_id, "failed", fetched=len(rows), error=str(exc))
            raise
    print(json.dumps({"source": SOURCE_ID, "rows": len(rows), "events": len(events)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
