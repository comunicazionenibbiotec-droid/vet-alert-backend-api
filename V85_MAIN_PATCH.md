# vet.ector backend v85 - main.py patch notes

This package intentionally avoids overwriting your `main.py`, because your current backend is running correctly.

## Files to add/replace

Copy this file into the backend repository:

```text
backend/sync/deduplicator.py
```

If your Render service uses repository root rather than `backend/` as Root Directory, place it here instead:

```text
sync/deduplicator.py
```

## Why this patch

The previous deduplication was a little too aggressive for `user` and `demo` events. v85 changes the rules:

- official + official = can be merged
- official + user/demo/test/vet = merged only if same disease/species and very close in time/location
- user + user = never merged
- demo + demo = never merged

This prevents multiple nearby user/demo cases from being collapsed into one map event.

## Optional endpoint to add to main.py

If you want a clearer sync status endpoint, add this snippet near your other sync endpoints:

```python
@app.get("/sync/summary")
def sync_summary(limit: int = 20):
    try:
        logs = get_sync_log(limit=limit)
    except TypeError:
        logs = get_sync_log()
    except Exception:
        logs = []

    latest_by_source = {}
    for item in logs:
        try:
            source = item.get("source", "unknown")
        except AttributeError:
            source = "unknown"
        if source not in latest_by_source:
            latest_by_source[source] = item

    return {
        "status": "ok",
        "version": APP_VERSION if "APP_VERSION" in globals() else "unknown",
        "sync_interval_hours": SYNC_INTERVAL_HOURS if "SYNC_INTERVAL_HOURS" in globals() else None,
        "sources": latest_by_source,
        "log_count": len(logs),
    }
```

If your `main.py` stores logs in a different function/table, leave this endpoint out for now. `/sync/log` and `/sync/adis/status` are already working.

## Test after deploy

```text
https://vet-alert-api-v2.onrender.com/health
https://vet-alert-api-v2.onrender.com/sync/log?limit=10
https://vet-alert-api-v2.onrender.com/sync/adis/status
https://vet-alert-api-v2.onrender.com/events?lat=44.3845&lon=7.5427&radius_km=100&days=365&animal_filter=ovine
```

Expected behavior:

- ovine events must not return bovine records;
- user/demo events should normally show `duplicate_count: 1` unless merged with an official event;
- official WAHIS/ADIS events describing the same outbreak can still merge.
