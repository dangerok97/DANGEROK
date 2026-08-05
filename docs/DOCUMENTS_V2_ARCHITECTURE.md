# Documents V2 — Architecture

Branch: `feature/rebuild-intelligent-documents`

## Product shift

From file archive → **intelligent actions engine**: every upload is classified and produces utility (events, study aids, deadlines, Brain facts).

## Legacy map (pre-rebuild)

| Layer | Paths |
|-------|--------|
| FE list | `frontend/app/(tabs)/documenti.tsx` (was Iter19 archive) |
| FE detail | `frontend/app/document/[id].tsx` |
| API | `backend/documents/router.py` |
| CRUD/storage | `backend/documents/service.py`, `storage.py`, `extraction.py` |
| Intel | `backend/documents/intelligence/*` |
| Calendar write | `google_sync.py` + connectors |
| Brain | Life Graph + Knowledge merge |

**Extended, not deleted:** storage, extraction, OCR, LLM manager, Google sync, Brain hooks, JWT auth.

**Replaced UX:** list hub + utility-first detail labels; archival-only framing removed.

## Pipeline V2

`uploaded → queued → extracting → classifying → understanding → generating_actions → awaiting_confirmation | completed | needs_review | failed`

Legacy aliases kept: `analyzing`, `action_required`.

Versions: `document_schema_version=2.0`, `analysis_version=2.0`, `processing_version=intel-docs-2.0`.

## Auto-add calendar

User pref (default **off**):

- `calendar_auto_add_enabled`
- `calendar_auto_add_threshold` (default `0.90`)

Gates: single proposed event, confidence ≥ threshold, datetime unambiguous, not `requires_review` → `confirm_event(sync_to_google=True)`.

## Hub API

`GET /api/documents/hub` — aggregates for home UI.  
`GET|PATCH /api/documents/preferences` — AI consent + auto-add.

## Dynamic utility by macro

| Macro | Utility |
|-------|---------|
| event / travel | Confirm → ORA + Google Calendar, Maps |
| education | Summary, concepts, Q&A, Brain |
| administrative / financial | Deadlines, amounts, reminders |
| medical | Discrete titles, appointments only, no diagnosis |
