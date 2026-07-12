from __future__ import annotations

from typing import Any, Dict, List


def species_matches(value: str, target: str) -> bool:
    if not target or target == "all":
        return True
    value = (value or "").lower().strip()
    target = target.lower().strip()
    aliases = {
        "bovine": ["bovine", "bovino", "bovini", "cattle"],
        "swine": ["swine", "suino", "suini", "pig", "pigs", "cinghiale", "cinghiali"],
        "ovine": ["ovine", "ovino", "ovini", "sheep", "pecora", "pecore"],
        "caprine": ["caprine", "caprino", "caprini", "goat", "goats", "capra", "capre"],
        "equine": ["equine", "equino", "equini", "horse", "horses", "cavallo", "cavalli"],
        "poultry": ["poultry", "avicoli", "volatile", "volatili", "avian", "bird", "birds"],
        "dog": ["dog", "cane", "canine"],
        "cat": ["cat", "gatto", "feline"],
    }
    return value in aliases.get(target, [target])


def summarize_area_risk(events: List[Dict[str, Any]], density_items: List[Dict[str, Any]], risk_layers: List[Dict[str, Any]], species: str = "all") -> Dict[str, Any]:
    filtered_events = [e for e in events if species_matches(str(e.get("animal_group") or e.get("species") or ""), species)]
    official = [e for e in filtered_events if e.get("is_official") or str(e.get("source_type", "")).lower() == "official"]
    vet_validated = [e for e in filtered_events if e.get("is_vet_validated")]
    rapid_positive = [e for e in filtered_events if e.get("is_rapid_test")]
    suspect = [e for e in filtered_events if e.get("is_suspect")]
    demo = [e for e in filtered_events if e.get("is_demo")]

    real_count = len(filtered_events) - len(demo)
    if official:
        level = "high"
        label = "Rischio alto"
        reason = "Sono presenti casi confermati ufficiali nell'area selezionata."
    elif vet_validated or rapid_positive:
        level = "medium"
        label = "Rischio medio"
        reason = "Sono presenti segnalazioni validate o test rapidi positivi nell'area selezionata."
    elif suspect:
        level = "watch"
        label = "Rischio da verificare"
        reason = "Sono presenti segnalazioni sospette non ancora confermate."
    else:
        level = "low"
        label = "Rischio basso"
        reason = "Non risultano eventi reali rilevanti nell'area selezionata."

    density_relevant = [d for d in density_items if species_matches(str(d.get("species", "")), species)]
    efsa_relevant = []
    for layer in risk_layers:
        layer_species = layer.get("species") or []
        if species == "all" or any(species_matches(str(s), species) for s in layer_species):
            efsa_relevant.append(layer)

    return {
        "risk_level": level,
        "risk_label": label,
        "reason": reason,
        "events": {
            "total": len(filtered_events),
            "real": real_count,
            "official": len(official),
            "vet_validated": len(vet_validated),
            "rapid_test_positive": len(rapid_positive),
            "suspect": len(suspect),
            "demo": len(demo),
        },
        "density_context_count": len(density_relevant),
        "risk_layers_count": len(efsa_relevant),
        "density_context": density_relevant[:10],
        "risk_layers": efsa_relevant[:10],
    }
