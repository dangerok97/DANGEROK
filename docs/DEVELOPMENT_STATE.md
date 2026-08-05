# ORA — Development State

Last updated: 2026-08-05 (Action Engine)

## Branch

- Active: `feature/ora-action-engine` (local, no push)
- Base: `feature/home-v2-intelligence` @ `01e50de`

## Action Engine

| Item | Stato |
|------|--------|
| Backend `action_engine/` + `/api/action-engine/*` | **implemented** |
| Flows: study, event, travel, medical, admin, generic | **implemented** |
| Frontend `ActionEngine.open(item)` + `/action/[sessionId]` | **implemented** |
| Home Apri/Organizza/Inizia/card → guided flow | **verified Expo web Playwright** (2026-08-05) |
| Brain (Life Graph + Knowledge) + action_projects | **implemented** |
| Medical: no advice / no diagnosis | **enforced in copy + tests** |
| Weather / live Maps traffic | **blocked placeholders** (honest) |
| pytest `test_action_engine.py` | **11 passed** |
| Playwright `e2e/action-engine.spec.ts` | **1 passed** (web); evidence `frontend/test-results/action-engine-smoke/` |
| Native iOS/Android Action Engine | **not verified** |

## Home V2

| Item | Stato |
|------|--------|
| Aggregator + ranking | **implemented** (base) |
| Guide actions (`kind=guide`) + AE adapter | **updated** |
| Native mobile Home V2 | **not verified** |

## Documents V2

| Item | Stato |
|------|--------|
| Hub / pipeline / study / quiz / admin | **complete** (untouched) |
| Mobile native | **not verified** |

## Open / next

1. Manual collaborative smoke: Home priority → first question → chip → Home refresh
2. Optional Playwright smoke for Action Engine
3. Device smoke (iOS/Android)
4. Weather integration when credentials exist

## Credentials / safety

- Never commit `.env` / tokens
- Action Engine needs no new env vars
- Home ranking / Action Engine work without LLM keys (study flashcard hook optional)
