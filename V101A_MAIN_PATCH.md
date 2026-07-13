# v101A main.py patch: BENV/IZS + MyVBDMap backend connectors

Apply these changes to `main.py`.

## 1. Add imports near existing connector imports

```python
from sync.izs_benv_csv_connector import IzsBenvCsvConnector
from sync.myvbdmap_csv_connector import MyVbdMapCsvConnector
```

## 2. Add sync functions after `sync_adis_events()`

```python
def sync_izs_benv_events():
    c = IzsBenvCsvConnector()
    return _sync_rows(c.source_name, c.fetch(), "IZS_BENV")


def sync_myvbdmap_events():
    c = MyVbdMapCsvConnector()
    started = now_iso()
    ins = upd = skip = 0
    rows = c.fetch()
    for row in rows:
        try:
            row["source"] = row.get("source") or "MYVBDMAP"
            row["source_type"] = row.get("source_type") or "sentinel"
            row["report_type"] = row.get("report_type") or "veterinary_sentinel"
            row["diagnosis_status"] = row.get("diagnosis_status") or "Dato sentinella"
            r = upsert_event(row)
            ins += r == "inserted"
            upd += r == "updated"
        except Exception as e:
            skip += 1
            print("Skipped MyVBDMap sentinel event", e)
    log_sync(c.source_name, "success", f"{c.source_name} sync completed; skipped={skip}", len(rows), ins, upd, started)
    return {"status": "success", "source": c.source_name, "received": len(rows), "inserted": ins, "updated": upd, "skipped": skip}
```

## 3. Add startup sync calls

In `startup()`, after ADIS sync, add:

```python
sync_izs_benv_events()
sync_myvbdmap_events()
```

In the scheduler, add:

```python
scheduler.add_job(sync_izs_benv_events, "interval", hours=SYNC_INTERVAL_HOURS, id="izs_benv_csv_sync", replace_existing=True)
scheduler.add_job(sync_myvbdmap_events, "interval", hours=SYNC_INTERVAL_HOURS, id="myvbdmap_csv_sync", replace_existing=True)
```

## 4. Add endpoints near the other sync endpoints

```python
@app.post("/sync/izs-benv/run")
def run_izs_benv_sync():
    return sync_izs_benv_events()


@app.get("/sync/izs-benv/status")
def get_izs_benv_status():
    with connect() as conn:
        row = conn.execute("SELECT * FROM sync_log WHERE source LIKE 'IZS_BENV%' ORDER BY id DESC LIMIT 1").fetchone()
    return {"status": "never_run" if row is None else "ok", "last_sync": None if row is None else dict(row)}


@app.post("/sync/myvbdmap/run")
def run_myvbdmap_sync():
    return sync_myvbdmap_events()


@app.get("/sync/myvbdmap/status")
def get_myvbdmap_status():
    with connect() as conn:
        row = conn.execute("SELECT * FROM sync_log WHERE source LIKE 'MYVBDMAP%' ORDER BY id DESC LIMIT 1").fetchone()
    return {"status": "never_run" if row is None else "ok", "last_sync": None if row is None else dict(row)}
```

## 5. Update `/sync/all/run`

Add these entries:

```python
"izs_benv": sync_izs_benv_events(),
"myvbdmap": sync_myvbdmap_events(),
```

## 6. Update `/sync/status`

Add these sources:

```python
"IZS_BENV_CSV", "MYVBDMAP_CSV"
```

## 7. Optional: update app version

```python
app = FastAPI(title="vet.ector Veterinary Alert API", version="2.2.0-italy-sources-v101A")
```
