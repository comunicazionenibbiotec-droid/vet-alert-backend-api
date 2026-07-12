# vet.ector backend v86 - Demo control patch for `main.py`

This patch keeps demo data visible during the prototype phase, but allows them to be hidden or purged when the product moves to a real pilot/public launch.

## 1. Add import near the other imports in `main.py`

```python
try:
    from sync.demo_control import (
        show_demo_events,
        auto_populate_demo_365,
        filter_demo_events,
        demo_status,
        purge_demo_events_sqlite,
    )
except Exception:
    # Safe fallback: never break backend startup if demo_control is missing.
    def show_demo_events(): return True
    def auto_populate_demo_365(): return True
    def filter_demo_events(events): return list(events)
    def demo_status(): return {"show_demo_events": True, "auto_populate_demo_365": True}
    def purge_demo_events_sqlite(conn, table_name="events", older_than_days=None):
        return {"status": "disabled", "deleted": 0}
```

## 2. Use `auto_populate_demo_365()` where demo records are generated

If `main.py` currently reads an environment variable directly, keep it. If it uses a constant, replace it with:

```python
AUTO_POPULATE_DEMO_365 = auto_populate_demo_365()
```

This keeps the current prototype behaviour by default, because `AUTO_POPULATE_DEMO_365` defaults to `true`.

## 3. Filter demo events in public event endpoints

In endpoints such as:

```python
GET /events
GET /official-events
GET /events/export
```

before returning events to the client, add:

```python
events = filter_demo_events(events)
```

Example:

```python
return {"count": len(events), "events": events}
```

should become:

```python
events = filter_demo_events(events)
return {"count": len(events), "events": events}
```

When `SHOW_DEMO_EVENTS=true`, nothing changes.
When `SHOW_DEMO_EVENTS=false`, records with source `Demo 365 giorni` or other demo markers are hidden.

## 4. Add endpoint `GET /demo/status`

Add this near the other status endpoints:

```python
@app.get("/demo/status")
def get_demo_status():
    return demo_status()
```

## 5. Add endpoint `POST /demo/purge`

Use this only when you want to remove old demo records. The exact database connection name in your `main.py` may differ; adapt `get_db_connection()` if necessary.

```python
@app.post("/demo/purge")
def post_demo_purge(older_than_days: int | None = None):
    # Replace get_db_connection() with your current SQLite connection helper.
    conn = get_db_connection()
    try:
        return purge_demo_events_sqlite(conn, table_name="events", older_than_days=older_than_days)
    finally:
        try:
            conn.close()
        except Exception:
            pass
```

If your table is not called `events`, change `table_name` to the correct table name.

## 6. Render environment variables

For the current prototype:

```text
SHOW_DEMO_EVENTS=true
AUTO_POPULATE_DEMO_365=true
PURGE_DEMO_OLDER_THAN_DAYS=365
```

For the public/pilot release:

```text
SHOW_DEMO_EVENTS=false
AUTO_POPULATE_DEMO_365=false
PURGE_DEMO_OLDER_THAN_DAYS=365
```

## 7. Test after deploy

```text
https://vet-alert-api-v2.onrender.com/demo/status
https://vet-alert-api-v2.onrender.com/events?lat=44.3845&lon=7.5427&radius_km=100&days=365&animal_filter=ovine
```

With `SHOW_DEMO_EVENTS=true`, demo records remain visible.
With `SHOW_DEMO_EVENTS=false`, demo records disappear from `/events`.
