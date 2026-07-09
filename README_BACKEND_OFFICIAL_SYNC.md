# vet.ector backend - Official events sync demo

Questo pacchetto aggiunge al backend FastAPI un primo layer per eventi ufficiali:

- tabella `official_events`;
- connettore demo `OfficialDemoConnector`;
- normalizzatore `normalize_official_event`;
- endpoint `POST /sync/official/run`;
- endpoint `GET /official-events`;
- endpoint `GET /events` compatibile con il frontend attuale, che unisce eventi utente/demo e ufficiali.

## File principali

```text
backend/
├── main.py
├── requirements.txt
├── render.yaml
├── data/
│   ├── source_cities.json
│   ├── source_events.json
│   ├── source_veterinarians.json
│   └── official_events_seed.json
└── sync/
    ├── official_connector.py
    └── normalizer.py
```

## Deploy su Render

Se il repository contiene una cartella `backend`, configura Render cosi:

```text
Root Directory: backend
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
```

Oppure usa `render.yaml` se preferisci l'infrastructure-as-code.

## Endpoint da testare

Dopo il deploy:

```text
https://vet-alert-poc-sync.onrender.com/health
https://vet-alert-poc-sync.onrender.com/cities
https://vet-alert-poc-sync.onrender.com/official-events
https://vet-alert-poc-sync.onrender.com/events?lat=45.4642&lon=9.19&radius_km=80&days=365&animal_filter=all
```

Per forzare il sync demo ufficiale:

```bash
curl -X POST https://vet-alert-poc-sync.onrender.com/sync/official/run
```

## Compatibilita con app corrente

Il frontend attuale puo continuare a chiamare:

```text
GET /events?lat=...&lon=...&radius_km=...&days=...&animal_filter=...
```

La risposta include sia eventi user/demo sia eventi ufficiali demo, con campi:

```text
disease
diagnosis_status
species
animal_group
observation_date
lat
lon
location
region
source
source_type
report_type
distance_km
risk_score
```

## Come sostituire il connettore demo

Il file:

```text
sync/official_connector.py
```

legge `data/official_events_seed.json`. In futuro puoi sostituire il metodo `fetch()` con un connettore reale autorizzato verso fonti ufficiali o pubbliche.

## Nota importante

I record in `official_events_seed.json` sono dimostrativi: servono per testare struttura, sync e visualizzazione. Non sono una replica ufficiale di dati live. Per uso reale bisogna implementare un connettore conforme ai termini d'uso della fonte dati e, per SIMAN/VetInfo, ottenere accesso autorizzato.
