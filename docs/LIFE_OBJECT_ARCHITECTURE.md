# Life Object Architecture

## Framing

Life Objects sono il **modello canonico** della realtà utente.  
Goal Engine, Documents V2, Brain, Conversation, Proactive, Home, Travel, Study **restano**: leggono/scrivono oggetti; non detengono più la verità in isolamento.

## Package

```
backend/life_objects/
  models.py          # LifeObject + reasoning/enrichment Pydantic
  types.py           # type catalog
  repository.py      # Mongo `life_objects` + identity indexes
  deduplication.py   # strong keys, soft address, merge fields
  identity_state.py  # identity vs state split (non-destructive)
  reasoner.py        # Gemini + deterministic document mapping
  enrichment.py      # narrative / questions / insights / temporal / health
  linking.py         # Brain edges object↔object / object↔doc
  memory.py          # history + utility trend + state changes
  home_v3.py         # DTO card PREDISPOSTO (flag OFF)
  service.py         # CRUD + shadow upserts + enrichment refresh
  shadow.py          # soft-fail wrappers
  router.py          # /api/life-objects
  tests/
```

## Collection Mongo

`life_objects` — indexes su `id`, `(user_id, type, status)`, identity_keys sparse (`address_norm`, `cadastral`, `pod`, `pdr`, `plate`, `vin`, `lender_property`, …).

Campi enrichment: `identity`, `state`, `narrative`, `insights`, `temporal`, `health` (explainable), `pending_questions`, `ai_enrichment_version`.  
`properties` conservato (compat).

## Shadow hooks

| Fonte | Dove | Funzione |
|-------|------|----------|
| Documents / Life Experience | `life_setup.service.consume_document` dopo `persist_document_understanding` | `shadow_upsert_from_document` → enrich |
| Goal Engine | `GoalService.upsert` | `shadow_attach_goal` → `goals.life_object_id` |
| Travel confirm | `TravelProjectService.confirm` | `shadow_upsert_from_travel` → enrich |
| Study confirm | `StudyPlanService.confirm` | `shadow_upsert_from_study` → enrich |

Enrichment è **best-effort**: non rompe il consume documento.

## Modello (campi chiave)

`id`, `user_id`, `type`, `title`, `status`, `confidence`, `created_at`, `updated_at`, `summary`, `relationships`, `documents`, `calendar_events`, `goals`, `projects`, `brain_nodes`, `knowledge`, `history`, `properties`, **`identity`**, **`state`**, `pending_questions`, `suggested_actions`, **`narrative`**, **`insights`**, **`temporal`**, `health`, `source_count`, `last_reasoning`, `next_reasoning`, `origin`, `ai_summary`, `ai_reasoning_version`, `ai_enrichment_version`, `ai_confidence`, `identity_keys`, `merge_proposals`

## Dedupe

- **HOME:** cadastral, POD/PDR, address (soft containment), coords, lender+property  
- **VEHICLE:** plate, VIN  
- Conflitto → `merge_proposals` (mai silent Casa 2)

## API surface

Auth Bearer. Prefisso `/api/life-objects`.

| Endpoint | Uso |
|----------|-----|
| `GET/POST /`, `GET/PATCH/DELETE /{id}` | CRUD |
| `POST /search`, `/merge`, `/reason` | ricerca / merge / reason |
| `GET /{id}/narrative\|questions\|insights\|health\|history\|relationships\|temporal\|trend` | lettura |
| `POST /{id}/enrich`, `.../*/refresh` | ri-esegue AI/fallback |
| `GET /home-v3-feed` | DTO futuro Home (OFF) |

## Home

Home V2 **invariata** (Goal-aware).  
`LIFE_OBJECT_HOME_UI_ENABLED` predispone Home V3 — non attiva.  
Serializer `home_v3.py` esiste ma non è collegato alla UI.
