from __future__ import annotations

from typing import Any, Dict, Iterable, List

REAL_OFFICIAL_SOURCES = {"WAHIS", "WAHIS_CSV", "WAHIS_CSV_UPLOAD", "ADIS", "ADIS_CSV", "WOAH"}
DEMO_SOURCES = {"Demo 365 giorni", "OFFICIAL_DEMO", "DEMO", "seed_demo"}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _norm(value).lower()


def _merged_sources(event: Dict[str, Any]) -> List[str]:
    sources = event.get("sources_merged")
    if isinstance(sources, list) and sources:
        return [str(s).strip() for s in sources if str(s).strip()]
    source = _norm(event.get("source"))
    return [source] if source else []


def _is_demo_source(source: str) -> bool:
    if not source:
        return False
    source_l = source.lower()
    return "demo" in source_l or source in DEMO_SOURCES


def _is_real_official_source(source: str) -> bool:
    if not source:
        return False
    source_l = source.lower()
    if _is_demo_source(source):
        return False
    return source in REAL_OFFICIAL_SOURCES or "adis" in source_l or "wahis" in source_l or "woah" in source_l


def _display_source(event: Dict[str, Any]) -> str:
    sources = _merged_sources(event)
    if not sources:
        return "Fonte non indicata"

    display: List[str] = []
    for src in sources:
        src_l = src.lower()
        if _is_real_official_source(src) and ("wahis" in src_l or "woah" in src_l or src in ("WAHIS", "WAHIS_CSV", "WAHIS_CSV_UPLOAD")):
            label = "WAHIS"
        elif _is_real_official_source(src) and ("adis" in src_l or src in ("ADIS", "ADIS_CSV")):
            label = "ADIS"
        elif "veterin" in src_l or src_l == "vet":
            label = "Veterinario"
        elif "rapid" in src_l or "leggi test" in src_l or "test" in src_l:
            label = "Leggi test rapido"
        elif _is_demo_source(src):
            label = "Demo"
        elif "user" in src_l or "utente" in src_l:
            label = "Utente"
        elif "company" in src_l or "azienda" in src_l:
            label = "Azienda"
        elif "association" in src_l or "associazione" in src_l:
            label = "Associazione"
        else:
            label = src
        if label not in display:
            display.append(label)

    return " + ".join(display)


def enrich_public_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Add frontend-friendly status/source/confidence fields to a public event.

    In v99, real official sources always take precedence over demo labels if a merged
    event contains both. The deduplicator should normally prevent official+demo merges,
    but this priority makes the response robust.
    """
    item = dict(event)

    source = _norm(item.get("source"))
    source_l = source.lower()
    source_type = _lower(item.get("source_type"))
    report_type = _lower(item.get("report_type"))
    diagnosis_status = _lower(item.get("diagnosis_status"))
    merged_sources = _merged_sources(item)

    has_real_official_source = any(_is_real_official_source(s) for s in merged_sources) or _is_real_official_source(source)
    has_demo_source = any(_is_demo_source(s) for s in merged_sources) or _is_demo_source(source)

    is_official = bool(
        has_real_official_source
        or (
            source_type == "official"
            and not has_demo_source
            and "official_demo" not in source_l
        )
        or ("official" in report_type and not has_demo_source)
    )
    is_demo = bool(has_demo_source and not is_official)

    is_vet_validated = (
        "vet" in report_type
        or "veterin" in report_type
        or "vet" in source_type
        or "veterin" in source_l
        or "validato" in diagnosis_status
        or "validated" in diagnosis_status
    )
    is_rapid_test = (
        "positive" in report_type
        or "rapid" in report_type
        or "test" in report_type
        or "test rapido" in diagnosis_status
        or ("positivo" in diagnosis_status and "test" in diagnosis_status)
        or "leggi test" in source_l
    )
    is_suspect = (
        "suspect" in report_type
        or "sosp" in diagnosis_status
        or "segnalato" in diagnosis_status
        or source_type in {"user", "company", "association"}
    )

    if is_official:
        display_status = "Confermato ufficiale"
        confidence_label = "Affidabilita alta"
        confidence_rank = 5
    elif is_vet_validated:
        display_status = "Validato da veterinario"
        confidence_label = "Affidabilita professionale"
        confidence_rank = 4
    elif is_rapid_test:
        display_status = "Test rapido positivo"
        confidence_label = "Affidabilita intermedia"
        confidence_rank = 3
    elif is_suspect:
        display_status = "Sospetto"
        confidence_label = "Da confermare"
        confidence_rank = 2
    elif is_demo:
        display_status = "Demo"
        confidence_label = "Dato dimostrativo temporaneo"
        confidence_rank = 0
    else:
        display_status = _norm(item.get("diagnosis_status")) or "Da classificare"
        confidence_label = "Da verificare"
        confidence_rank = 1

    item["display_status"] = display_status
    item["display_source"] = _display_source(item)
    item["confidence_label"] = confidence_label
    item["confidence_rank"] = confidence_rank
    item["is_demo"] = bool(is_demo)
    item["is_official"] = bool(is_official)
    item["is_user_generated"] = bool(source_type in {"user", "company", "association"} or "user" in source_l or "utente" in source_l)
    item["is_vet_validated"] = bool(is_vet_validated)
    item["is_rapid_test"] = bool(is_rapid_test)
    item["is_suspect"] = bool(is_suspect and not is_demo and not is_official and not is_vet_validated and not is_rapid_test)

    return item


def enrich_public_events(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [enrich_public_event(e) for e in events]
