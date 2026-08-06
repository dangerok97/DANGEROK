# Life Object Engine

**Stato:** SHADOW + AI enrichment (2026-08-07)  
**Branch:** `feature/life-object-engine`  
**Home V3 Life Objects UI:** PREDISPOSTO (`LIFE_OBJECT_HOME_UI_ENABLED=0`) — **non shippato**. Home resta Goal-aware. Nessuna schermata “Life Object” per l’utente.

## Visione (framing canonico)

Il Life Object Engine è il **modello canonico della realtà dell’utente**.  
Gli altri motori **continuano a esistere** e non vengono eliminati: Conversation, Goal, Documents, Brain, Proactive, Home, Travel, Study restano operativi come **satelliti / fonti**.  
Non possiedono più “la verità” da soli: **leggono e aggiornano** i Life Object.

```
                    ┌──────────────────────────┐
                    │      LIFE OBJECTS        │
                    │  (verità canonica user)  │
                    │  identity / state        │
                    │  narrative · insights    │
                    └────────────▲─────────────┘
           read/write │          │          │ read/write
    ┌─────────────────┼──────────┼──────────┼─────────────────┐
    │                 │          │          │                 │
 Documents V2    Goal Engine   Brain    Conversation     Proactive
 (upload/OCR)    (outcomes)   (edges)   Life Experience    Home
    │                 │                     │
 Travel / Study   Action Engine        (UX Home ancora Goal-aware;
 artifact tipizzati                     Home V3 oggetti = OFF)
```

## Feature flags

| Flag | Default | Effetto |
|------|---------|---------|
| `LIFE_OBJECT_ENGINE_ENABLED` | `1` | Shadow writes ON |
| `LIFE_OBJECT_HOME_UI_ENABLED` | `0` | Home V3 oggetti OFF (UX invariata) |
| `LIFE_OBJECT_GEMINI` | `1` | Reasoning + enrichment Gemini; fallback italiano deterministico se assente |

## Identity vs State

| Piano | Significato | Esempi |
|-------|-------------|--------|
| **Identity** | Cosa definisce l’oggetto | indirizzo, catastale, POD/PDR, targa, VIN, ateneo, datore |
| **State** | Cosa cambia nel tempo | fornitore, importi, rata, consumi, compagnia, scadenze |

`properties` resta come bag di compatibilità; migrazione non distruttiva in `identity` / `state`.

## AI enrichment (backend only)

Dopo ogni shadow upsert (documento / goal / travel / study), best-effort:

1. **Narrative** — descrizione naturale della situazione (versionata), non dump campi  
2. **Questions** — domande intelligenti che aumentano la capacità di aiutare ORA  
3. **Insights** — osservazioni (non notifiche) da storia completa  
4. **Temporal** — presente vs storia (bollette, fornitori)  
5. **Life Health** — valutazione spiegabile: completeness, reliability, missing_info, opportunities, risks (+ score overall con reasons)

Gemini via Provider Manager (Pydantic strutturato). Se assente → fallback italiano deterministico. **Mai inventare fatti.**

## Tipi

`HOME`, `VEHICLE`, `PERSON`, `JOB`, `UNIVERSITY`, `COURSE`, `PET`, `UTILITY`, `INSURANCE`, `BANK_ACCOUNT`, `MORTGAGE`, `SUBSCRIPTION`, `TRAVEL`, `DEVICE`, `INVESTMENT`, `HEALTH_PROVIDER`, `COMPANY`, `FAMILY_MEMBER`, `CUSTOM`

## Motori satelliti (tutti conservati)

- **Documents V2** — unica pipeline upload/OCR; dopo understanding → aggiorna Life Object + enrichment  
- **Goal Engine** — resta; shadow field `life_object_id`  
- **Travel / Study** — restano artifact; aggiornano TRAVEL / UNIVERSITY|COURSE  
- **Brain / Conversation / Proactive / Home** — restano; Home UX non sostituita

## API (auth, non usata dalla UI principale)

`/api/life-objects` — CRUD, search, link, merge, reason, trend, status  
`/api/life-objects/{id}/narrative|questions|insights|health|history|relationships|temporal`  
`POST .../enrich` e `.../*/refresh` — ri-eseguono AI/fallback  
`GET /api/life-objects/home-v3-feed` — DTO interno PREDISPOSTO (flag OFF)

## Cosa NON fa ancora

- Nessuna modifica UX Home  
- Nessuna schermata Life Objects  
- Home V3 non attiva (solo serializer interno)  
- Non sostituisce Travel Project / Goal / Documents  
- Gemini live opzionale: CI verde con fallback
