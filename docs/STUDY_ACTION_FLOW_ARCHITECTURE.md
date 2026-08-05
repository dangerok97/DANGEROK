# Study Action Flow — Architecture

## Routing

Intent Classification Engine remains the sole flow router.  
`study` + `exam_preparation` → Action Engine flow `"study"`.  
Action Engine never re-parses titles for category selection.

## Packages

| Path | Role |
|------|------|
| `backend/action_engine/study/models.py` | `StudyPlan`, `StudySessionItem`, statuses, intensity, idempotency key |
| `backend/action_engine/study/flow.py` | Stable step ids, validation, skip-known, duplicate/ambiguous turns |
| `backend/action_engine/study/date_parser.py` | IT natural / relative / ISO; never silent on ambiguous |
| `backend/action_engine/study/documents.py` | Documents V2 + education / Brain search |
| `backend/action_engine/study/generator.py` | Deterministic schedule; Gemini optional topic split only |
| `backend/action_engine/study/plan_service.py` | Draft / preview / confirm / sessions / delete |
| `backend/action_engine/study/tools.py` | Flashcards / Interrogami link-or-generate on confirm |
| `backend/action_engine/study/google_sync.py` | Real Google events if connected; partial OK |
| `backend/action_engine/study/brain_links.py` | Goal + material edges; no dup nodes; user corrections win |
| `backend/action_engine/flows/study.py` | Thin delegate to study.flow |
| `backend/action_engine/service.py` | Study answer / back / draft / confirm gating |
| `backend/action_engine/router.py` | `/api/action-engine/*` + `/api/study-plans/*` |

## Mongo collections

- `study_plans` — plan documents
- `study_sessions` — individual sessions
- Indexes created non-destructively in `StudyPlanService.ensure_indexes` (startup via Action Engine)

## Time

Storage UTC. Default display TZ `Europe/Rome`.

## Idempotency

`sha256(user_id|source_priority_id|exam_name|exam_date)[:32]`

## Frontend

- `frontend/app/action/[sessionId].tsx` — chips, multi-select, date text, preview, back, draft
- `frontend/app/study-plan/[id].tsx` — plan detail + session actions
- Home V2 adapter `home/adapters/study.py` loads active plans + draft resume CTAs

## Audit notes (pre-implementation)

Previous study flow was chip-only intake that wrote Life Graph sessions on last answer without preview/confirm, real dates, doc picker, or first-class plan model. This architecture replaces that path for `flow == "study"` only; other flows unchanged.
