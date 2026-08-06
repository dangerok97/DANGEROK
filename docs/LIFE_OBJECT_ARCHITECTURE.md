# Life Object Architecture

## Framing

Life Objects sono il **modello canonico** della realtà utente.  
Goal Engine, Documents V2, Brain, Conversation, Proactive, Home, Travel, Study **restano**: leggono/scrivono oggetti; non detengono più la verità in isolamento.

## Package

```
backend/life_objects/
  models.py          # LifeObject + ObjectReasoningDecision
  types.py           # type catalog
  repository.py      # Mongo `life_objects` + identity indexes
  deduplication.py   # strong keys, soft address, merge fields
  reasoner.py        # Gemini + deterministic
  linking.py         # Brain edges object↔object / object↔doc
  memory.py          # history + utility trend helper
  service.py         # CRUD + shadow upserts
  shadow.py          # soft-fail wrappers
  router.py          # /api/life-objects
  tests/
```

## Collection Mongo

`life_objects` — indexes su `id`, `(user_id, type, status)`, identity_keys sparse (`address_norm`, `cadastral`, `pod`, `pdr`, `plate`, `vin`, `lender_property`, …).

## Shadow hooks

| Fonte | Dove | Funzione |
|-------|------|----------|
| Documents / Life Experience | `life_setup.service.consume_document` dopo `persist_document_understanding` | `shadow_upsert_from_document` |
| Goal Engine | `GoalService.upsert` | `shadow_attach_goal` → `goals.life_object_id` |
| Travel confirm | `TravelProjectService.confirm` | `shadow_upsert_from_travel` |
| Study confirm | `StudyPlanService.confirm` | `shadow_upsert_from_study` |

## Modello (campi chiave)

`id`, `user_id`, `type`, `title`, `status`, `confidence`, `created_at`, `updated_at`, `summary`, `relationships`, `documents`, `calendar_events`, `goals`, `projects`, `brain_nodes`, `knowledge`, `history`, `properties`, `pending_questions`, `suggested_actions`, `health`, `source_count`, `last_reasoning`, `next_reasoning`, `origin`, `ai_summary`, `ai_reasoning_version`, `ai_confidence`, `identity_keys`, `merge_proposals`

## Dedupe

- **HOME:** cadastral, POD/PDR, address (soft containment), coords, lender+property  
- **VEHICLE:** plate, VIN  
- Conflitto → `merge_proposals` (mai silent Casa 2)

## Home

Home V2 **invariata** (Goal-aware).  
`LIFE_OBJECT_HOME_UI_ENABLED` predispone Home V3 — non attiva.
