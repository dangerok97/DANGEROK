# ORA Goal Engine — Foundation (P1 + P2 Shadow)

**Status:** Implemented (backend-only, invisible)  
**Branch:** `feature/goal-engine-foundation`  
**Date:** 2026-08-06  
**Goal UX:** **NOT implemented** — no Goal screens/tabs. Home is **Goal-aware** (context/dedupe only); see `docs/HOME_GOAL_AWARE.md` on `feature/goal-aware-home`.

Aligned with `docs/GOAL_ENGINE_ARCHITECTURAL_AUDIT.md` recommended architecture.

## Product pipeline

```
Input → Intent → Goal Engine (identity/lifecycle) → Action Engine (conversation)
      → Study/Travel (typed artifacts) → Projects (bags) → Brain → Home (reads Goals for context)
```

## What shipped

| Piece | Location | Notes |
|-------|----------|-------|
| Package | `backend/goal_engine/` | models, service, repository, router, dedupe, progress, types, strategy, events, lifecycle |
| Collection | Mongo `goals` + `goal_events` | Non-destructive indexes on startup |
| Feature flag | `GOAL_ENGINE_ENABLED` | Default **ON** (`1`) locally; when OFF, upsert is no-op |
| Shadow Study | `StudyPlanService.confirm` → `GoalService.upsert_from_study_confirm` | e.g. "Preparare esame Psicologia" |
| Shadow Travel | `TravelProjectService.confirm` → `GoalService.upsert_from_travel_confirm` | e.g. "Vacanza Calabria" |
| API | `/api/goals/*` | Auth-protected; unused by UI |
| Brain | Reuse study/travel node; stamp `attributes.goal_id` | No breaking of existing `brain_links` |
| Projects | `action_projects.goal_id` soft link | Project ≠ Goal |

## Boundaries (enforced)

- **Intent Engine** — classification only; does not create Goals.
- **Action Engine** — does **not** invent Goals ad-hoc; Study/Travel confirm flows call `GoalService.upsert`.
- **Study / Travel** — remain typed artifacts (`study_plans`, `travel_projects`).
- **`action_projects`** — remain AE link bags.
- **Brain** — graph identity/facts; Goal owns product lifecycle.
- **Home** — Goal-aware context on `feature/goal-aware-home` (dedupe/ranking/insights); **still no Goal UX**.

## Flag

```env
GOAL_ENGINE_ENABLED=1
```

Set `0` / `false` to disable shadow upserts and Home Goal attach/dedupe.

## Non-goals (foundation + Home-aware)

- No Goal screens / tabs / dedicated Goals section on Home
- No collapsing Study/Travel into the `goals` table
- No fuzzy auto-merge without explicit merge API
- No production deploy

## Next phases (from audit)

- ~~M1/P4: Home `meta.goal_id` dedupe~~ → done in Goal-aware Home (`docs/HOME_GOAL_AWARE.md`)
- P5: Progress projection on session complete / travel phase tick
- P6: Optional FE Goals read surface (later — still not Goal UX on Home)
