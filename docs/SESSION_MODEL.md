# Conversation Session Model

Collection: `conversation_sessions`

## Fields

| Field | Type | Notes |
|-------|------|--------|
| `id` | string | `ces_…` |
| `user_id` | string | Owner |
| `created_at` / `updated_at` | ISO | |
| `status` | enum | `active` \| `waiting_user` \| `running_action` \| `completed` \| `cancelled` \| `paused` |
| `origin` | enum | home, voice, text, documents, notifications, proactive; stubs: email, whatsapp, open_banking |
| `input` | string? | Original user phrase |
| `intent` | object? | Intent Engine result dump |
| `goal_id` | string? | Shadow Goal |
| `project_id` | string? | Action / travel / study project |
| `action_session_id` | string? | Bridged AE session |
| `current_step` | string? | Current AE turn id |
| `history` | array | Compact steps (not chat bubbles) |
| `artifacts` | array | `{kind,id,label}` refs |
| `summary` | string? | Human resume line |
| `resume_token` | string | `crt_…` unique |
| `known_slots` | object | Memory — never re-ask |
| `suggestion_id` | string? | Proactive link |
| `voice_meta` | object? | STT stub honesty |
| `meta` | object | route, ui_mode, synthetic_prompt, … |
| `engine_version` | string | `conversation-engine-1.0` |

## History entry

`{ at, role: user|ora|system, kind, text?, step_id?, meta }`  
Kinds: start | intent | goal | question | answer | artifact | status | resume | cancel.

API `GET …/history` returns steps with `not_chat: true` — UI must not render as messenger bubbles.

## Status lifecycle (summary)

See `ORCHESTRATION.md` for full lifecycle. In short:

`active` → classify/open → `waiting_user` ⇄ `running_action` → `completed` | `cancelled` | `paused` → resume → `waiting_user`.
