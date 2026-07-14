# v138 main.py patch - ESCCAP / parasites territorial import

This patch adds ESCCAP as a curated parasite territorial layer source.
It does not scrape ESCCAP automatically. Use a curated or authorised CSV.

## 1. Add import near the other territorial imports

```python
from sync.esccap_connector import EsccapConnector
```

## 2. Add sync function near the other territorial layer sync functions

```python
def sync_esccap_layers():
    started = now_iso()
    try:
        from sync.territorial_layers_connector import replace_source_rows
        rows = EsccapConnector().fetch()
        replaced = replace_source_rows("ESCCAP", rows)
        log_sync("ESCCAP_CSV", "success", f"ESCCAP territorial layer sync completed; rows={len(rows)}", len(rows), replaced.get("inserted", len(rows)), replaced.get("updated", 0), started)
        return {"status": "success", "source": "ESCCAP", "received": len(rows), **replaced}
    except Exception as e:
        log_sync("ESCCAP_CSV", "error", str(e), 0, 0, 0, started)
        raise
```

If your `territorial_layers_connector.py` does not expose `replace_source_rows`, use the script-based fallback:

```python
def sync_esccap_layers():
    started = now_iso()
    import subprocess, sys
    p = subprocess.run([sys.executable, "scripts/build_esccap_layers.py"], capture_output=True, text=True)
    if p.returncode != 0:
        log_sync("ESCCAP_CSV", "error", p.stderr or p.stdout, 0, 0, 0, started)
        raise HTTPException(status_code=500, detail=p.stderr or p.stdout)
    rows = EsccapConnector().fetch()
    log_sync("ESCCAP_CSV", "success", "ESCCAP territorial layer sync completed", len(rows), len(rows), 0, started)
    return {"status": "success", "source": "ESCCAP", "received": len(rows), "message": p.stdout}
```

## 3. Add endpoints

```python
@app.post("/sync/territorial-layers/esccap/run")
def run_esccap_layer_sync():
    return sync_esccap_layers()

@app.get("/sync/territorial-layers/esccap/status")
def get_esccap_layer_status():
    with connect() as conn:
        row = conn.execute("SELECT * FROM sync_log WHERE source='ESCCAP_CSV' ORDER BY id DESC LIMIT 1").fetchone()
    return {"status": "never_run" if row is None else "ok", "last_sync": None if row is None else dict(row)}
```

## 4. Update `/sources/registry`

Add:

```python
{
    "id": "ESCCAP",
    "name": "ESCCAP Parasite Infection Maps",
    "type": "territorial_layer",
    "category": "parasites",
    "status": "curated_csv",
    "notes": "Positive-test percentages among screened pets; not true population prevalence. Use only authorised/verified aggregate rows."
}
```

## 5. Optional environment variables

```text
ESCCAP_CSV_PATH=data/territorial_layers/esccap_parasites.csv
ESCCAP_REMOTE_CSV_URL=https://...
ESCCAP_TIMEOUT_SECONDS=30
```
