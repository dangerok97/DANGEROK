# Home V2 — Ranking

Last updated: 2026-08-06

## Version

`ranking_version = home-rank-1.3` (Goal-aware + Presentation Aggregation Layer; flag-gated)

### Changelog

| Version | Change |
|---------|--------|
| `1.0` | Base type/due/confidence ranking |
| `1.1` | Goal importance/urgency/deadline/next_action/progress + goal dedupe |
| `1.2` | + status/blockers/stale/skipped sessions/missing prep/calendar; travel phase progress (no fake %); session_today |
| `1.3` | Presentation Aggregation Layer (`home-pres-1.0`): one card per Goal; siblings → supporting_details; title-dedupe scoped by goal_id |

## Properties

- **Deterministic** — same inputs → same order
- **Versioned** — stamped on items + Home response
- **Testable** — pure `rank_items` + integration fixtures
- **Works without Gemini / any LLM**

## Inputs

Type weights, due/start proximity, overdue, amount present, confidence (low boosts review), needs_review, incomplete study sessions, overdue activities. Soft dampening of leisure activities when critical bills exist.

**1.2 Goal factors** (only if item has `goal_id`): importance, urgency, status (blocked/waiting/paused), blockers, deadline vs progress, next_action, progress/% or phase label, stale advance, skipped sessions, missing prep, calendar links. See `docs/GOAL_AWARE_HOME.md`.

**Brain** contributes verify/link items as context — not a Goal score input.

## Outputs (persisted)

`score`, `reason_factors`, `reason_summary`, `priority` band, `urgency`, `ranking_version`, `generated_at`.

## UI rule

**Never show the numeric score** in the Home UI. Show factor labels and summary only.

## Priority bands

`critical` → `today` → `this_week` → `waiting` → `later`

## Explanation

Built only from fired factors + source refs + optional missing_fields. No invented narrative / chain-of-thought.
