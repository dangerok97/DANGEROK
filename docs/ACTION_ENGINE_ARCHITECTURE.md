# Action Engine — Architecture

Last updated: 2026-08-06 — receives Gap Analyzer `next_slot` / `next_best_question` + known entities from Semantic Layer. Travel asks departure and return separately (never combined when departure known).

## Shape

```
backend/action_engine/
  models.py          session, turn, answer, project link
  flows/             study|event|travel|medical|admin|generic
  travel/            TravelProject draft/preview/confirm + maps + google_sync
  service.py         open / answer / complete / cancel / merge
  brain.py           Life Graph + Knowledge (deduped merges)
  projects.py        action_projects aggregator
  effects.py         calendar / reminders / decisions / study hooks
  router.py          /api/action-engine/*

frontend/src/action-engine/ActionEngine.ts   ActionEngine.open(item)
frontend/app/action/[sessionId].tsx          one-question UI
frontend/app/action/open.tsx                 deep-link bridge
```

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/action-engine/open` | Start or resume from Home item |
| GET | `/api/action-engine/sessions/{id}` | Session state + current turn |
| POST | `/api/action-engine/sessions/{id}/answer` | One answer → next or complete |
| POST | `/api/action-engine/sessions/{id}/complete` | Force complete + effects |
| POST | `/api/action-engine/sessions/{id}/cancel` | Cancel |
| POST | `/api/action-engine/sessions/{id}/merge-project` | Merge into similar project |

## Persistence

| Collection | Role |
|------------|------|
| `action_sessions` | Conversational state |
| `action_projects` | Multi-step aggregator (docs, calendar, reminders, decisions) |
| `life_nodes` (goal/event) | Brain + Home internal calendar |
| `node_knowledge` | Answer facts via `knowledge.merge` (idempotent) |
| `reminders` | Home adapter pickup |
| `decisions` | Checklist / work items when useful |

Indexes created non-destructively on startup.

## Home integration

- `home/actions_catalog.py` — Apri/Organizza/Inizia → `kind=guide` → `/action/open`
- Frontend `ActionEngine.open(item)` is the only UI entry (no scattered switches)
- Adapter `home/adapters/action_engine_adapter.py` surfaces active sessions + project next hints
- Completion sets `home_invalidate`; client calls `refreshHome()`

## Guarantees

1. Open always returns a `current_turn` while `status=active` (else HTTP 500).
2. Medical copy includes no-advice disclaimer.
3. Credential-blocked integrations are `status=blocked` with honest detail (e.g. weather).
4. Flow selection uses **Intent Classification Engine** only — never raw home `item_type` / title heuristics inside AE.

## Intent integration

See `docs/INTENT_ENGINE_ARCHITECTURE.md`. `POST /api/action-engine/open` classifies (or accepts precomputed Intent) then maps intent(+subtype) → study|event|travel|medical|admin|generic|clarify.
