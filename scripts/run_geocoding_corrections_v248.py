#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

STEPS = [
    ("build_comuni_reference", "scripts/build_comuni_reference_v246.py", False),
    ("fix_official_events_geocoding", "scripts/fix_official_events_geocoding_v245.py", True),
    ("fix_territorial_layers_geocoding", "scripts/fix_territorial_layers_geocoding_v247.py", True),
    ("normalize_territorial_layers", "scripts/normalize_territorial_layers_radius_v232.py", True),
]

def run_step(name: str, script: str, required: bool):
    path = Path(script)
    if not path.exists():
        status = {"name": name, "script": script, "status": "missing", "required": required}
        if required:
            status["error"] = f"Required script not found: {script}"
        return status
    p = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=3600)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    parsed = None
    if out:
        try:
            parsed = json.loads(out)
        except Exception:
            parsed = None
    return {
        "name": name,
        "script": script,
        "status": "success" if p.returncode == 0 else "error",
        "returncode": p.returncode,
        "stdout_json": parsed,
        "stdout_tail": out[-3000:],
        "stderr_tail": err[-3000:],
        "required": required,
    }

def main():
    started = datetime.now(timezone.utc).isoformat()
    results = []
    overall = "success"
    for name, script, required in STEPS:
        result = run_step(name, script, required)
        results.append(result)
        if result.get("status") == "error" or (required and result.get("status") == "missing"):
            overall = "error"
            break
    print(json.dumps({
        "status": overall,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "steps": results,
        "notes": "Run official sync endpoints after this if corrected official CSVs changed. Commit corrected CSVs before deploy, or run this on Render after deploy if sources are available there."
    }, ensure_ascii=False, indent=2))
    return 0 if overall == "success" else 1

if __name__ == "__main__":
    raise SystemExit(main())
