# Home V2 — Architecture

Last updated: 2026-08-06

## Shape

```
frontend/app/(tabs)/index.tsx          → Home V2 screen
frontend/app/situazione.tsx            → full situation view
frontend/src/components/home/v2/*      → Adesso, Perché, actions, situazione, banner, priorità, ORA TI CONSIGLIA, insights, resume
backend/home/                          → aggregator + ranking + presentation + actions
backend/home/adapters/*                → per-source loaders (fail-soft)
backend/home/presentation.py           → Presentation Aggregation Layer (one card / Goal)
backend/proactive_engine/              → suggestions for ora_ti_consiglia
GET  /api/home
GET  /api/home/situation
POST /api/home/actions
POST /api/home/refresh
```

## Aggregated response

| Field | Meaning |
|-------|---------|
| `primary_focus` | Top **presentation** card (public shape, **no score**) |
| `explanation` | Factors, sources (incl. `source_refs`), confidence, missing_data, ranking_version |
| `current_situation` | ≤4 indicators + CTA |
| `priorities` | Non-empty groups — **max one card per Goal** |
| `insights` | ≤2 deduped insights |
| `resume_item` | One resume or null (never same Goal as primary) |
| `ora_ti_consiglia` | ≤3 Proactive Engine suggestions not already folded into a Goal card |
| `connection_warnings` | Partial-source / Google banner signals |
| `google_calendar` | `{ connected, show_banner, … }` |
| `generated_at` | ISO |
| `ranking_version` | `home-rank-1.3` |
| `partial` | True if a source adapter failed |

**No Goals section** — Goals are not listed on Home. See `docs/GOAL_AWARE_HOME.md` + `docs/HOME_PRESENTATION_AGGREGATION.md`.

## Unified item model

`id, type, subtype, title, description, source_type, source_id, priority, urgency, confidence, due_at, start_at, end_at, duration_minutes, location, amount, status, actions, reason_factors, created_at, updated_at` (+ internal `score` persisted only).

Optional Goal context refs (when `GOAL_ENGINE_ENABLED` + linked): `goal_id`, `goal_title`, `goal_type`, `goal_status`, `goal_progress`, `goal_progress_label`, `goal_next_action`, `goal_target_date`, `goal_blockers`, `goal_project_id`.

Presentation fields (when aggregated): `presentation_id`, `card_type`, `subtitle`, `next_action`, `supporting_details`, `source_refs`, `hidden_artifact_count`, `presentation_badges`, `presentation_version`.

## Adapters (fail-soft)

Google Calendar ingestion, internal Life Graph events, Documents V2, event candidates, document actions, study/flashcard/quiz, travel projects, activities/tasks, reminders, decisions (non-seed for real users), Brain/Life Graph link proposals, Action Engine sessions/projects, Conversation Engine resumes.

**Post-gather:** `home/goal_context.py` attaches active Goals via persistent refs; `home/presentation.py` collapses same-`goal_id` artifacts into **one** presentation card (flag-gated). Source data is never deleted for presentation.

## Persistence

- `home_snapshots` — ranked items including score
- `home_item_state` — snooze / ignore / complete / priority override / banner dismiss
- `home_insights` — dedupe + status

## Frontend refresh triggers

Focus re-entry, pull-to-refresh (`/home/refresh`), after home actions, app reopen via `useFocusEffect`.
