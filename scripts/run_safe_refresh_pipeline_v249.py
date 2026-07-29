#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

MODES = {"light", "territorial", "heavy", "full"}

def run_script(name: str, script: str, timeout: int = 3600, required: bool = True):
    path = Path(script)
    if not path.exists():
        return {"name": name, "script": script, "status": "missing", "required": required}
    p = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=timeout)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    parsed = None
    if out:
        try:
            parsed = json.loads(out)
        except Exception:
            pass
    return {
        "name": name,
        "script": script,
        "status": "success" if p.returncode == 0 else "error",
        "returncode": p.returncode,
        "stdout_json": parsed,
        "stdout_tail": out[-3500:],
        "stderr_tail": err[-3500:],
        "required": required,
    }

def local_plan(mode: str):
    # This script handles file-based corrections only. Database reload and connector syncs are done by main.py endpoint.
    steps = []
    if mode in {"light", "full", "territorial", "heavy"}:
        steps.append(("build_comuni_reference", "scripts/build_comuni_reference_v246.py", 1200, False))
        steps.append(("fix_official_events_geocoding", "scripts/fix_official_events_geocoding_v245.py", 1800, True))
        steps.append(("fix_territorial_layers_geocoding", "scripts/fix_territorial_layers_geocoding_v247.py", 1800, True))
        steps.append(("normalize_territorial_layers", "scripts/normalize_territorial_layers_radius_v232.py", 900, True))
    return steps

def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "light").strip().lower()
    if mode not in MODES:
        print(json.dumps({"status":"error","message":f"Invalid mode {mode}. Allowed: {sorted(MODES)}"}, indent=2))
        return 2
    started = datetime.now(timezone.utc).isoformat()
    results = []
    overall = "success"
    for name, script, timeout, required in local_plan(mode):
        result = run_script(name, script, timeout=timeout, required=required)
        results.append(result)
        if result.get("status") == "error" or (required and result.get("status") == "missing"):
            overall = "error"
            break
    print(json.dumps({
        "status": overall,
        "mode": mode,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "steps": results
    }, ensure_ascii=False, indent=2))
    return 0 if overall == "success" else 1

if __name__ == "__main__":
    raise SystemExit(main())
