# ORA Goal Engine — Lifecycle

**Goal UX:** not implemented. This document describes backend status machine only.

## Statuses

`idea` → `planning` → `active` → (`waiting` \| `blocked` \| `paused`) → `completed` \| `cancelled` → `archived`

| Status | Meaning |
|--------|---------|
| `idea` | Captured outcome, not yet planned |
| `planning` | Draft / pre-confirm |
| `active` | Confirmed living goal (Study/Travel shadow default) |
| `waiting` | Blocked on external input |
| `blocked` | Hard blocker |
| `paused` | User/system pause |
| `completed` | Desired outcome reached |
| `cancelled` | Abandoned (also used for merge source) |
| `archived` | Terminal sink |

## Shadow confirm path

1. User completes Study or Travel Action Engine flow.
2. Domain service confirms artifact (`study_plans` / `travel_projects`).
3. Flow calls `GoalService.upsert_from_*_confirm`.
4. Goal status set to **`active`**.
5. Progress projected from sessions / travel phase (not invented).
6. Events: `GoalCreated` or `GoalUpdated` in `goal_events`.

## Dedupe order

1. `idempotency_key` (same as study/travel hash when available)
2. `study_plan_id` / `travel_project_id`
3. Same `goal_type` + equivalent title

Identical goals are **updated**, never duplicated. Explicit merge via `POST /api/goals/merge`.

## Events

| Event | When |
|-------|------|
| `GoalCreated` | First upsert |
| `GoalUpdated` | Subsequent upsert / patch |
| `GoalCompleted` | Status → completed |
| `GoalCancelled` | Status → cancelled / soft delete |
| `GoalMerged` | Merge API |
| `GoalArchived` | Archive API |

## Progress rules

- **Study:** `completed_sessions / total_sessions` from `study_sessions` / plan sessions.
- **Travel:** prep done flags when present; otherwise honest phase-based soft ratio (upcoming with no prep → **0%**).
- Never ship a hardcoded decorative percentage unrelated to domain data.
