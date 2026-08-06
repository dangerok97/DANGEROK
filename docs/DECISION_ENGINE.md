# Proactive Decision Engine (gate)

**Location:** `backend/proactive_engine/decision_engine.py`  

This is the **disturbance gate** for the Proactive Engine (distinct from the legacy `decision_engine/` ranking package for Decisions).

## Question

Should ORA create/surface this suggestion **now**?

Only if a real personal assistant would speak up.

## Hard rejects

- Stub types (email/finance/weather/health) — never invent
- Missing title/reason/dedupe_key
- Active generators without grounded `evidence`
- Confidence below floor (~0.45)
- Score below floor (~0.42)
- Active suggestion cap
- Same dedupe key in recent window
- Rate limit (~3 emissions / hour unless critical urgency)
- During driving (when detectable from calendar title heuristics)
- During study/event unless urgency high enough
- High dismiss learning rate suppressing mid-value noise
- Generic motivational fluff titles

Quiet hours / sleep do **not** block creating Home suggestions — `notification_policy` defers push/batch instead.

## Context signals (when data exists)

| Signal | Source |
|--------|--------|
| Quiet hours | Local hour heuristic (≈ Europe/Rome) |
| Sleep | 23:00–06:00 local |
| In study | `study_sessions` in_progress or overlapping planned |
| In event | Life Graph / calendar events overlapping now |
| Driving | Event title keywords (guida, autostrada, …) |
| Learning dismiss rate | `proactive_learning` |

## Notification policy (related)

`notification_policy.py` never sets `send_now=true` for push in foundation. Channels: `home` or `none`. Batch windows morning/afternoon. Respects quiet/study/sleep/events/driving.

## Scoring (inputs to gate)

`scoring.py` — urgency, importance, deadlines, goal importance/progress, brain soft-link, calendar busyness, type base, learning multiplier. **Never random.**

## Output

`GateResult(accept, reasons[], notes[])` — stored in explain `gate_notes` when accepted; rejected samples returned from `regenerate` for debugging.
