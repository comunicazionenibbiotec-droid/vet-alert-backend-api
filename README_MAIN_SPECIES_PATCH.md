# Patch concettuale per backend/main.py - filtro specie v73

Se il backend filtra gli eventi in base ad animal_filter, verificare che i valori supportati includano:

all
companion
dog
cat
livestock
bovine
swine
equine
ovine
caprine
poultry
wildlife

Schema consigliato:

ANIMAL_FILTER_GROUPS = {
    "all": None,
    "companion": ["dog", "cat"],
    "dog": ["dog"],
    "cat": ["cat"],
    "livestock": ["bovine", "swine", "equine", "ovine", "caprine", "poultry"],
    "bovine": ["bovine"],
    "swine": ["swine"],
    "equine": ["equine"],
    "ovine": ["ovine"],
    "caprine": ["caprine"],
    "poultry": ["poultry"],
    "wildlife": ["wildlife"]
}

Nel filtro SQL o in memoria, usare animal_group normalizzato e includere ovine/caprine.