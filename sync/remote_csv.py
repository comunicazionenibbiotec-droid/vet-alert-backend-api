from __future__ import annotations

import os
import time
import urllib.request
from pathlib import Path
from typing import Optional


def is_truthy(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def download_text(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "vet.ector/1.0 official-source-sync (+https://vet.ector.nibbiotec.com)",
            "Accept": "text/csv, text/plain, application/csv, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def save_snapshot(prefix: str, text: str, snapshot_dir: str = "data/source_snapshots") -> Optional[str]:
    if not is_truthy(os.getenv("SAVE_SOURCE_SNAPSHOTS"), default=False):
        return None
    path = Path(snapshot_dir)
    path.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    file_path = path / f"{prefix}-{stamp}.csv"
    file_path.write_text(text, encoding="utf-8")
    return str(file_path)
