# Intent Classification Engine — Architecture

Last updated: 2026-08-05

## Pipeline

```
Free text / Home item
        │
        ▼
┌───────────────────────────┐
│ Intent Classification     │  backend/intent_engine/
│  knowledge (patterns)     │
│  deterministic classifier │  ← always on
│  entity extraction        │
│  confidence + clarify     │
│  optional LLM enricher    │  ← INTENT_LLM_ENRICH=1 only
└───────────┬───────────────┘
            │ Intent object
            ▼
┌───────────────────────────┐
│ Action Engine open        │  flow registry keyed by intent(+subtype)
│  study|event|travel|…     │  NOT by home item_type EVENT/GENERIC
│  clarify flow if needed   │
└───────────────────────────┘
```

## Package layout

```
backend/intent_engine/
  knowledge.py     extensible keyword/pattern KB (IT)
  classifier.py    deterministic scoring + thresholds
  entities.py      subject, place, amount, date, exam, …
  enricher.py      optional Gemini/LLM confirm (never required)
  mapping.py       Intent → AE flow / Home type / decision category
  models.py        IntentResult, ClarifyOption, CLASSIFIER_VERSION
  service.py       IntentEngine.classify / classify_text
  router.py        POST /api/intent/classify
```

## Intent object

```json
{
  "intent": "study",
  "subtype": "exam_preparation",
  "confidence": 0.99,
  "reason": "keywords + deterministic rules",
  "entities": { "subject": "Psicologia", "goal": "Preparare esame" },
  "clarify_options": null,
  "needs_clarify": false,
  "classifier_version": "intent-engine-1.0"
}
```

## Flow mapping

| Intent | Action Engine flow |
|--------|--------------------|
| study (+ exam_preparation) | study |
| travel (+ vacation) | travel |
| event | event |
| medical | medical |
| payment / financial / administrative / document_review | admin |
| task / communication / shopping / project / generic | generic |
| needs_clarify | clarify |

## Action Engine changes

- `POST /api/action-engine/open` classifies via Intent Engine first (or accepts precomputed `intent`).
- Deprecated: `resolve_category(item_type, source_type)` as flow router (returns generic; unused for choice).
- On clarify answer → rebuild real flow turns from chosen Intent.
- Persist Intent on `decisions` when opened/created.

## Home

- Decision create runs `classify_text` and stores `intent*` fields; weak/wrong `category` overridden when confidence high.
- `decisions_adapter` prefers Intent for Home `type` labels; classifies legacy rows on load.
- UI labels prefer `meta.intent` over raw `item.type`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/intent/classify` | Classify text → Intent (auth) |
| POST | `/api/action-engine/open` | Uses Intent Engine internally |

## Config

- `INTENT_LLM_ENRICH=0` (default) — fully offline deterministic.
- No new secrets required.
