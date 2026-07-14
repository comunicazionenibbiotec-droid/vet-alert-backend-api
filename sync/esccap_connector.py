from __future__ import annotations

import csv
import io
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

DEFAULT_LOCAL_CSV = "data/territorial_layers/esccap_parasites.csv"
DEFAULT_TIMEOUT = int(os.getenv("ESCCAP_TIMEOUT_SECONDS", "30"))

CATEGORY = "parasites"
SOURCE = "ESCCAP"
DEFAULT_COLOR = "#059669"
DEFAULT_RADIUS_KM = 25.0

REGIONAL_CAPITALS = {
    "Abruzzo": (42.3498, 13.3995, "L'Aquila"),
    "Basilicata": (40.6395, 15.8051, "Potenza"),
    "Calabria": (38.9059, 16.5944, "Catanzaro"),
    "Campania": (40.8518, 14.2681, "Napoli"),
    "Emilia-Romagna": (44.4949, 11.3426, "Bologna"),
    "Friuli-Venezia Giulia": (45.6495, 13.7768, "Trieste"),
    "Lazio": (41.9028, 12.4964, "Roma"),
    "Liguria": (44.4056, 8.9463, "Genova"),
    "Lombardia": (45.4642, 9.1900, "Milano"),
    "Marche": (43.6158, 13.5189, "Ancona"),
    "Molise": (41.5603, 14.6627, "Campobasso"),
    "Piemonte": (45.0703, 7.6869, "Torino"),
    "Puglia": (41.1171, 16.8719, "Bari"),
    "Sardegna": (39.2238, 9.1217, "Cagliari"),
    "Sicilia": (38.1157, 13.3615, "Palermo"),
    "Toscana": (43.7696, 11.2558, "Firenze"),
    "Trentino-Alto Adige": (46.0664, 11.1258, "Trento"),
    "Umbria": (43.1107, 12.3908, "Perugia"),
    "Valle d'Aosta": (45.7370, 7.3201, "Aosta"),
    "Veneto": (45.4384, 12.3265, "Venezia"),
}

ANIMAL_GROUP_MAP = {
    "dog": "dog", "cane": "dog", "canine": "dog",
    "cat": "cat", "gatto": "cat", "feline": "cat",
    "dogs": "dog", "cats": "cat",
}

DISPLAY_SOURCE = "ESCCAP"
DATA_TYPE = "positive_tests_aggregate"


def _now_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _read_text_from_url(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "vetector-esccap-import/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8-sig")


def _read_csv_text(path_or_url: str | None = None) -> str:
    remote = os.getenv("ESCCAP_REMOTE_CSV_URL", "").strip()
    source = path_or_url or remote
    if source and source.lower().startswith(("http://", "https://")):
        return _read_text_from_url(source)
    local = source or os.getenv("ESCCAP_CSV_PATH", DEFAULT_LOCAL_CSV)
    return Path(local).read_text(encoding="utf-8-sig")


def normalize_animal_group(value: str) -> str:
    key = (value or "").strip().lower()
    return ANIMAL_GROUP_MAP.get(key, key or "companion")


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    text = str(value).strip().replace(",", ".")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        text = str(value or "").strip()
        if not text:
            return default
        return int(float(text.replace(",", ".")))
    except Exception:
        return default


def _coerce_lat_lon(row: Dict[str, str]) -> tuple[float, float, str, str]:
    lat = safe_float(row.get("lat"))
    lon = safe_float(row.get("lon"))
    location = (row.get("location") or row.get("area") or row.get("region") or "Italy").strip()
    note_extra = ""
    if lat is not None and lon is not None:
        return lat, lon, location, "coordinates provided by curated ESCCAP CSV"
    region = (row.get("region") or "").strip()
    if region in REGIONAL_CAPITALS:
        lat, lon, capital = REGIONAL_CAPITALS[region]
        location = region
        note_extra = f"coordinates set to regional capital {capital} for area-level display"
        return lat, lon, location, note_extra
    return 41.9028, 12.4964, location, "coordinates unavailable; fallback set to Rome for display"


def parse_esccap_csv(path_or_url: str | None = None) -> List[Dict[str, Any]]:
    text = _read_csv_text(path_or_url)
    reader = csv.DictReader(io.StringIO(text))
    rows: List[Dict[str, Any]] = []
    for i, raw in enumerate(reader, start=1):
        parasite = (raw.get("parasite") or raw.get("label") or raw.get("infection") or "").strip()
        if not parasite:
            continue
        species = (raw.get("animal_species") or raw.get("species") or "Cane/Gatto").strip()
        group = normalize_animal_group(raw.get("animal_group") or species)
        region = (raw.get("region") or "").strip()
        province = (raw.get("province") or "").strip()
        lat, lon, location, geo_note = _coerce_lat_lon(raw)
        period_start = (raw.get("period_start") or raw.get("date_start") or "").strip()
        period_end = (raw.get("period_end") or raw.get("date_end") or _now_iso()).strip()
        count = safe_int(raw.get("count") or raw.get("positive_tests") or raw.get("n_positive"), 0)
        total = safe_int(raw.get("tested") or raw.get("n_tested") or raw.get("sample_size"), 0)
        percent = (raw.get("percent_positive") or raw.get("positive_percent") or "").strip()
        radius = safe_float(raw.get("radius_km"), DEFAULT_RADIUS_KM) or DEFAULT_RADIUS_KM
        external_id = (raw.get("external_id") or f"ESCCAP-{period_end[:4] or 'YYYY'}-IT-{region or 'AREA'}-{parasite}-{group}-{i}").replace(" ", "_")
        note_base = (raw.get("notes") or "").strip()
        interpretation = "ESCCAP maps represent percentage of positive tests among screened pets, not true population prevalence"
        notes = "; ".join([n for n in [note_base, interpretation, geo_note] if n])
        data_type = (raw.get("data_type") or DATA_TYPE).strip() or DATA_TYPE
        label = parasite
        if percent:
            label = f"{parasite}"
        rows.append({
            "external_id": external_id,
            "category": CATEGORY,
            "source": SOURCE,
            "label": label,
            "scientific_name": (raw.get("scientific_name") or parasite).strip(),
            "data_type": data_type,
            "count": count,
            "period_start": period_start,
            "period_end": period_end,
            "country": (raw.get("country") or "Italy").strip(),
            "region": region,
            "province": province,
            "location": location,
            "lat": lat,
            "lon": lon,
            "radius_km": radius,
            "color": (raw.get("color") or DEFAULT_COLOR).strip(),
            "url_source": (raw.get("url_source") or "https://www.esccap.org/parasite-infection-map/").strip(),
            "notes": notes,
        })
    return rows


class EsccapConnector:
    source_name = "ESCCAP_CSV"

    def fetch(self) -> List[Dict[str, Any]]:
        return parse_esccap_csv()
