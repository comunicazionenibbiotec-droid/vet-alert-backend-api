#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Optionally trigger a vet.ector backend sync endpoint after data refresh/deploy")
    ap.add_argument("--enabled", default=os.getenv("VETECTOR_BACKEND_SYNC_ENABLED", "false"))
    ap.add_argument("--base-url", default=os.getenv("VETECTOR_BACKEND_BASE_URL", "https://vet-alert-api-v2.onrender.com"))
    ap.add_argument("--endpoint", default="/sync/izs-benv/run")
    ap.add_argument("--status-output", default="data/official_sources/backend_sync_status.json")
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--sleep", type=int, default=20)
    args = ap.parse_args()

    status: dict[str, Any] = {
        "version": "v161-backend-sync-trigger",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "enabled": truthy(args.enabled),
        "base_url": args.base_url,
        "endpoint": args.endpoint,
        "attempts": [],
        "final_status": "skipped",
    }

    output = Path(args.status_output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if not truthy(args.enabled):
        status["message"] = "Backend sync disabled. Set repository variable VETECTOR_BACKEND_SYNC_ENABLED=true to enable."
        output.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    base = args.base_url.rstrip("/")
    endpoint = args.endpoint if args.endpoint.startswith("/") else "/" + args.endpoint
    url = base + endpoint
    token = os.getenv("VETECTOR_BACKEND_SYNC_TOKEN", "").strip()
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(1, max(args.retries, 1) + 1):
        item: dict[str, Any] = {"attempt": attempt, "url": url, "started_at": datetime.now(timezone.utc).isoformat()}
        try:
            response = requests.post(url, headers=headers, timeout=args.timeout)
            item["http_status"] = response.status_code
            item["response_text"] = response.text[:4000]
            item["ok"] = response.ok
            status["attempts"].append(item)
            if response.ok:
                status["final_status"] = "success"
                output.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(status, ensure_ascii=False, indent=2))
                return 0
        except Exception as exc:
            item["ok"] = False
            item["error"] = str(exc)
            status["attempts"].append(item)
        if attempt < args.retries:
            time.sleep(args.sleep)

    status["final_status"] = "error"
    output.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    sys.exit(main())
