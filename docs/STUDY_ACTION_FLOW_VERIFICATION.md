# Study Action Flow — Verification

## Status matrix

| Area | Status |
|------|--------|
| Implemented (backend + FE) | Yes |
| Unit / integration pytest | Yes — `tests/test_study_action_flow.py` + updated AE study test |
| API endpoints | Yes — `/api/action-engine/*`, `/api/study-plans/*` |
| Browser Playwright FULL UI | **PASS** 2026-08-05 — `frontend/e2e/study-action-flow.spec.ts` (1/1, ~29s); UI-only after fixture seed |
| Gemini topic split | Optional — skipped when keys absent (verified in tests) |
| Google Calendar real sync | Best-effort when connector connected; otherwise compact banner — **does not block** |
| Native mobile (iOS/Android) | **Not verified** |

## Backend tests covered

Intent received · subject extracted · dates · docs found/none · upload mid-flow · availability · intensities · conflicts/impossible plan · preview · confirm · idempotency · duplicate · session actions · resume/draft · logout persistence · isolation · Gemini absent · Google absent · delete · complete blocked without confirm.

## Playwright evidence

Path: `frontend/test-results/study-action-flow/` (gitignored).

- Screenshots per turn + complete + plan + Home after
- `google-status.json` — connected or explicitly absent
- `run-log.json` — steps answered via UI only

## Honest limits

- Google sync uses connector `create_event` when available; partial failures recorded on sessions.
- Documents seed in E2E may skip if multipart upload required; materials step still completable with «Nessuno».
- Exam-questions tool maps to Interrogami generation path (no separate fake generator).
- Mobile native not run in this activity.

## Manual procedure

1. Start Mongo + `uvicorn` backend + Expo web.
2. Register/login.
3. Create decision «Preparazione esame di Psicologia» (or use Home priority).
4. Tap Inizia → answer each UI question (date text OK).
5. On preview, accept → confirm.
6. Open plan from complete CTA; start/complete a session.
7. Refresh Home — plan / countdown / resume visible.
8. Optional: connect Google, retry sync from plan screen.
