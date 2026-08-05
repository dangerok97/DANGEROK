# ORA — Development State

Last updated: 2026-08-06 (Goal-aware Home complete vs full checklist — no Goal UX)

## Branch

- Active: `feature/goal-aware-home` (local, no push)
- Base: `feature/goal-engine-foundation` @ `7352f7c`
- Follow-up on `a702d1e`: schema fields, ranking `1.2`, blockers/prep/skipped, idle proposal, docs `GOAL_AWARE_HOME.md`

## Goal-aware Home V2 (no Goal UX)

| Item | Stato |
|------|--------|
| Home loads active Goals when `GOAL_ENGINE_ENABLED` | **implemented** |
| Attach full `goal_*` refs (type/target/blockers/project) | **implemented** |
| Dedupe same `goal_id` → one focus + one resume | **implemented** |
| Ranking `home-rank-1.2` Goal factors | **implemented** |
| Travel soft progress = phase/label (no fake %) | **implemented** |
| Primary focus: action + Obiettivo / blocked surface | **implemented** |
| Idle Goals → useful proposal (not empty) | **implemented** |
| Insights / resume / Perché cite Goal honestly | **implemented** |
| Flag OFF → pre–Goal-aware behavior | **implemented** |
| Goal tab / list / Goals Home section | **NOT implemented** (by design) |
| Docs `GOAL_AWARE_HOME.md` (+ `HOME_GOAL_AWARE.md` alias) | **implemented** |

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
