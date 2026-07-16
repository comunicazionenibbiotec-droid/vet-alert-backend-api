#!/usr/bin/env python3
"""Trigger a backend sync endpoint and write a status JSON file.

Designed for GitHub Actions. By default failures return a non-zero exit code.
Use --non-blocking to record failures but keep the workflow green.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--endpoint", default="/sync/izs-benv/run")
    parser.add_argument("--output", default="data/official_sources/benv_backend_sync_status.json")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--non-blocking", action="store_true")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    endpoint = args.endpoint if args.endpoint.startswith("/") else f"/{args.endpoint}"
    url = f"{base}{endpoint}"

    status = {
        "version": "v162-benv-robust-refresh",
        "started_at": now_iso(),
        "backend_base_url": base,
        "endpoint": endpoint,
        "url": url,
        "status": "pending",
        "http_status": None,
        "response_preview": None,
        "error": None,
        "finished_at": None,
    }

    exit_code = 0
    try:
        response = requests.post(url, timeout=args.timeout)
        status["http_status"] = response.status_code
        status["response_preview"] = response.text[:2000]
        if 200 <= response.status_code < 300:
            status["status"] = "success"
        else:
            status["status"] = "error"
            status["error"] = f"non_2xx_http_status_{response.status_code}"
            exit_code = 1
    except Exception as exc:  # noqa: BLE001
        status["status"] = "error"
        status["error"] = repr(exc)
        exit_code = 1
    finally:
        status["finished_at"] = now_iso()
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(status, indent=2, ensure_ascii=False))

    if args.non_blocking and exit_code != 0:
        print("WARNING: backend sync failed, but --non-blocking is enabled; continuing.")
        return 0
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
