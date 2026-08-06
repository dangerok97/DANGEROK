# ORA Proactive Engine — Product

**Status:** Foundation implemented  
**Branch:** `feature/proactive-engine`  
**Date:** 2026-08-06  

## One line

ORA decides **IF / WHEN / HOW / WHY** to intervene — only when a real personal assistant would speak up. Not a notification cron. Not a reminder spam engine.

## User-facing

Home section **ORA TI CONSIGLIA** (max 3, ordered, no duplicates). Hidden when empty.

Actions per suggestion:

| Action | Behavior |
|--------|----------|
| Accetta | Real effect when possible (e.g. study recovery session); else accepted + concrete next_action/route |
| Ignora | Dismiss + learning |
| Ricordamelo dopo | Snooze: 15m / 1h / stasera / domani / custom |
| Apri | Navigate to grounded route (plan, travel, document, situazione) |

## Pipeline (product view)

```
Goals · Projects · Brain · Documents · Calendar  (+ future email/finance/weather)
        ↓
Proactive Engine (observe + candidate generation)
        ↓
Decision Engine (worth disturbing?)
        ↓
Suggestion (scored, explainable)
        ↓
Home "ORA TI CONSIGLIA"  +  Notification Policy (batch / quiet — no push blast)
```

Integrates with Goal Engine / Home V2 / Action Engine. Does **not** duplicate Goal identity.

## Real interventions today

| Domain | Example |
|--------|---------|
| Study | Skipped sessions → recovery suggestion with concrete text; Accept creates planned recovery session |
| Travel | ≤7 days to departure → packing/prep grounded on travel project |
| Calendar | Overlapping events → suggest modify |
| Documents | Education doc + study goal → suggest flashcards (generation via Documents path) |

## Predisposed only (NOT done)

| Domain | Status |
|--------|--------|
| Email / Gmail | Types + stub generator — **never invents** |
| Finance | Predisposed — **never invents** |
| Weather | Predisposed — **never invents** |
| Health | Predisposed — **never invents** |
| WhatsApp | Not implemented (out of scope for foundation) |

## Ruthless quality bar

If a suggestion fails “would a real assistant say this?”, it is **not** emitted.

## Feature flag

```env
PROACTIVE_ENGINE_ENABLED=1
```

Default ON locally. OFF → no generation; Home section empty.
