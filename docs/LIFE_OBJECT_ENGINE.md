# Life Object Engine

**Stato:** SHADOW MODE (2026-08-06)  
**Branch:** `feature/life-object-engine`  
**Home V3 Life Objects UI:** PREDISPOSTO (`LIFE_OBJECT_HOME_UI_ENABLED=0`) — **non shippato**. Home resta Goal-aware.

## Visione (framing canonico)

Il Life Object Engine è il **modello canonico della realtà dell’utente**.  
Gli altri motori **continuano a esistere** e non vengono eliminati: Conversation, Goal, Documents, Brain, Proactive, Home, Travel, Study restano operativi come **satelliti / fonti**.  
Non possiedono più “la verità” da soli: **leggono e aggiornano** i Life Object.

```
                    ┌──────────────────────────┐
                    │      LIFE OBJECTS        │
                    │  (verità canonica user)  │
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
| `LIFE_OBJECT_GEMINI` | `1` | Reasoning Gemini; fallback deterministico se assente |

## Tipi

`HOME`, `VEHICLE`, `PERSON`, `JOB`, `UNIVERSITY`, `COURSE`, `PET`, `UTILITY`, `INSURANCE`, `BANK_ACCOUNT`, `MORTGAGE`, `SUBSCRIPTION`, `TRAVEL`, `DEVICE`, `INVESTMENT`, `HEALTH_PROVIDER`, `COMPANY`, `FAMILY_MEMBER`, `CUSTOM`

## Motori satelliti (tutti conservati)

- **Documents V2** — unica pipeline upload/OCR; dopo understanding → aggiorna Life Object
- **Goal Engine** — resta; shadow field `life_object_id` (il Goal non è più l’unica verità)
- **Travel / Study** — restano artifact; in parallelo aggiornano TRAVEL / UNIVERSITY|COURSE
- **Brain / Conversation / Proactive / Home** — restano; Home UX non sostituita in questa fase

## API (auth, non usata dalla UI principale)

`/api/life-objects` — CRUD, search, link, merge, reason, trend, status

## Cosa NON fa ancora

- Nessuna modifica UX importante
- Home V3 Life Objects view non attiva
- Non sostituisce Travel Project / Goal / Documents
