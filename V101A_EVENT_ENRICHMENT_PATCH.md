# v101A event_enrichment.py patch: add sentinel status

Add this logic to `enrich_public_event(event)` before the generic suspect/user logic.

```python
source = str(event.get("source") or "").upper()
source_type = str(event.get("source_type") or "").lower()
report_type = str(event.get("report_type") or "").lower()
status = str(event.get("diagnosis_status") or "").lower()

if source == "MYVBDMAP" or source_type == "sentinel" or report_type == "veterinary_sentinel" or "sentinella" in status:
    event["display_status"] = "Dato sentinella"
    event["display_source"] = "MyVBDMap" if source == "MYVBDMAP" else (event.get("source") or "Dato sentinella")
    event["confidence_label"] = "Dato epidemiologico veterinario"
    event["confidence_rank"] = 3
    event["is_demo"] = False
    event["is_official"] = False
    event["is_user_generated"] = False
    event["is_vet_validated"] = False
    event["is_rapid_test"] = False
    event["is_suspect"] = False
    event["is_sentinel"] = True
    return event
```

For BENV/IZS events, no special enrichment is needed if BENV is inserted as:

```text
source = IZS_BENV
source_type = official
report_type = official_confirmed
diagnosis_status = Confermato
```

The backend should classify these as `Confermato ufficiale`.
