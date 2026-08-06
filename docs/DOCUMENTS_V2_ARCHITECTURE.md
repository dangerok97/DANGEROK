# Documents V2 — Architecture

Branch: `feature/documents-v2-completion` (from `feature/rebuild-intelligent-documents` @ `3ff825d`)

## Product shift

From file archive → **intelligent actions engine**: every upload is classified and produces utility (events, study aids, deadlines, Brain facts).

## Modules

| Layer | Paths |
|-------|--------|
| FE hub | `frontend/app/(tabs)/documenti.tsx` |
| FE detail | `frontend/app/document/[id].tsx` + `DocumentUtilityPanel.tsx` |
| API | `backend/documents/router.py` |
| Orchestration | `backend/documents/intelligence/service.py` |
| Analyze / taxonomy | `analyzer.py`, `taxonomy.py` |
| Study | `study_tools.py` (flashcards, quiz, outline, explain) |
| Admin extract | `admin_extract.py` |
| Calendar / Maps / Google | `calendar_adapter.py`, `google_sync.py` |
| Brain | Life Graph + Knowledge merge in `service._merge_brain` |

**Extended, not deleted:** storage, extraction, OCR, LLM manager, Google sync, Brain hooks, JWT auth.

## Pipeline V2

`uploaded → queued → extracting → classifying → understanding → generating_actions → awaiting_confirmation | completed | needs_review | failed`

Versions: `document_schema_version=2.0`, `analysis_version=2.0`, `processing_version=intel-docs-2.0`.

## Study / quiz / admin API

| Method | Path |
|--------|------|
| POST | `/api/documents/{id}/study` — `explain_simple`, `summary_*`, `outline`, `questions`, `exam_questions`, `flashcards`, `quiz_start` |
| POST | `/api/documents/{id}/quiz/answer` |
| POST | `/api/documents/{id}/admin/actions/complete` |
| POST | `/api/documents/{id}/admin/deadline-calendar` |
| PATCH | `/api/documents/{id}/analysis` — user corrections + provenance |

## Provenance

`field_provenance` per field: extracted / suggested / confirmed / corrected + confidence + source.  
Reanalyze **never overwrites** confirmed/corrected values (title, admin.*, edu.*, analysis scalars).

## Auto-add calendar

Prefs (default **off**): `calendar_auto_add_enabled`, `calendar_auto_add_threshold` (0.90).

Gates: single proposed event, **confidence > threshold**, datetime present & not ambiguous, no critical missing fields, not `requires_review`, no existing draft → `confirm_event(sync_to_google=True)`.

## Search

`GET /api/documents/search/intelligent` — multi-token AND across title/text/edu/admin; special phrases `azioni aperte`, `da verificare`; always filtered by `user_id`.

## Life Experience integration (no second pipeline)

`backend/life_setup/` (Life Experience) reuses Documents V2 as its **only** document pipeline: it never re-implements upload, MIME/size validation, storage, OCR, extraction, classification, retry, reanalyze or delete. It only attaches a `document_id` to the conversation session, polls `pipeline_status`, and — once ready — runs an **extra** reasoning layer (`backend/documents/intelligence/life_reasoning.py`, Gemini via Provider Manager) that writes `doc["life_reasoning"]` onto the same document and maps the result into the Life Profile (`backend/life_setup/document_mapping.py`). See `LIFE_EXPERIENCE_REAL_DOCUMENTS.md` and `AI_DOCUMENT_UNDERSTANDING.md`.

## Dynamic utility by macro

| Macro | Utility UI |
|-------|------------|
| event / travel | Confirm ORA / Google, Maps, directions |
| education | Study panel + flashcards + Interrogami |
| administrative / financial | Admin panel + editable fields + deadline calendar |
| medical | Appointment only + medical disclaimer (no clinical invention) |
| generic | Summary / keywords / resolved fields |
