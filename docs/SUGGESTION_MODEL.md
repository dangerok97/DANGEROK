# Suggestion Model

Collection: `proactive_suggestions`

## Fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | `psug_…` |
| `user_id` | string | Owner |
| `title` | string | User-facing |
| `description` | string? | Concrete helpful text |
| `reason` | string | Short why |
| `type` | enum | study, travel, finance, calendar, documents, health, projects, emails, weather, life, generic |
| `priority` | low\|medium\|high\|critical | From score/urgency |
| `importance` | 0–1 | Scored |
| `urgency` | 0–1 | Scored |
| `confidence` | 0–1 | Evidence confidence |
| `score` | float | Composite; omitted from public Home payloads by default |
| `source` | string | study_plan, travel_project, calendar, document, … |
| `goal_id` | string? | Soft link — Goal identity not duplicated |
| `project_id` | string? | Action project bag |
| `calendar_event` | string? | Event id |
| `document_id` | string? | |
| `study_plan_id` / `travel_project_id` | string? | Typed artifacts |
| `action` | `{kind,label,route,params}` | Concrete next step |
| `status` | candidate\|active\|snoozed\|dismissed\|accepted\|completed\|expired | |
| `factors` | ScoreFactor[] | Explainable weights |
| `explain` | `{summary,factors,would_assistant_speak,gate_notes}` | No CoT |
| `dedupe_key` | string | Windowed hash |
| `expires_at` | ISO? | Lifecycle |
| `snooze_until` | ISO? | |
| `dismissed` / `accepted` / `completed` | bool | |
| `accept_result` | object? | Honesty + effect from accept handler |
| `meta` | object | evidence, notification_policy, … |
| `created_at` / `updated_at` | ISO | |

## Types

**Active generators:** study, travel, calendar, documents (+ projects/life/generic when grounded).  

**Stub only (never invent):** finance, emails, weather, health.

## Accept honesty

| Type | Accept effect |
|------|----------------|
| Study recovery | Creates **planned** recovery `study_sessions` row; updates plan `next_recovery_session_id`; may set Goal `next_action`. Does **not** mark skipped sessions completed. |
| Travel prep | Sets `next_action` on travel project / goal. No weather/booking invention. |
| Documents flashcards | Marks document `suggested_action=flashcards`; generation via Documents UI/API. |
| Calendar overlap | Opens modify/review path — does not auto-edit events. |
