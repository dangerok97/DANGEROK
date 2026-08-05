# ORA — Development State

Last updated: 2026-08-05 (Intent Classification Engine)

## Branch

- Active: `feature/intent-classification-engine` (local, no push)
- Base: `feature/ora-action-engine` @ `6b3831b`

## Intent Classification Engine

| Item | Stato |
|------|--------|
| Package `backend/intent_engine/` | **implemented** |
| Deterministic classifier + KB (IT) | **implemented** |
| Optional LLM enricher (`INTENT_LLM_ENRICH`) | **implemented** (off by default) |
| `POST /api/intent/classify` | **implemented** |
| AE open routes via Intent (not item_type) | **implemented** |
| Clarify flow on low confidence | **implemented** |
| Persist Intent on decisions + Home labels | **implemented** |
| Corpus ≥100 IT phrases | **124** in fixtures |
| pytest intent + AE | **147 passed** |
| Playwright psychology exam | **1 passed** (Expo web) |
| Native mobile Intent→AE | **not verified** |

## Action Engine

| Item | Stato |
|------|--------|
| Flows study/event/travel/medical/admin/generic/clarify | **implemented** |
| Flow choice via Intent Engine | **required** |
| Title heuristics inside AE for flow choice | **removed** |
| Medical no-advice | **enforced** |
| Weather / live Maps | **blocked placeholders** |

## Home V2 / Documents V2

| Item | Stato |
|------|--------|
| Home V2 aggregator + ranking | **implemented** (labels prefer Intent) |
| Documents V2 | **untouched / intact** |
| Native mobile | **not verified** |

## Open / next

1. Wire Parla / notifications / email ingest to same Intent Engine
2. Expand KB for more languages / edge cases
3. Device smoke (iOS/Android)
4. Optional LLM enrich evaluation with Gemini key

## Credentials / safety

- Never commit `.env` / tokens
- Intent Engine needs no secrets; LLM enrich optional via existing provider keys
