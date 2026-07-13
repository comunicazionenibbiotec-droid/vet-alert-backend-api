#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Optional, Any

import pandas as pd

OUTPUT_COLUMNS = [
    "external_id", "source", "disease", "disease_it", "diagnosis_status", "species", "animal_group",
    "observation_date", "report_date", "country", "region", "location", "lat", "lon", "url_source", "notes"
]

GEOCODING_REPORT_COLUMNS = [
    "source_file", "benv_id", "raw_comune", "raw_provincia", "raw_regione",
    "matched_level", "matched_label", "lat", "lon", "note"
]

BENV_URL = "https://www.izs.it/BENV_NEW/datiemappe.html"

DISEASE_MAP = {
    "leishmaniosi": ("Leishmaniosis", "Leishmaniosi"),
    "leishmania": ("Leishmaniosis", "Leishmaniosi"),
    "brucellosi": ("Brucellosis", "Brucellosi"),
    "brucellosis": ("Brucellosis", "Brucellosi"),
    "west_nile": ("West Nile Fever", "West Nile Fever"),
    "west nile": ("West Nile Fever", "West Nile Fever"),
    "rabbia": ("Rabies", "Rabbia"),
    "rabies": ("Rabies", "Rabbia"),
    "influenza_aviaria": ("Highly pathogenic avian influenza", "Influenza aviaria ad alta patogenicita"),
    "influenza aviaria": ("Highly pathogenic avian influenza", "Influenza aviaria ad alta patogenicita"),
    "hpai": ("Highly pathogenic avian influenza", "Influenza aviaria ad alta patogenicita"),
    "blue tongue": ("Bluetongue", "Bluetongue"),
    "bluetongue": ("Bluetongue", "Bluetongue"),
    "peste_suina_africana": ("African swine fever", "Peste suina africana"),
    "peste suina africana": ("African swine fever", "Peste suina africana"),
    "psa": ("African swine fever", "Peste suina africana"),
    "tubercolosi": ("Mycobacterium tuberculosis complex", "Tubercolosi bovina / MTBC"),
    "leucosi": ("Enzootic bovine leukosis", "Leucosi bovina enzootica"),
    "aethina": ("Small hive beetle", "Aethina tumida"),
}

ANIMAL_GROUP_MAP = {
    "CANE": "dog", "CANI": "dog", "DOG": "dog",
    "GATTO": "cat", "GATTI": "cat", "CAT": "cat",
    "BOVINO": "bovine", "BOVINI": "bovine", "BUFALO": "bovine", "BUFALI": "bovine", "CATTLE": "bovine",
    "SUINO": "swine", "SUINI": "swine", "CINGHIALE": "swine", "CINGHIALI": "swine", "SWINE": "swine",
    "OVINO": "ovine", "OVINI": "ovine", "SHEEP": "ovine",
    "CAPRA": "caprine", "CAPRE": "caprine", "CAPRINO": "caprine", "CAPRINI": "caprine", "GOAT": "caprine",
    "EQUINO": "equine", "EQUINI": "equine", "HORSE": "equine",
    "AVICOLI": "poultry", "VOLATILI": "poultry", "POLLAME": "poultry", "BIRDS": "poultry",
    "API": "bees", "APE": "bees", "BEES": "bees",
    "LEPRE": "wildlife", "LEPRI": "wildlife", "FAUNA": "wildlife", "SELVATICA": "wildlife",
}

REGION_CAPITALS: Dict[str, Tuple[str, float, float]] = {
    "ABRUZZO": ("L'Aquila", 42.3498, 13.3995),
    "BASILICATA": ("Potenza", 40.6404, 15.8056),
    "CALABRIA": ("Catanzaro", 38.9098, 16.5877),
    "CAMPANIA": ("Napoli", 40.8518, 14.2681),
    "EMILIA-ROMAGNA": ("Bologna", 44.4949, 11.3426),
    "FRIULI-VENEZIA GIULIA": ("Trieste", 45.6495, 13.7768),
    "LAZIO": ("Roma", 41.9028, 12.4964),
    "LIGURIA": ("Genova", 44.4056, 8.9463),
    "LOMBARDIA": ("Milano", 45.4642, 9.1900),
    "MARCHE": ("Ancona", 43.6158, 13.5189),
    "MOLISE": ("Campobasso", 41.5603, 14.6627),
    "PIEMONTE": ("Torino", 45.0703, 7.6869),
    "PUGLIA": ("Bari", 41.1171, 16.8719),
    "SARDEGNA": ("Cagliari", 39.2238, 9.1217),
    "SICILIA": ("Palermo", 38.1157, 13.3615),
    "TOSCANA": ("Firenze", 43.7696, 11.2558),
    "TRENTINO-ALTO ADIGE": ("Trento", 46.0748, 11.1217),
    "UMBRIA": ("Perugia", 43.1107, 12.3908),
    "VALLE D'AOSTA": ("Aosta", 45.7370, 7.3201),
    "VENETO": ("Venezia", 45.4408, 12.3155),
}

# Province centroids / capitals used as fallback when municipality centroid is unavailable.
PROVINCE_CENTROIDS: Dict[str, Tuple[str, float, float]] = {
    "AG": ("Agrigento", 37.3094, 13.5858), "AL": ("Alessandria", 44.9132, 8.6200),
    "AN": ("Ancona", 43.6158, 13.5189), "AO": ("Aosta", 45.7370, 7.3201),
    "AP": ("Ascoli Piceno", 42.8536, 13.5749), "AQ": ("L'Aquila", 42.3498, 13.3995),
    "AR": ("Arezzo", 43.4633, 11.8796), "AT": ("Asti", 44.9008, 8.2066),
    "AV": ("Avellino", 40.9146, 14.7900), "BA": ("Bari", 41.1171, 16.8719),
    "BG": ("Bergamo", 45.6983, 9.6773), "BI": ("Biella", 45.5629, 8.0583),
    "BL": ("Belluno", 46.1425, 12.2167), "BN": ("Benevento", 41.1298, 14.7820),
    "BO": ("Bologna", 44.4949, 11.3426), "BR": ("Brindisi", 40.6327, 17.9418),
    "BS": ("Brescia", 45.5416, 10.2118), "BT": ("Barletta", 41.3113, 16.2908),
    "BZ": ("Bolzano", 46.4983, 11.3548), "CA": ("Cagliari", 39.2238, 9.1217),
    "CB": ("Campobasso", 41.5603, 14.6627), "CE": ("Caserta", 41.0723, 14.3311),
    "CH": ("Chieti", 42.3479, 14.1638), "CL": ("Caltanissetta", 37.4901, 14.0629),
    "CN": ("Cuneo", 44.3845, 7.5427), "CO": ("Como", 45.8081, 9.0852),
    "CR": ("Cremona", 45.1332, 10.0227), "CS": ("Cosenza", 39.2983, 16.2537),
    "CT": ("Catania", 37.5079, 15.0830), "CZ": ("Catanzaro", 38.9098, 16.5877),
    "EN": ("Enna", 37.5676, 14.2799), "FC": ("Forli", 44.2227, 12.0407),
    "FE": ("Ferrara", 44.8353, 11.6198), "FG": ("Foggia", 41.4622, 15.5446),
    "FI": ("Firenze", 43.7696, 11.2558), "FM": ("Fermo", 43.1606, 13.7183),
    "FR": ("Frosinone", 41.6396, 13.3512), "GE": ("Genova", 44.4056, 8.9463),
    "GO": ("Gorizia", 45.9415, 13.6220), "GR": ("Grosseto", 42.7635, 11.1124),
    "IM": ("Imperia", 43.8897, 8.0396), "IS": ("Isernia", 41.5960, 14.2330),
    "KR": ("Crotone", 39.0808, 17.1271), "LC": ("Lecco", 45.8566, 9.3977),
    "LE": ("Lecce", 40.3515, 18.1750), "LI": ("Livorno", 43.5485, 10.3106),
    "LO": ("Lodi", 45.3097, 9.5037), "LT": ("Latina", 41.4676, 12.9037),
    "LU": ("Lucca", 43.8429, 10.5027), "MB": ("Monza", 45.5845, 9.2744),
    "MC": ("Macerata", 43.2984, 13.4531), "ME": ("Messina", 38.1938, 15.5540),
    "MI": ("Milano", 45.4642, 9.1900), "MN": ("Mantova", 45.1564, 10.7914),
    "MO": ("Modena", 44.6471, 10.9252), "MS": ("Massa", 44.0354, 10.1397),
    "MT": ("Matera", 40.6664, 16.6043), "NA": ("Napoli", 40.8518, 14.2681),
    "NO": ("Novara", 45.4469, 8.6222), "NU": ("Nuoro", 40.3202, 9.3264),
    "OR": ("Oristano", 39.9038, 8.5926), "PA": ("Palermo", 38.1157, 13.3615),
    "PC": ("Piacenza", 45.0526, 9.6934), "PD": ("Padova", 45.4064, 11.8768),
    "PE": ("Pescara", 42.4618, 14.2161), "PG": ("Perugia", 43.1107, 12.3908),
    "PI": ("Pisa", 43.7228, 10.4017), "PN": ("Pordenone", 45.9569, 12.6605),
    "PO": ("Prato", 43.8777, 11.1022), "PR": ("Parma", 44.8015, 10.3279),
    "PT": ("Pistoia", 43.9335, 10.9173), "PU": ("Pesaro", 43.9125, 12.9155),
    "PV": ("Pavia", 45.1847, 9.1582), "PZ": ("Potenza", 40.6404, 15.8056),
    "RA": ("Ravenna", 44.4184, 12.2035), "RC": ("Reggio Calabria", 38.1113, 15.6473),
    "RE": ("Reggio Emilia", 44.6989, 10.6297), "RG": ("Ragusa", 36.9269, 14.7255),
    "RI": ("Rieti", 42.4045, 12.8567), "RM": ("Roma", 41.9028, 12.4964),
    "RN": ("Rimini", 44.0678, 12.5695), "RO": ("Rovigo", 45.0698, 11.7902),
    "SA": ("Salerno", 40.6824, 14.7681), "SI": ("Siena", 43.3188, 11.3308),
    "SO": ("Sondrio", 46.1699, 9.8788), "SP": ("La Spezia", 44.1025, 9.8241),
    "SR": ("Siracusa", 37.0755, 15.2866), "SS": ("Sassari", 40.7259, 8.5557),
    "SU": ("Carbonia", 39.1672, 8.5222), "SV": ("Savona", 44.3091, 8.4772),
    "TA": ("Taranto", 40.4644, 17.2470), "TE": ("Teramo", 42.6612, 13.6990),
    "TN": ("Trento", 46.0748, 11.1217), "TO": ("Torino", 45.0703, 7.6869),
    "TP": ("Trapani", 38.0176, 12.5362), "TR": ("Terni", 42.5636, 12.6427),
    "TS": ("Trieste", 45.6495, 13.7768), "TV": ("Treviso", 45.6669, 12.2430),
    "UD": ("Udine", 46.0711, 13.2346), "VA": ("Varese", 45.8206, 8.8251),
    "VB": ("Verbania", 45.9214, 8.5510), "VC": ("Vercelli", 45.3231, 8.4239),
    "VE": ("Venezia", 45.4408, 12.3155), "VI": ("Vicenza", 45.5455, 11.5354),
    "VR": ("Verona", 45.4384, 10.9916), "VT": ("Viterbo", 42.4207, 12.1077),
    "VV": ("Vibo Valentia", 38.6762, 16.1016),
}

LOCAL_CENTROIDS: Dict[Tuple[str, str], Tuple[str, float, float]] = {
    ("GROSSETO", "GR"): ("Grosseto", 42.7635, 11.1124),
    ("CAMPAGNATICO", "GR"): ("Campagnatico", 42.8826, 11.2731),
    ("BATTAGLIA TERME", "PD"): ("Battaglia Terme", 45.2895, 11.7843),
    ("MALO", "VI"): ("Malo", 45.6597, 11.4049),
    ("VALDOBBIADENE", "TV"): ("Valdobbiadene", 45.8993, 11.9951),
    ("BRESCIA", "BS"): ("Brescia", 45.5416, 10.2118),
    ("CINTO EUGANEO", "PD"): ("Cinto Euganeo", 45.2755, 11.6631),
    ("PEZZAZE", "BS"): ("Pezzaze", 45.7770, 10.2369),
    ("MONTE DI MALO", "VI"): ("Monte di Malo", 45.6615, 11.3615),
}


def norm(value: Any) -> str:
    return str(value or "").strip()


def key(value: Any) -> str:
    text = norm(value).upper()
    text = text.replace("’", "'").replace("`", "'").replace("\\'", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def parse_date(value: Any) -> str:
    if value is None or pd.isna(value) or norm(value) in {"", "-", "\\-"}:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = norm(value)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return text


def clean_disease_stem(raw: str) -> str:
    text = str(raw or "")
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\b20\d{2}\b", " ", text)
    text = re.sub(r"\b(italia|italy|it|nazionale|tabella|focolai|focolaio|export|benv)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text or str(raw or "").strip()

def infer_disease(path: Path, override: Optional[str]) -> Tuple[str, str, str]:
    raw = override or path.stem
    cleaned_stem = clean_disease_stem(raw)
    raw_l = cleaned_stem.lower().replace("-", "_").replace(" ", "_")
    for k, val in DISEASE_MAP.items():
        if k.lower().replace(" ", "_") in raw_l:
            return val[0], val[1], val[1]
    cleaned = cleaned_stem.strip().title()
    return cleaned, cleaned, cleaned


def load_centroids(path: Optional[Path]) -> Dict[Tuple[str, str], Tuple[str, float, float]]:
    data = dict(LOCAL_CENTROIDS)
    if not path or not path.exists():
        return data
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            comune = key(r.get("comune") or r.get("Comune") or r.get("municipality"))
            provincia = key(r.get("provincia") or r.get("Provincia") or r.get("province"))
            try:
                lat = float(str(r.get("lat") or r.get("latitude")).replace(",", "."))
                lon = float(str(r.get("lon") or r.get("lng") or r.get("longitude")).replace(",", "."))
            except Exception:
                continue
            label = norm(r.get("comune") or r.get("Comune") or r.get("municipality"))
            if comune and provincia:
                data[(comune, provincia)] = (label, lat, lon)
    return data


def animal_group(species: str) -> str:
    sp = key(species)
    for token, group in ANIMAL_GROUP_MAP.items():
        if token in sp:
            return group
    return "unknown"


def resolve_coordinates(raw_comune: str, raw_provincia: str, raw_regione: str, centroids: Dict[Tuple[str, str], Tuple[str, float, float]]):
    comune_key = key(raw_comune)
    provincia_key = key(raw_provincia)
    regione_key = key(raw_regione)

    if comune_key and provincia_key and (comune_key, provincia_key) in centroids:
        label, lat, lon = centroids[(comune_key, provincia_key)]
        return label, lat, lon, "municipality", "coordinates approximated at municipality centroid"

    if provincia_key and provincia_key in PROVINCE_CENTROIDS:
        label, lat, lon = PROVINCE_CENTROIDS[provincia_key]
        display_label = norm(raw_comune) or label
        return display_label, lat, lon, "province", "municipality centroid unavailable; coordinates set to province capital for map display"

    if regione_key and regione_key in REGION_CAPITALS:
        label, lat, lon = REGION_CAPITALS[regione_key]
        display_label = norm(raw_comune) or norm(raw_regione) or label
        return display_label, lat, lon, "region", "municipality/province centroid unavailable; coordinates set to regional capital for map display"

    # Last resort to keep CSV valid; should be rare and reported clearly.
    return norm(raw_comune) or norm(raw_regione) or "Italy", 41.9028, 12.4964, "country", "municipality/province/region centroid unavailable; coordinates set to Rome for map display"


def read_benv_xlsx(path: Path, disease_override: Optional[str], centroids):
    disease, disease_it, _disease_slug = infer_disease(path, disease_override)
    df = pd.read_excel(path, sheet_name=0, engine="openpyxl")
    rows: list[dict] = []
    geocode_rows: list[dict] = []
    required = {"ID", "Tipo focolaio", "Stato sanitario", "Data conferma", "Data sospetto", "Data estinzione", "Specie", "Comune", "Provincia", "Regione"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing columns: {sorted(missing)}")

    for _, r in df.iterrows():
        original_id = norm(r.get("ID"))
        if not original_id:
            continue

        raw_comune = norm(r.get("Comune"))
        raw_provincia = norm(r.get("Provincia"))
        raw_regione = norm(r.get("Regione"))
        location, lat, lon, matched_level, coord_note = resolve_coordinates(raw_comune, raw_provincia, raw_regione, centroids)

        confirm_date = parse_date(r.get("Data conferma"))
        suspect_date = parse_date(r.get("Data sospetto"))
        extinction_date = parse_date(r.get("Data estinzione"))
        tipo = norm(r.get("Tipo focolaio"))
        stato = norm(r.get("Stato sanitario"))
        sierotipo = norm(r.get("Sierotipo")) if "Sierotipo" in df.columns else ""
        species = norm(r.get("Specie")).title() or "Animale"
        species_group = animal_group(species)

        notes = (
            f"Official BENV/IZS table export; disease filter: {disease_it}; original BENV ID {original_id}; "
            f"tipo focolaio: {tipo}; stato sanitario: {stato}; provincia: {raw_provincia}; "
            f"data sospetto: {suspect_date or 'not available'}; data estinzione: {extinction_date or 'not available'}; "
            f"sierotipo: {sierotipo or 'not specified'}; geocoding level: {matched_level}; {coord_note}."
        )

        external_slug = re.sub(r"[^A-Z0-9]+", "-", disease_it.upper()).strip("-")
        species_slug = re.sub(r"[^A-Z0-9]+", "-", species.upper()).strip("-") or "SPECIE"
        year = (confirm_date or suspect_date or "YYYY")[:4]
        rows.append({
            "external_id": f"BENV-{year}-{external_slug}-{original_id}-{species_slug}",
            "source": "IZS_BENV",
            "disease": disease,
            "disease_it": disease_it,
            "diagnosis_status": "Confermato",
            "species": species,
            "animal_group": species_group,
            "observation_date": confirm_date or suspect_date,
            "report_date": confirm_date or suspect_date,
            "country": "Italy",
            "region": raw_regione.title(),
            "location": location,
            "lat": f"{float(lat):.5f}",
            "lon": f"{float(lon):.5f}",
            "url_source": BENV_URL,
            "notes": notes,
        })

        geocode_rows.append({
            "source_file": path.name,
            "benv_id": original_id,
            "raw_comune": raw_comune,
            "raw_provincia": raw_provincia,
            "raw_regione": raw_regione,
            "matched_level": matched_level,
            "matched_label": location,
            "lat": f"{float(lat):.5f}",
            "lon": f"{float(lon):.5f}",
            "note": coord_note,
        })

    return rows, geocode_rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize BENV/IZS XLSX outbreak exports to vet.ector CSV schema")
    ap.add_argument("--input-dir", default="data/raw/benv_exports")
    ap.add_argument("--output", default="data/official_sources/izs_benv_events.csv")
    ap.add_argument("--centroids", default="data/reference/italia_comuni_centroids.csv")
    ap.add_argument("--geocoding-report", default="data/official_sources/benv_geocoding_report.csv")
    ap.add_argument("--disease", default=None, help="Optional disease override for all input files")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    output = Path(args.output)
    geocoding_report = Path(args.geocoding_report)
    centroids = load_centroids(Path(args.centroids))
    files = sorted(input_dir.glob("*.xlsx"))
    all_rows: list[dict] = []
    all_geocode_rows: list[dict] = []
    seen = set()

    for f in files:
        rows, geocode_rows = read_benv_xlsx(f, args.disease, centroids)
        for row in rows:
            if row["external_id"] not in seen:
                seen.add(row["external_id"])
                all_rows.append(row)
        all_geocode_rows.extend(geocode_rows)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    geocoding_report.parent.mkdir(parents=True, exist_ok=True)
    with geocoding_report.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=GEOCODING_REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(all_geocode_rows)

    summary = {
        "output": str(output),
        "records": len(all_rows),
        "input_files": [str(f) for f in files],
        "geocoding_report": str(geocoding_report),
        "geocoding_levels": {},
    }
    for gr in all_geocode_rows:
        lvl = gr.get("matched_level", "unknown")
        summary["geocoding_levels"][lvl] = summary["geocoding_levels"].get(lvl, 0) + 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
