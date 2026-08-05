# Home V2 — Architecture

Last updated: 2026-08-05

## Shape

```
frontend/app/(tabs)/index.tsx          → Home V2 screen
frontend/app/situazione.tsx            → full situation view
frontend/src/components/home/v2/*      → Adesso, Perché, actions, situazione, banner, priorità, insights, resume
backend/home/                          → aggregator + ranking + actions
backend/home/adapters/*                → per-source loaders (fail-soft)
GET  /api/home
GET  /api/home/situation
POST /api/home/actions
POST /api/home/refresh
```

## Aggregated response

| Field | Meaning |
|-------|---------|
| `primary_focus` | Top ranked item (public shape, **no score**) |
| `explanation` | Factors, sources, confidence, missing_data, ranking_version |
| `current_situation` | ≤4 indicators + CTA |
| `priorities` | Non-empty groups |
| `insights` | ≤2 deduped insights |
| `resume_item` | One resume or null |
| `connection_warnings` | Partial-source / Google banner signals |
| `google_calendar` | `{ connected, show_banner, … }` |
| `generated_at` | ISO |
| `ranking_version` | `home-rank-1.0` |
| `partial` | True if a source adapter failed |

## Unified item model

`id, type, subtype, title, description, source_type, source_id, priority, urgency, confidence, due_at, start_at, end_at, duration_minutes, location, amount, status, actions, reason_factors, created_at, updated_at` (+ internal `score` persisted only).

## Adapters (fail-soft)

Google Calendar ingestion, internal Life Graph events, Documents V2, event candidates, document actions, study/flashcard/quiz, activities/tasks, reminders, decisions (non-seed for real users), Brain/Life Graph link proposals.

## Persistence

- `home_snapshots` — ranked items including score
- `home_item_state` — snooze / ignore / complete / priority override / banner dismiss
- `home_insights` — dedupe + status

## Frontend refresh triggers

Focus re-entry, pull-to-refresh (`/home/refresh`), after home actions, app reopen via `useFocusEffect`.
