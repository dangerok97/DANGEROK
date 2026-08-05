# ORA Goal Engine — Data Model

**Collection:** `goals`  
**Events:** `goal_events`  
**Goal UX:** not implemented.

## Goal document

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | `goal_…` |
| `user_id` | string | Owner |
| `goal_type` | string | `study` \| `travel` \| `event` \| `medical` \| `admin` \| `generic` \| … |
| `goal_subtype` | string? | e.g. `exam_preparation`, `vacation` |
| `title` | string | User-facing outcome label |
| `description` | string? | |
| `status` | string | See lifecycle doc |
| `priority` / `importance` / `urgency` | int? | Optional hints; Home still recomputes later |
| `desired_outcome` | string? | End state in user language |
| `current_state` | string? | Short state label |
| `next_action` | string? | Denormalized hint from confirm |
| `progress` | object | `{ ratio, label, phase, completed_units, total_units, source, details }` |
| `completion_percentage` | float | `ratio * 100` — never a fixed fake % |
| `brain_node_id` | string? | Primary Life Graph node (`goal` or `trip`) |
| `project_id` | string? | Link to `action_projects` bag (not the Goal itself) |
| `study_plan_id` | string? | Typed artifact |
| `travel_project_id` | string? | Typed artifact |
| `source_action_session_id` | string? | AE session that confirmed |
| `idempotency_key` | string? | Unique sparse per user |
| `linked_documents` | string[] | |
| `linked_calendar_events` | string[] | Life/Google opaque ids |
| `linked_decisions` | string[] | |
| `linked_people` / `linked_places` / `linked_memories` / `linked_finances` | string[] | Soft links |
| `created_from` | object | intent, subtype, source refs, artifact |
| `merged_into_id` / `merged_from_ids` | | Merge trail |
| `target_date` / `start_date` | string? | Exam / trip window |
| `created_at` / `updated_at` / `completed_at` / `cancelled_at` / `archived_at` | ISO | |

## Indexes (non-destructive)

- unique `id`
- `(user_id, status, updated_at)`
- `(user_id, goal_type)`
- unique sparse `(user_id, idempotency_key)`
- sparse `(user_id, study_plan_id)`, `(user_id, travel_project_id)`, `(user_id, project_id)`, `(user_id, brain_node_id)`, `(user_id, source_action_session_id)`

## What Goals are / are not

| ARE | ARE NOT |
|-----|---------|
| Durable outcome identity | Intent results |
| Parent pointer for study/travel | Replacement for `action_sessions` |
| Soft-linked to one Brain node | Full schedule blobs |
| Progress projection owner | `action_projects` rename |

## Artifact relationship

```
Goal
 ├─ study_plan_id → study_plans (+ study_sessions)
 ├─ travel_project_id → travel_projects
 ├─ project_id → action_projects (bag)
 └─ brain_node_id → life_nodes (goal|trip)
```

Soft reverse links written on upsert: `study_plans.goal_id`, `travel_projects.goal_id`, `action_projects.goal_id`.
