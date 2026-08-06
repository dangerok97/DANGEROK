# Entity Model

Every extracted slot is an `EntityValue`:

```json
{
  "raw": "fra due settimane",
  "normalized": "2026-08-20",
  "confidence": 0.93,
  "status": "known",
  "source": "deterministic",
  "timezone": "Europe/Rome",
  "label": "20 agosto 2026",
  "ambiguity": null
}
```

## Status

`known` | `confirmed` | `corrected` | `ambiguous` | `inferred` | `missing` | `low_confidence`

## Source (merge rank)

`user_confirmed` > `manual_correction` > `current_input` > `prior_conversation` > `document` > `calendar` > `deterministic`/`gemini` > `default`

## Dates

Keep original phrase + ISO normalized + Europe/Rome timezone + confidence + ambiguity candidates when DMY/MDY collide. Never invent `return_date` from departure-only phrases.
