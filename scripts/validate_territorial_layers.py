#!/usr/bin/env python3
from __future__ import annotations
import csv, sys, pathlib
REQUIRED=["external_id","category","source","label","lat","lon"]
ALLOWED={"vectors","parasites","west_nile"}

def main(path):
    p=pathlib.Path(path)
    errors=[]
    if not p.exists():
        print(f"MISSING {p}")
        return 1
    with p.open(newline="",encoding="utf-8-sig") as f:
        rows=list(csv.DictReader(f))
    for col in REQUIRED:
        if col not in (rows[0].keys() if rows else csv.DictReader(p.open(encoding="utf-8-sig")).fieldnames or []):
            errors.append(f"missing column {col}")
    for i,row in enumerate(rows, start=2):
        for col in REQUIRED:
            if not str(row.get(col,"")).strip(): errors.append(f"line {i}: missing {col}")
        if row.get("category") and row["category"].strip().lower() not in ALLOWED:
            errors.append(f"line {i}: invalid category {row['category']}")
        for col in ("lat","lon"):
            try: float(row.get(col,""))
            except Exception: errors.append(f"line {i}: invalid {col}")
    if errors:
        print("INVALID territorial_layers.csv")
        for e in errors[:100]: print("-",e)
        return 1
    print(f"OK territorial_layers.csv rows={len(rows)}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv)>1 else "data/territorial_layers/territorial_layers.csv"))
