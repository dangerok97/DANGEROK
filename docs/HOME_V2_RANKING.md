# Home V2 — Ranking

Last updated: 2026-08-05

## Version

`ranking_version = home-rank-1.0`

## Properties

- **Deterministic** — same inputs → same order
- **Versioned** — stamped on items + Home response
- **Testable** — pure `rank_items` + integration fixtures
- **Works without Gemini / any LLM**

## Inputs

Type weights, due/start proximity, overdue, amount present, confidence (low boosts review), needs_review, incomplete study sessions, overdue activities. Soft dampening of leisure activities when critical bills exist.

## Outputs (persisted)

`score`, `reason_factors`, `reason_summary`, `priority` band, `urgency`, `ranking_version`, `generated_at`.

## UI rule

**Never show the numeric score** in the Home UI. Show factor labels and summary only.

## Priority bands

`critical` → `today` → `this_week` → `waiting` → `later`

## Explanation

Built only from fired factors + source refs + optional missing_fields. No invented narrative / chain-of-thought.
