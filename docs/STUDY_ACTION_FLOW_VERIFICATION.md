# Study Action Flow — Verification

## Status matrix

| Area | Status |
|------|--------|
| Implemented (backend + FE) | Yes |
| Unit / integration pytest | Yes — `tests/test_study_action_flow.py` + updated AE study test |
| API endpoints | Yes — `/api/action-engine/*`, `/api/study-plans/*` |
| Browser Playwright FULL UI | **PASS** 2026-08-05 — `frontend/e2e/study-action-flow.spec.ts` (1/1, ~29s); UI-only after fixture seed |
| Gemini topic split | Optional — skipped when keys absent (verified in tests) |
| Google Calendar real sync | **PASS** 2026-08-05 — create / update (snooze) / delete verified on live Google |
| Native mobile (iOS/Android) | **Not verified** |

## Backend tests covered

Intent received · subject extracted · dates · docs found/none · upload mid-flow · availability · intensities · conflicts/impossible plan · preview · confirm · idempotency · duplicate · session actions · resume/draft · logout persistence · isolation · Gemini absent · Google absent · delete · complete blocked without confirm.

## Playwright evidence

Path: `frontend/test-results/study-action-flow/` (gitignored).

- Screenshots per turn + complete + plan + Home after
- `google-status.json` — connected or explicitly absent
- `run-log.json` — steps answered via UI only

## Google Calendar real sync (2026-08-05)

**Result: PASS**

Script: `backend/scripts/verify_study_google_sync.py`  
Evidence (gitignored): `frontend/test-results/study-google-sync/verify-report.json`

| Check | Result |
|-------|--------|
| Connector instance (`calendar_google`, status connected) | OK |
| Vault secret reference present | OK |
| Scopes `calendar.events` + `calendarlist.readonly` | OK |
| Default calendar listable via API | OK — primary `francesconicolocefala@gmail.com` |
| Create session → Google event | OK — `google_sync_status=synced` |
| `google_event_id` / `google_calendar_id` persisted | OK |
| Google GET matches title / start / Europe/Rome | OK |
| No duplicates in window | OK (count=1) |
| Snooze via `StudyPlanService.session_action` (UI path) → Google PATCH | OK (start moved +90m) |
| Delete via `StudyPlanService.delete_plan` (UI path) → Google cancelled | OK |

### Bug fixed during verification

`is_google_connected` / sync looked up `connector_id: "google_calendar"` but the real connector id is `calendar_google`. Create also called a non-existent `get_provider_for_user`. Fixed in `action_engine/study/google_sync.py` to use `GoogleCalendarService` + provider `create_event` / `update_event` / `delete_event`, and wired snooze + plan delete to Google.

### Honest limits

- Verification used the **same service methods** as the study-plan UI (`sync_plan_sessions` on confirm/retry-sync, `session_action` snooze, `delete_plan`), not a full Playwright login (password for the connected Gmail user not available in CI).
- Synthetic events were deleted / cancelled on Google after the run.
- Partial sync failures remain non-blocking for plan confirm.

## Manual procedure

1. Start Mongo + `uvicorn` backend + Expo web.
2. Register/login; connect Google Calendar (both localhost and 127.0.0.1 Console URIs).
3. Create decision «Preparazione esame di Psicologia» (or use Home priority).
4. Tap Inizia → answer each UI question (date text OK); enable Google sync when asked.
5. On preview, accept → confirm.
6. Open plan; confirm sessions appear on Google; snooze one; delete plan and confirm Google removal.
7. Or: `cd backend && .venv\Scripts\python.exe scripts\verify_study_google_sync.py`
