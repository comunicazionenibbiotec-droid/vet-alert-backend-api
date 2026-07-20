import json
import os
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from common import db, finish_run, load_json, stable_id, start_run, upsert_territorial_layer

SOURCE_ID = "cns_wnv"
DEFAULT_URL = "https://www.centronazionalesangue.it/west-nile-virus-2025/"
PROVINCES_PATH = os.getenv("PROVINCE_CENTROIDS_JSON", "data/province_centroids_italy_minimal.json")

PROVINCE_PATTERN = re.compile(
    r"(?:provincia|province)\s+di\s+([^\n\r]+)",
    re.IGNORECASE,
)


def split_provinces(text):
    text = re.sub(r"\([^)]*\)", "", text)
    text = text.replace(" e ", ",")
    text = text.replace("–", "-")
    parts = [p.strip(" .;:-") for p in text.split(",")]
    return [p for p in parts if p]


def fetch_cns_items(url):
    html = requests.get(url, timeout=30, headers={"User-Agent": "vetector-importer/1.0"}).text
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for node in soup.find_all(["li", "p", "a", "td"]):
        text = " ".join(node.get_text(" ", strip=True).split())
        if "WNV" in text or "West Nile" in text:
            if "Misure" in text or "prevenzione" in text or "provincia" in text or "province" in text:
                candidates.append(text)
    return candidates


def build_layers(items, centroids, source_url):
    layers = []
    for text in items:
        match = PROVINCE_PATTERN.search(text)
        if not match:
            continue
        for province in split_provinces(match.group(1)):
            meta = centroids.get(province)
            if not meta:
                continue
            layers.append({
                "id": "cns-wnv-" + stable_id(province, text),
                "category": "west_nile",
                "label": "West Nile",
                "scientific_name": None,
                "data_type": "cns_wnv_prevention_measure",
                "count": 1,
                "count_label": "misura CNS WNV",
                "country": "Italy",
                "region": meta.get("region"),
                "province": province,
                "location": province,
                "lat": meta["lat"],
                "lon": meta["lon"],
                "radius_km": 50,
                "aggregation_level": "province",
                "source": "CNS WNV",
                "display_source": "Centro Nazionale Sangue - WNV",
                "period_start": None,
                "period_end": None,
                "url_source": source_url,
                "notes": text,
                "raw_payload": json.dumps({"source_text": text}),
            })
    return layers


def main():
    url = os.getenv("CNS_WNV_URL", DEFAULT_URL)
    centroids = load_json(PROVINCES_PATH)
    items = fetch_cns_items(url)
    layers = build_layers(items, centroids, url)
    with db() as conn:
        run_id = start_run(conn, SOURCE_ID, {"url": url})
        try:
            for layer in layers:
                upsert_territorial_layer(conn, layer)
            conn.commit()
            finish_run(conn, run_id, "success", fetched=len(items), inserted=len(layers), updated=0)
        except Exception as exc:
            conn.rollback()
            finish_run(conn, run_id, "failed", fetched=len(items), error=str(exc))
            raise
    print(json.dumps({"source": SOURCE_ID, "items": len(items), "layers": len(layers)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
