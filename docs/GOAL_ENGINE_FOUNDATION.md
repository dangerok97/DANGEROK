# ORA Goal Engine — Foundation (P1 + P2 Shadow)

**Status:** Implemented (backend-only, invisible)  
**Branch:** `feature/goal-engine-foundation`  
**Date:** 2026-08-06  
**Goal UX:** **NOT implemented** — no screens, tabs, Home ranking changes, or Goal cards.

Aligned with `docs/GOAL_ENGINE_ARCHITECTURAL_AUDIT.md` recommended architecture.

## Product pipeline

```
Input → Intent → Goal Engine (identity/lifecycle) → Action Engine (conversation)
      → Study/Travel (typed artifacts) → Projects (bags) → Brain → Home (unchanged)
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
- **Home** — unchanged this phase (no Goals adapter, no ranking change).

## Flag

```env
GOAL_ENGINE_ENABLED=1
```

Set `0` / `false` to disable shadow upserts entirely.

## Non-goals (this phase)

- No Goal screens / tabs / Home primary_focus from Goals
- No collapsing Study/Travel into the `goals` table
- No fuzzy auto-merge without explicit merge API
- No production deploy

## Next phases (from audit)

- M1/P4: Home `meta.goal_id` dedupe
- P5: Progress projection on session complete / travel phase tick
- P6: Optional FE read API consumers
