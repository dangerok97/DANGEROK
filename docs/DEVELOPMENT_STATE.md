# ORA — Development State

Last updated: 2026-08-06 (Semantic Extraction + Gap Analyzer)

## Branch

- Active: `feature/semantic-extraction-gap-analyzer` (local, no push)
- Base: `feature/home-goal-presentation-dedupe` @ `90b3fb1`

## Semantic Extraction + Gap Analyzer

| Item | Stato |
|------|--------|
| Package `backend/semantic_engine/` | **implemented** |
| Deterministic IT dates/entities | **implemented** |
| Gap schemas (study/travel/medical/payment/…) | **implemented** |
| Conversation session entity fields | **implemented** |
| Action Engine travel split departure/return | **implemented** |
| APIs `/api/semantic/*` | **implemented** |
| FE understood summary (Partenza/Destinazione/Ritorno) | **implemented** |
| pytest `test_semantic_engine.py` | **17 passed** (corpus ≥200) |
| Playwright `semantic-extraction-gap.spec.ts` | **2 passed** (API :8001 + Expo :8081) |
| Docs SEMANTIC_* / ENTITY_MODEL / GAP_ANALYZER | **implemented** |
| Gemini extraction | **optional** via Provider Manager |

## Prior (intact)

- Home Presentation Aggregation / Goal-aware Home
- Conversation Engine / Proactive / Intent / Action / Travel / Study

## Open / next

1. Optional Gemini rephrase for questions (`SEMANTIC_GEMINI_REPHRASE`)
2. Real STT behind voice origin
3. Richer medical/payment flows using gap chips in AE UI

## Credentials / safety

- Never commit `.env` / tokens
- Semantic path works without Gemini (`SEMANTIC_GEMINI_ENABLED=0`)
