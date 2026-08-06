# Conversation Engine — Architecture

## Place in the pipeline

```
Input → Conversation Engine → Semantic Extraction → Intent → Gap Analyzer
  → Goal → Action Engine → Projects → Brain → Proactive → Home
```

CE is the **entry orchestrator**. It runs Semantic Extraction + Gap Analyzer before Action Engine, then passes `known_slots` + `next_best_question`. It never duplicates study/travel/calendar domain logic.

## Package

```
backend/conversation_engine/
  models.py          # ConversationSession + API bodies
  repository.py      # Mongo conversation_sessions
  memory.py          # known_slots merge / skip helpers
  orchestrator.py    # start / message / continue / resume / cancel
  service.py         # feature flag facade
  router.py          # /api/conversation/*
  adapters/
    intent.py | goal.py | action.py | projects.py
    brain.py | suggestions.py | maps.py
    documents.py | calendar.py | stubs.py
```

## Adapters (only domain touch points)

| Adapter | Calls |
|---------|--------|
| IntentAdapter | `IntentEngine.classify` |
| GoalAdapter | Goal shadow `create` from intent |
| ActionAdapter | AE `open` / `answer` / `get` / `cancel` + known_slots seed |
| ProjectsAdapter | Read action/study/travel project refs from AE |
| BrainAdapter | Artifact pointer only |
| SuggestionsAdapter | Proactive context / resume handoff |
| MapsAdapter | Extract maps artifacts from AE (no geocoding in CE) |
| Documents / Calendar | Extract artifact refs from AE effects |
| StubOriginAdapter | email / whatsapp / open_banking honesty |

## HTTP API (`/api/conversation`)

| Method | Path | Role |
|--------|------|------|
| GET | `/` | List resumable sessions |
| POST | `/start` | Classify → Goal shadow → open AE |
| POST | `/resume` | Resume by `session_id` or `resume_token` |
| GET | `/sessions/{id}` | Session + AE snapshot |
| POST | `/{id}/message` | Forward answer to AE |
| POST | `/{id}/continue` | Refresh next question |
| POST | `/{id}/cancel` | Cancel CE + AE |
| POST | `/{id}/pause` | Pause + new resume_token |
| GET | `/{id}/history` | Compact steps (`not_chat: true`) |
| GET | `/{id}/summary` | Resume summary + artifacts |

## Frontend

- `ParlaConOra` replaces Home top bar hero.
- `ConversationEngine.start` → API → `router.push(/action/{id})`.
- `/conversation` entry bridge for deep links / resume.
- ResumeCard + Proactive **Riprendi** → CE resume → AE UI.

## Home presentation

Interrupted CE sessions with a `goal_id` are **not** shown as a second Home card. The Presentation Aggregation Layer folds them into the Goal card as action **Continua organizzazione** / **Riprendi conversazione** (`docs/HOME_PRESENTATION_AGGREGATION.md`).

## Indexes

`conversation_sessions`: unique `id`, unique `resume_token`, `(user_id, status, updated_at)`, `(user_id, origin)`, `(user_id, action_session_id)`, `(user_id, goal_id)`.

## Proactive handoff

Generators emit `resume_conversation` for interrupted CE sessions. Accept → `ConversationEngineService.start_from_proactive` (resume preferred).
