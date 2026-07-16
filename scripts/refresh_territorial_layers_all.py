#!/usr/bin/env python3
from __future__ import annotations
import csv, json
from pathlib import Path
from datetime import datetime, timezone

HEADERS = ["external_id","category","source","label","scientific_name","data_type","count","period_start","period_end","country","region","province","location","lat","lon","radius_km","color","url_source","notes"]
BASE = Path("data/territorial_layers")
OUT = BASE / "territorial_layers.csv"
STATUS = BASE / "refresh_status.json"
SOURCE_FILES = [
    BASE / "mosquito_alert_layers.csv",
    BASE / "vectornet_gbif_layers.csv",
    BASE / "west_nile_surveillance.csv",
    BASE / "esccap_parasites.csv",
]

def read_rows(path: Path):
    if not path.exists():
        return []
    rows=[]
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames:
            return []
        for row in reader:
            if not any((v or "").strip() for v in row.values()):
                continue
            rows.append({h: (row.get(h, "") or "").strip() for h in HEADERS})
    return rows

def main():
    BASE.mkdir(parents=True, exist_ok=True)
    all_rows=[]
    status={"version":"v148-curated-vector-preserving-refresh","generated_at":datetime.now(timezone.utc).isoformat(),"sources":[]}
    seen=set()
    for src in SOURCE_FILES:
        rows=read_rows(src)
        status["sources"].append({"path":str(src),"rows":len(rows),"exists":src.exists()})
        for r in rows:
            eid=r.get("external_id") or f"AUTO-{len(all_rows)+1}"
            if eid in seen:
                continue
            seen.add(eid)
            r["external_id"]=eid
            all_rows.append(r)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer=csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(all_rows)
    status["rows_total"]=len(all_rows)
    counts={}
    for r in all_rows:
        counts[r.get("category","")]=counts.get(r.get("category",""),0)+1
    status["categories"]=counts
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(status)

if __name__ == "__main__":
    main()
