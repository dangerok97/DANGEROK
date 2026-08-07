# Digital Twin Knowledge Model

**Stato:** implementato (2026-08-07) — layer interno del Life Object Engine  
**Branch:** `feature/life-object-engine`  
**Home UX / schermata Life Objects:** **NON toccate**

## Visione

Ogni Life Object è un **Digital Twin** della realtà dell’utente, con cinque sezioni indipendenti:

| Sezione | Ruolo |
|---------|--------|
| **facts** | Solo informazioni confermate |
| **hypotheses** | Ciò che ORA pensa (mai Facts) |
| **decisions** | Suggerimenti importanti con esito utente |
| **goals** | Solo link a Goal Engine (`life_object_id`) — nessuna duplicazione |
| **memory** | Storia narrativa raccontabile (non log tecnico) |

Più **Life Timeline**: raggruppamento semantico degli eventi (es. percorso mutuo), non solo ordine documenti.

## Regola fondamentale — immutabilità dei Fact

> **Un Fact non viene mai cancellato.**  
> Può essere sostituito, superseduto o archiviato, ma resta nella storia del Digital Twin.

Esempio: cambio fornitore energia → vecchio fornitore `status=superseded` / `active=false`; nuovo `status=current`.  
Consente domande tipo: *«Quanti fornitori energia in 5 anni?»* / *«Quando è stato chiuso il vecchio mutuo?»*

API di delete sui Fact **solleva errore** (`FactImmutabilityError`).

## Authority

| Ruolo | Può | Non può |
|-------|-----|---------|
| **Gemini** | suggerire Facts/Hypotheses/Questions/Recommendations/Decisions **separati** | auto-promuovere Hypothesis→Fact, inventare, cancellare Fact |
| **Backend** | scrivere Fact su path verificato, supersede, confirm/reject, timeline | — |

Prompt AI: sezioni sempre separate — **Facts / Hypotheses / Questions / Recommendations / Decisions**. Mai mischiare.

## Package

`backend/life_objects/knowledge_model/`

- `models.py` — Fact, Hypothesis, Decision, MemoryEvent, TimelineGroup
- `facts.py` — add / supersede / archive (**no delete**)
- `hypotheses.py` — add / confirm→Fact / reject
- `decisions.py` — propose / outcome / `never_ask_again` fingerprint
- `memory_events.py` — eventi narrativi
- `timeline.py` — gruppi semantici
- `migration.py` — identity/state → facts/hypotheses (non distruttivo)
- `integration.py` — hook assimilazione / upsert
- `prompts.py` — regole Gemini separate
- `service.py` — orchestrazione + API helpers

## Integrazione (non-breaking)

- Documento verificato / `LINK_CONFIRMED|PROBABLE` + confidence ≥ 0.70 → **Fact**
- Ambiguo / `LINK_UNCERTAIN` / bassa confidence → **Hypothesis**
- Conferma utente → Fact (con supersede se stesso `type`)
- Reject → `rejected` (non diventa Fact)
- `never_ask_again` → fingerprint; non riproposto (filtro su questions/suggestions)

## API (auth)

**Read:**

- `GET /api/life-objects/{id}/facts`
- `GET /api/life-objects/{id}/hypotheses`
- `GET /api/life-objects/{id}/decisions`
- `GET /api/life-objects/{id}/timeline`
- `GET /api/life-objects/{id}/knowledge` (bundle)

**Write minimi (test / interno, no UI):**

- `POST .../hypotheses` — seed hypothesis
- `POST .../hypotheses/confirm` | `reject`
- `POST .../decisions` — propose
- `POST .../decisions/outcome` — incl. `never_ask_again`

## Home

`LIFE_OBJECT_HOME_UI_ENABLED=0`. Home V3 DTO predisposto con `knowledge_summary` — **nessuna UX shippata**.

## Docs correlate

- `DIGITAL_TWIN_MODEL.md`
- `FACTS_HYPOTHESES_DECISIONS.md`
- `LIFE_OBJECT_ENGINE.md`, `LIFE_OBJECT_ARCHITECTURE.md`, `LIFE_OBJECT_REASONING.md`, `LIFE_OBJECT_VERIFICATION.md`
