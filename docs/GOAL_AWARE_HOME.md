# Goal-aware Home (no Goal UX)

**Status:** Implemented  
**Branch:** `feature/goal-aware-home`  
**Date:** 2026-08-06  
**Ranking:** `home-rank-1.2`  
**Alias:** `docs/HOME_GOAL_AWARE.md` points here (same product feature).

## Principle

Goals are an **invisible context layer**. Home remains the only surface (Adesso / Situazione / Priorità / Osserva / Continua). **No Goal tab, list page, Goals Home section, or parallel Goal UX.**

A Goal does **not** replace Home items; it stamps refs for ranking, dedupe, motivation factors, progress, next_action, blockers, resume, and insights.

## Item schema (refs, not full Goal)

When linked + `GOAL_ENGINE_ENABLED`:

| Field | Meaning |
|-------|---------|
| `goal_id` | Goal identity |
| `goal_title` | Context title (“Obiettivo: …”) |
| `goal_type` | study / travel / … |
| `goal_status` | active / blocked / waiting / … |
| `goal_progress` | 0–100 when **reliable** (study sessions / prep counts) |
| `goal_progress_label` | Honest label (`2/5 sessioni`, `fase: days_until`) |
| `goal_next_action` | Next concrete action string |
| `goal_target_date` | Target / start date |
| `goal_blockers` | Honest blocker strings (blocked state, skipped sessions, missing prep) |
| `goal_project_id` | Linked action_project id (bag ≠ Goal) |

Omitted when null. **No** `goals[]` block on `GET /api/home`.

### Progress honesty

- Study: session ratio → `%` + label OK.
- Travel soft phase (`travel_phase`): **phase/checklist label only** — `goal_progress` omitted (no fake precise %).

## Primary focus

1. Concrete imminent next action → action card + Goal as context (`Obiettivo: …`).
2. Goal `blocked` → surface block (e.g. “Alloggio non confermato”).
3. Same `goal_id` → **one** focus representative (not five duplicate cards).
4. Goals but no artifact → idle proposal from `next_action` (opens plan/travel/project — **not** a Goal page).
5. No Goals → legacy Home unchanged.

## Dedupe

1. Source/title dedupe.
2. `dedupe_by_goal`: same `goal_id` → one **focus** + one **resume** lane.
3. Prefer: blocked surface → draft resume → next session → travel phase/prep → study/travel project → docs → **action_project last**.

## Ranking (`home-rank-1.2`)

Bump from `1.1`: blockers, status, stale advance, skipped sessions, missing prep, calendar links, travel phase progress factor.

| Factor | Meaning |
|--------|---------|
| `goal_importance` / `goal_urgency` | From Goal |
| `goal_blocked` / `goal_waiting` / `goal_paused` | Status |
| `goal_blockers` | Non-status blockers |
| `goal_deadline_*` | Target date vs progress |
| `goal_next_action` / `goal_context` | Next action / title |
| `goal_progress` / `goal_progress_phase` | Reliable % or soft phase |
| `goal_stale` | Hours since last progress update |
| `goal_skipped_sessions` | Skipped study sessions |
| `goal_missing_prep` | Travel prep pending |
| `goal_calendar` | Linked calendar events (light) |
| `session_today` | Study session today |

**Brain = context only** (link proposals as verify items) — never a Goal score input.

Flag **OFF** → no attach, no goal factors, no goal collapse → legacy aggregation.

## Actions

Open flow / plan / project / doc / calendar / travel detail — **never** a generic Goal page.

Study: Inizia / Apri piano / Flashcard / Interrogami when applicable.

## Perché adesso / Resume / Insights

- Explanation factors include Goal codes only when primary is linked — no CoT.
- Resume may mention `Obiettivo: {title}`; ≠ duplicate of primary for same Goal.
- Insights: ≤2 slots; Goal progress may fill a free slot (`source=goal_engine`).

## Flag

```env
GOAL_ENGINE_ENABLED=1
```

## Pipeline

```
Intent → Goal (identity) → Action → Study/Travel → Projects → Brain
                              ↓
                         Home reads Goals for context
```

## Tests

- Backend: `tests/test_home_goal_aware.py` (≥12 cases: session today, skipped, travel prep, blocked, completed, multi-artifact/dedupe, resume, insight, no Goals, flag off, isolation, idle proposal, unit attach/progress).
- Playwright: `frontend/e2e/home-goal-aware.spec.ts` (Study + Travel + refresh/logout).
