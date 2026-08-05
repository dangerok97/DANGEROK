# Home V2 — Verification

Last updated: 2026-08-06

## Backend

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests/test_home_v2.py tests/test_home_goal_aware.py -q
```

Coverage includes: empty home, bill (3d), concert tomorrow, visit, needs_review, study/resume, invoice, overdue activity, multi priority, primary focus, ranking/explanation/insight, resume, Google on/off, Gemini absent, source error, user isolation, dedupe, snooze, complete, update after document, free-window indicators, 3 deferred admin tasks, incomplete flashcard/quiz. Fixtures A–G.

**Goal-aware (2026-08-06):** `home-rank-1.2` — same-goal collapse, study/travel shadow, blockers/skipped/prep, flag off, isolation, resume/idle proposal, ranking factors — `tests/test_home_goal_aware.py` (**39** with `test_home_v2`).

## Frontend checks

```bash
cd frontend
yarn lint
npx tsc --noEmit
npx expo export --platform web
```

## Playwright (Expo web)

Verified 2026-08-05: **2 passed** against local backend `:8000` + Expo web `:8081`.

```bash
cd frontend
npx playwright test e2e/home-v2.spec.ts
npx playwright test e2e/home-goal-aware.spec.ts
```

Covers: API `/home` schema (no score leak), Home shell, Adesso/Perché/actions/situazione/Google banner, no 100/100 / Dopo, situazione route, refresh, responsive widths, bottom nav, logout/login when logout control is present.

**Goal-aware smoke:** Study/Travel confirm → one item per `goal_id`, Goal context, Perché factors, Apri piano, refresh + logout/login — no `goals` block / Goal tab (`e2e/home-goal-aware.spec.ts`, **2 passed** on `:8010` with `GOAL_ENGINE_ENABLED=1`).

## Not verified

- Native iOS / Android Home V2
- Production deploy

## Manual procedure

1. Register/login on Expo web.
2. Upload a bill-like document (Documents V2) or create a bill decision.
3. Open Home → expect Adesso + Perché + type actions.
4. Pull to refresh → `generated_at` updates.
5. Open **Vedi situazione completa**.
6. If Google disconnected → compact banner; **Non ora** dismisses; Settings still has full connect.
7. Start a quiz/flashcards session, leave incomplete → resume block appears.
8. Complete / snooze primary → Home reorders.
