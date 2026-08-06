# Home Presentation Aggregation Layer

**Status:** Implemented  
**Branch:** `feature/home-goal-presentation-dedupe`  
**Date:** 2026-08-06  
**Ranking:** `home-rank-1.3`  
**Presentation:** `home-pres-1.0`

## Problem

The same Goal (e.g. Psicologia) previously appeared as many Home cards: study plan, action-project hint (“Prossima sessione tra N giorni”), calendar sessions, ripasso reminders, decisions, suggestions, conversation resumes. Users saw a fragmented Home instead of one coherent next step.

## Principle

**Presentation-only aggregation.** Plans, sessions, events, suggestions, and conversation sessions are **never deleted or mutated** to fix Home. The layer groups related artifacts and emits **one presentation card per `goal_id`**.

## Pipeline

```
adapters (gather_all)
    → attach_goal_context (persistent refs → goal_id)
    → user state (snooze/ignore)
    → rank_items (home-rank-1.3)
    → source dedupe (never merge distinct Goals by title)
    → aggregate_presentation (ONE card / Goal)
    → primary + priorities + resume + ORA TI CONSIGLIA
```

Code: `backend/home/presentation.py`, wired in `backend/home/service.py`.

## Preference order (primary shell)

1. Concrete imminent action (session today / departure / overdue)
2. Blocker
3. Recovery session (skipped / missed)
4. Next session
5. Synthetic Goal card (study plan / travel project)
6. Resume suggestion

Collapsed siblings become `supporting_details`, badges, secondary `actions`, and `source_refs` — **not** separate priority cards.

## Card contract (`GET /api/home`)

Each Goal card (promoted onto the existing HomeItem public shape):

| Field | Meaning |
|-------|---------|
| `presentation_id` | Stable `pres_goal_{goal_id}` |
| `goal_id` | Goal identity (required for aggregation) |
| `card_type` | `study` / `travel` / … |
| `title` | Goal-level title (e.g. Preparare l'esame di Psicologia) |
| `subtitle` | Exam countdown · next session · progress |
| `next_action` | Concrete next step (may absorb a better suggestion) |
| `supporting_details` | Collapsed artifacts (sessions, events, CE, …) |
| `actions` | Continua, Apri piano, Flashcard, … |
| `source_refs` | Provenance list |
| `hidden_artifact_count` | How many siblings were folded in |
| `generated_at` | Aggregation timestamp |

Ungrouped items (no `goal_id`) pass through unchanged — **safe fallback**, never title-merge across Goals.

## Study card example

- **Title:** Preparare l'esame di Psicologia  
- **Fields:** exam in N days, next session, completed/skipped, review, flashcards, plan link  
- **Actions:** Continua, Apri piano, Flashcard, Interrogami, Rimanda  
- **Not** separate cards for Goal / plan / each session / review / calendar event

## Travel card example

- **Title:** Vacanza a Vibo Marina  
- **Fields:** departure, next prep, outbound/return, docs, Maps, bookings  
- **Actions:** Continua, Preparativi, Percorso, Calendario, Documenti  
- **Not** separate cards for Goal / vacation block / outbound / return / project / suggestion

## Cross-lane rules

| Lane | Rule |
|------|------|
| Primary focus | Same aggregation; one Goal max |
| Priorities | Max **one** card per Goal; never re-list primary Goal |
| Resume | Same Goal as primary → omitted (unless truly distinct motivated action) |
| ORA TI CONSIGLIA | Suggestion with same `goal_id` enriches Goal card / `next_action`; section only if not duplicating primary |
| Conversation | Interrupted CE for a Goal → action “Continua organizzazione” / “Riprendi conversazione” on Goal card — **not** a new card |

## Dedupe keys (prefer order)

`goal_id` → `project_id` / `plan_id` → `source_priority_id` → `action_session_id` → `conversation_session_id` → Google `extendedProperties.private` → artifact relationships (`study_plan_id` on life_nodes, decisions, reminders).

**Never** merge different Goals because titles look similar.

## Legacy

- Audit/migrate: `backend/scripts/audit_home_goal_links.py`  
- Non-destructive attach of `goal_id` where uniquely reconstructible  
- Optional `--archive-fixtures` marks local e2e users (no deletes)

## Flag

```env
GOAL_ENGINE_ENABLED=1
```

When OFF: no Goal attach → no presentation clusters → legacy Home item list.

## Tests

- Backend: `tests/test_home_presentation_aggregation.py` (≥13 cases)
- Playwright: `frontend/e2e/home-presentation-dedupe.spec.ts`
- Verification: `docs/HOME_DEDUPLICATION_VERIFICATION.md`
