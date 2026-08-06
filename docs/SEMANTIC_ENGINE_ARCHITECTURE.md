# Semantic Engine — Architecture

## Package

```
backend/semantic_engine/
  models.py            # EntityValue, ExtractionResult, GapAnalysisResult
  dates.py             # IT relative/absolute dates (Europe/Rome)
  deterministic.py     # Primary extractor (no LLM)
  gemini_extractor.py  # Optional via Provider Manager / google-genai
  extractor.py         # Deterministic → optional Gemini fill → merge → gaps
  normalizer.py
  context_merge.py     # Precedence merge; never overwrite confirmed
  gap_analyzer.py      # Declarative schemas → next_best_question
  cache.py             # input+context hash
  service.py / router.py
  schemas/             # study, exam_preparation, travel, vacation, event,
                       # medical, payment, administrative, document_review, generic
```

## Intent vs Semantic

| Engine | Role |
|--------|------|
| Intent Engine | Classifier — which flow |
| Semantic Engine | Structured entities + missing slots |
| Gap Analyzer | Next question only |
| Action Engine | Render / validate answers; no autonomous question choice when slots known |

## API (`/api/semantic`)

| Method | Path | Role |
|--------|------|------|
| POST | `/extract` | Extract (+ store on CE session if id given) |
| POST | `/gaps` | Gap analysis |
| PATCH | `/conversation/entities` | Patch entities |
| POST | `/confirm-entity` | Confirm a slot |

Auth required. Cache by input+context hash. Usage metrics on Gemini attempts.

## Conversation Engine wiring

On `start` and after each answer: extract → merge confirmed → Gap Analyzer → pass `gap` + `known_slots` into Action Engine open/answer. Persist `extracted_entities`, `confirmed_entities`, `missing_slots`, `ambiguous_slots`, `extraction_version`, `last_extraction_at`.

## Context merge precedence

confirmed user > manual correction > current input > prior conversation > document > calendar > inference > default
