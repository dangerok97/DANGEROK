# Home V2 × Goal Engine — Goal-aware context (no Goal UX)

**Status:** Implemented (backend-first)  
**Branch:** `feature/goal-aware-home`  
**Date:** 2026-08-06  
**Goal UX:** **NOT implemented** — no Goal tab, list page, or Goals section on Home.

## Principle

Goals are an **invisible context layer**. Home remains the only surface (Adesso / Situazione / Priorità / Osserva / Continua). A Goal does **not** replace all Home items; it provides identity for ranking, dedupe, motivation factors, progress, next_action, resume, and insights.

**Example:** Goal “Preparare esame Psicologia” with study plan + sessions + action_project → Home shows **one** coherent primary/priority card (e.g. study plan with next session), enriched with `goal_title` / progress / next_action — not three competing cards for the same exam.

## Duplicate map (pre → post)

| Source adapter | Typical Home item | Link to Goal | Dedupe role |
|----------------|-------------------|--------------|-------------|
| `study` | `study_plan` (+ next session meta) | `study_plan_id` / `goal_id` on plan | **Preferred focus representative** |
| `study` | draft resume | `study_plan_id` + session | Resume lane only |
| `action_engine` | `action_project` bag | `project_id` → Goal | Collapsed when same `goal_id` |
| `action_engine` | active AE session resume | `source_action_session_id` | Resume lane |
| `travel` | `travel_project` | `travel_project_id` | Preferred travel focus |
| `study` docs/flashcards | document study/resume | `linked_documents` | Collapsed if same Goal |
| Brain | link proposals | (usually unlinked) | Untouched |

## Pipeline

```
Intent → Goal (identity) → Action → Study/Travel → Projects → Brain
                              ↓
                         Home reads Goals for context
```

## Dedupe strategy

1. Existing source/title dedupe (`dedupe_items`).
2. **Goal collapse** (`dedupe_by_goal`): same `goal_id` → one **focus** item + one **resume** item.
3. Representative preference (concreteness): resume draft → study with `next_session` → travel phase imminent → `study_plan` / `travel_project` → study docs → **`action_project` last** (bag).

## Ranking (`home-rank-1.1`)

When `goal_id` is attached (and `GOAL_ENGINE_ENABLED`):

| Factor code | Meaning |
|-------------|---------|
| `goal_importance` | From Goal.importance |
| `goal_urgency` | From Goal.urgency |
| `goal_deadline_pressure` | ≤14d + progress &lt; 50% |
| `goal_deadline_near` | ≤7d |
| `goal_next_action` | Honest next_action string |
| `goal_context` / `goal_progress` | Title / % label |

Flag **OFF** → no attach, no goal factors, no goal collapse → behavior matches pre-1.1 (aside from version string still `home-rank-1.1` on response; scoring inputs identical).

## API deltas (item public shape)

Optional fields when linked:

- `goal_id`, `goal_title`, `goal_status`
- `goal_progress` (0–100), `goal_progress_label`, `goal_next_action`
- `meta.goal_*` mirrors + `goal_days_remaining`, `goal_dedupe_key`

Omitted when null. **No** `goals[]` / Goals block on `GET /api/home`.

## Insights / Resume / Perché adesso

- Insights: up to 1–2 total; Goal progress text may fill a free slot (`source=goal_engine`, dedupe_key `goal_progress:{id}`).
- Resume: description may include `Obiettivo: {title}` when linked.
- Explanation factors include Goal codes only when the primary item is linked — never invented.

## Flag

```env
GOAL_ENGINE_ENABLED=1
```

`0` / `false` → Home ignores Goals (identical aggregation to pre–Goal-aware).
