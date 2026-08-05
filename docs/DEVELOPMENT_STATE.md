# ORA — Development State

Last updated: 2026-08-06 (Goal Engine Foundation — shadow)

## Branch

- Active: `feature/goal-engine-foundation` (local, no push)
- Base: `feature/travel-action-flow` @ `cda5017` (+ audit doc)

## Goal Engine Foundation (backend-only)

| Item | Stato |
|------|--------|
| Package `backend/goal_engine/` | **implemented** |
| Mongo `goals` + `goal_events` + indexes | **implemented** |
| Flag `GOAL_ENGINE_ENABLED` (default ON) | **implemented** |
| Shadow upsert on Study confirm | **implemented** |
| Shadow upsert on Travel confirm | **implemented** |
| Dedupe / merge / timeline / progress | **implemented** |
| Brain link (`goal_id` on node) | **implemented** |
| API `/api/goals/*` (unused by UI) | **implemented** |
| Goal UX / Home ranking / tabs | **NOT implemented** (by design) |
| pytest `test_goal_engine.py` | **9 passed** |
| pytest study+travel regression | **22 passed** |
| Playwright shadow API assert | **2 passed** — `frontend/e2e/goal-engine-shadow.spec.ts` |

## Travel Action Flow (Life Planner slice)

| Item | Stato |
|------|--------|
| Full travel confirm + Home phases + Brain | **intact** (prior branch) |

## Study Action Flow

| Item | Stato |
|------|--------|
| Full study plan E2E + Google sync | **intact** |

## Intent Classification Engine

| Item | Stato |
|------|--------|
| Package + AE routing via Intent | **intact** (does not create Goals) |

## Open / next

1. Home `meta.goal_id` dedupe (audit M2 / P4) — **not started**
2. Progress refresh on session complete / travel phase tick
3. Optional FE Goals read surface (later)
4. Weather / email auto-find / native mobile (travel)

## Credentials / safety

- Never commit `.env` / tokens
- Goal Engine needs no new secrets
- Flag off → shadow upsert no-op
