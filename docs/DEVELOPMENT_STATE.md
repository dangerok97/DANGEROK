# ORA — Development State

Last updated: 2026-08-06 (Goal-aware Home V2 — no Goal UX)

## Branch

- Active: `feature/goal-aware-home` (local, no push)
- Base: `feature/goal-engine-foundation` @ `7352f7c`

## Goal-aware Home V2 (no Goal UX)

| Item | Stato |
|------|--------|
| Home loads active Goals when `GOAL_ENGINE_ENABLED` | **implemented** |
| Attach `goal_*` on study/travel/AE/resume items | **implemented** |
| Dedupe same `goal_id` → one focus + one resume | **implemented** |
| Ranking `home-rank-1.1` Goal factors | **implemented** |
| Insights / resume / Perché cite Goal honestly | **implemented** |
| Flag OFF → pre–Goal-aware behavior | **implemented** |
| Goal tab / list / Goals Home section | **NOT implemented** (by design) |
| Docs `HOME_GOAL_AWARE.md` | **implemented** |

## Goal Engine Foundation (backend)

| Item | Stato |
|------|--------|
| Package `backend/goal_engine/` + shadow Study/Travel | **intact** |
| API `/api/goals/*` (unused by Goal UI) | **intact** |
| Flag `GOAL_ENGINE_ENABLED` | **intact** (also gates Home attach) |

## Open / next

1. Progress refresh on session complete / travel phase tick
2. Optional FE Goals read surface (later — still not a Home Goals module)
3. Weather / email auto-find / native mobile (travel)

## Credentials / safety

- Never commit `.env` / tokens
- Goal Engine / Goal-aware Home need no new secrets
- Flag off → shadow upsert no-op + Home ignores Goals
