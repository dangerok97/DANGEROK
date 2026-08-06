# ORA Proactive Engine — Architecture

**Package:** `backend/proactive_engine/`  
**Flag:** `PROACTIVE_ENGINE_ENABLED` (default `1`)  
**Collections:** `proactive_suggestions`, `proactive_learning`

## Modules

| Module | Role |
|--------|------|
| `models.py` | Suggestion + candidate + explain + learning stats |
| `types.py` | Taxonomy + stub vs active generator sets |
| `generators/` | study, travel, calendar, documents (real); stubs (empty) |
| `scoring.py` | Deterministic score (urgency, importance, goal, deadlines, brain, calendar, learning) |
| `decision_engine.py` | Gate: anti-spam, quiet hours, study/event/driving heuristics |
| `notification_policy.py` | Never send push immediately; batch; respect quiet/study/sleep/events/driving |
| `learning.py` | Per user/type/source accept/dismiss → multiplier |
| `explainability.py` | Reason + structured factors (no CoT) |
| `dedupe.py` | Same goal/source/action window |
| `lifecycle.py` | Expiry + unsnooze |
| `accept.py` | Real accept hooks (study recovery, travel next_action, flashcards path, calendar open) |
| `repository.py` | Mongo CRUD |
| `service.py` | Orchestration |
| `router.py` | `/api/suggestions/*` |

## Flow

1. `regenerate(user_id)` — lifecycle cleanup  
2. `gather_candidates` — fail-soft generators  
3. Dedupe against active keys  
4. Score each candidate (never random)  
5. Decision gate (`would_assistant_speak`)  
6. Persist `active` suggestions + attach notification policy meta  
7. Home calls `home_suggestions` → max 3 collapsed  

## Integration

```
Goal Engine ──refs──► Suggestion.goal_id / project_id
Action Engine / Study / Travel ──artifacts──► generators
Documents / Calendar ──evidence──► generators
Home V2 ──GET /api/home──► ora_ti_consiglia[]
Notification Policy ──future channel──► no blast in foundation
```

## API

| Method | Path |
|--------|------|
| GET | `/api/suggestions` |
| POST | `/api/suggestions/regenerate` |
| POST | `/api/suggestions/search` |
| GET | `/api/suggestions/{id}` |
| GET | `/api/suggestions/{id}/explain` |
| GET | `/api/suggestions/{id}/notification-policy` |
| POST | `/api/suggestions/{id}/dismiss` |
| POST | `/api/suggestions/{id}/accept` |
| POST | `/api/suggestions/{id}/complete` |
| POST | `/api/suggestions/{id}/snooze` |

All auth-protected (`get_current_user`).

## Home

`HomeResponse.ora_ti_consiglia` — list ≤3 public suggestions. FE section hidden if empty.

## Indexes (startup)

`proactive_suggestions`: id unique; user+status+score; user+dedupe_key+status; user+goal_id; user+expires_at; user+type+created  
`proactive_learning`: unique (user_id, suggestion_type, source)

## Predisposed stubs

`generators/stubs.py` always returns `[]` for emails/finance/weather/health. Wired so future connectors plug in without inventing facts.
