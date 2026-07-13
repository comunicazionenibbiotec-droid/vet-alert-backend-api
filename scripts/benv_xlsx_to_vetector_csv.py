#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, re, sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple, Optional
import pandas as pd

OUTPUT_COLUMNS = [
    "external_id","source","disease","disease_it","diagnosis_status","species","animal_group",
    "observation_date","report_date","country","region","location","lat","lon","url_source","notes"
]

BENV_URL = "https://www.izs.it/BENV_NEW/datiemappe.html"

DISEASE_MAP = {
    "leishmaniosi": ("Leishmaniosis", "Leishmaniosi"),
    "leishmania": ("Leishmaniosis", "Leishmaniosi"),
    "west_nile": ("West Nile Fever", "West Nile Fever"),
    "west nile": ("West Nile Fever", "West Nile Fever"),
    "rabbia": ("Rabies", "Rabbia"),
    "rabies": ("Rabies", "Rabbia"),
    "influenza_aviaria": ("Highly pathogenic avian influenza", "Influenza aviaria ad alta patogenicita"),
    "hpaI": ("Highly pathogenic avian influenza", "Influenza aviaria ad alta patogenicita"),
    "blue tongue": ("Bluetongue", "Bluetongue"),
    "bluetongue": ("Bluetongue", "Bluetongue"),
    "peste_suina_africana": ("African swine fever", "Peste suina africana"),
    "psa": ("African swine fever", "Peste suina africana"),
    "tubercolosi": ("Mycobacterium tuberculosis complex", "Tubercolosi bovina / MTBC"),
    "leucosi": ("Enzootic bovine leukosis", "Leucosi bovina enzootica"),
}

ANIMAL_GROUP_MAP = {
    "CANE": "dog", "CANI": "dog", "DOG": "dog",
    "GATTO": "cat", "GATTI": "cat", "CAT": "cat",
    "BOVINO": "bovine", "BOVINI": "bovine", "BUFALO": "bovine", "CATTLE": "bovine",
    "SUINO": "swine", "SUINI": "swine", "CINGHIALE": "swine", "CINGHIALI": "swine", "SWINE": "swine",
    "OVINO": "ovine", "OVINI": "ovine", "SHEEP": "ovine",
    "CAPRINO": "caprine", "CAPRINI": "caprine", "GOAT": "caprine",
    "EQUINO": "equine", "EQUINI": "equine", "HORSE": "equine",
    "AVICOLI": "poultry", "VOLATILI": "poultry", "POLLAME": "poultry", "BIRDS": "poultry",
    "API": "bees", "APE": "bees", "BEES": "bees",
}

REGION_CAPITALS = {
    "ABRUZZO": ("L'Aquila", 42.3498, 13.3995), "BASILICATA": ("Potenza", 40.6404, 15.8056),
    "CALABRIA": ("Catanzaro", 38.9098, 16.5877), "CAMPANIA": ("Napoli", 40.8518, 14.2681),
    "EMILIA-ROMAGNA": ("Bologna", 44.4949, 11.3426), "FRIULI-VENEZIA GIULIA": ("Trieste", 45.6495, 13.7768),
    "LAZIO": ("Roma", 41.9028, 12.4964), "LIGURIA": ("Genova", 44.4056, 8.9463),
    "LOMBARDIA": ("Milano", 45.4642, 9.1900), "MARCHE": ("Ancona", 43.6158, 13.5189),
    "MOLISE": ("Campobasso", 41.5603, 14.6627), "PIEMONTE": ("Torino", 45.0703, 7.6869),
    "PUGLIA": ("Bari", 41.1171, 16.8719), "SARDEGNA": ("Cagliari", 39.2238, 9.1217),
    "SICILIA": ("Palermo", 38.1157, 13.3615), "TOSCANA": ("Firenze", 43.7696, 11.2558),
    "TRENTINO-ALTO ADIGE": ("Trento", 46.0748, 11.1217), "UMBRIA": ("Perugia", 43.1107, 12.3908),
    "VALLE D'AOSTA": ("Aosta", 45.7370, 7.3201), "VENETO": ("Venezia", 45.4408, 12.3155),
}

# Fallback for municipalities already encountered in initial BENV tests.
LOCAL_CENTROIDS = {
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

def norm(s) -> str:
    return str(s or "").strip()

def key(s) -> str:
    return norm(s).upper()

def parse_date(value) -> str:
    if value is None or pd.isna(value) or norm(value) in {"", "-"}:
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

def infer_disease(path: Path, override: Optional[str]) -> Tuple[str, str, str]:
    raw = override or path.stem
    raw_l = raw.lower().replace("-", "_")
    for k, val in DISEASE_MAP.items():
        if k.lower().replace(" ", "_") in raw_l:
            return val[0], val[1], val[1]
    cleaned = raw.replace("_", " ").replace("-", " ").strip().title()
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
                lat = float(r.get("lat") or r.get("latitude"))
                lon = float(r.get("lon") or r.get("lng") or r.get("longitude"))
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

def read_benv_xlsx(path: Path, disease_override: Optional[str], centroids) -> list[dict]:
    disease, disease_it, disease_slug = infer_disease(path, disease_override)
    df = pd.read_excel(path, sheet_name=0, engine="openpyxl")
    rows = []
    required = {"ID", "Tipo focolaio", "Stato sanitario", "Data conferma", "Data sospetto", "Data estinzione", "Specie", "Comune", "Provincia", "Regione"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing columns: {sorted(missing)}")
    for _, r in df.iterrows():
        original_id = norm(r.get("ID"))
        if not original_id:
            continue
        comune_key = key(r.get("Comune"))
        provincia = key(r.get("Provincia"))
        regione_key = key(r.get("Regione"))
        location, lat, lon = centroids.get((comune_key, provincia), (None, None, None))
        coord_note = "coordinates approximated at municipality centroid"
        if not location:
            cap = REGION_CAPITALS.get(regione_key)
            if cap:
                location, lat, lon = cap
                coord_note = "municipality centroid unavailable; coordinates set to regional capital for map display"
            else:
                location, lat, lon = norm(r.get("Comune")) or norm(r.get("Regione")), "", ""
                coord_note = "coordinates unavailable"
        confirm_date = parse_date(r.get("Data conferma"))
        suspect_date = parse_date(r.get("Data sospetto"))
        extinction_date = parse_date(r.get("Data estinzione"))
        tipo = norm(r.get("Tipo focolaio"))
        stato = norm(r.get("Stato sanitario"))
        sierotipo = norm(r.get("Sierotipo")) if "Sierotipo" in df.columns else ""
        species = norm(r.get("Specie")).title() or "Animale"
        notes = (
            f"Official BENV/IZS table export; disease filter: {disease_it}; original BENV ID {original_id}; "
            f"tipo focolaio: {tipo}; stato sanitario: {stato}; provincia: {provincia}; "
            f"data sospetto: {suspect_date or 'not available'}; data estinzione: {extinction_date or 'not available'}; "
            f"sierotipo: {sierotipo or 'not specified'}; {coord_note}."
        )
        rows.append({
            "external_id": f"BENV-{confirm_date[:4] or 'YYYY'}-{re.sub(r'[^A-Z0-9]+','-', disease_it.upper()).strip('-')}-{original_id}",
            "source": "IZS_BENV",
            "disease": disease,
            "disease_it": disease_it,
            "diagnosis_status": "Confermato",
            "species": species,
            "animal_group": animal_group(species),
            "observation_date": confirm_date or suspect_date,
            "report_date": confirm_date or suspect_date,
            "country": "Italy",
            "region": norm(r.get("Regione")).title(),
            "location": location,
            "lat": f"{float(lat):.5f}" if lat not in (None, "") else "",
            "lon": f"{float(lon):.5f}" if lon not in (None, "") else "",
            "url_source": BENV_URL,
            "notes": notes,
        })
    return rows

def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize BENV/IZS XLSX outbreak exports to vet.ector CSV schema")
    ap.add_argument("--input-dir", default="data/raw/benv_exports")
    ap.add_argument("--output", default="data/official_sources/izs_benv_events.csv")
    ap.add_argument("--centroids", default="data/reference/italia_comuni_centroids.csv")
    ap.add_argument("--disease", default=None, help="Optional disease override for all input files")
    args = ap.parse_args()
    input_dir = Path(args.input_dir)
    output = Path(args.output)
    centroids = load_centroids(Path(args.centroids))
    files = sorted(input_dir.glob("*.xlsx"))
    all_rows = []
    seen = set()
    for f in files:
        for row in read_benv_xlsx(f, args.disease, centroids):
            if row["external_id"] not in seen:
                seen.add(row["external_id"])
                all_rows.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)
    print(json.dumps({"output": str(output), "records": len(all_rows), "input_files": [str(f) for f in files]}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
