#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

REQUIRED = {"id", "type", "section", "name_it"}
ALLOWED_SECTIONS = {"patologie", "vettori", "parassiti", "west_nile"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file", nargs="?", default="public_html/data/diseases.json")
    args = ap.parse_args()
    path = Path(args.json_file)
    data = json.loads(path.read_text(encoding="utf-8"))
    diseases = data.get("diseases", [])
    if not isinstance(diseases, list) or not diseases:
        print(f"ERROR {path}: missing or empty diseases array")
        return 1
    ids = set()
    errors = []
    for i, item in enumerate(diseases, start=1):
        missing = REQUIRED - set(item)
        if missing:
            errors.append(f"row {i}: missing {sorted(missing)}")
        if item.get("id") in ids:
            errors.append(f"row {i}: duplicate id {item.get('id')}")
        ids.add(item.get("id"))
        if item.get("section") not in ALLOWED_SECTIONS:
            errors.append(f"row {i}: invalid section {item.get('section')}")
    section_keys = {s.get("key") for s in data.get("sections", []) if isinstance(s, dict)}
    missing_sections = ALLOWED_SECTIONS - section_keys
    if missing_sections:
        errors.append(f"missing sections: {sorted(missing_sections)}")
    if errors:
        for e in errors:
            print("ERROR", e)
        return 1
    counts = {}
    for item in diseases:
        counts[item["section"]] = counts.get(item["section"], 0) + 1
    print(f"OK {path}: {len(diseases)} entries; sections={counts}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
