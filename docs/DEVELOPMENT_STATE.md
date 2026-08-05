# ORA — Development State

Last updated: 2026-08-05 (Study Action Flow complete)

## Branch

- Active: `feature/complete-study-action-flow` (local, no push)
- Base: `feature/intent-classification-engine` @ `66b7775`

## Study Action Flow

| Item | Stato |
|------|--------|
| Conversational steps 1–12 + preview/confirm | **implemented** |
| StudyPlan model + sessions + intensities/states | **implemented** |
| Documents V2 material search + upload resume | **implemented** |
| Deterministic generator (+ optional Gemini topics) | **implemented** |
| Flashcards / Interrogami on confirm (no dupes) | **implemented** |
| Brain links (no dup nodes) | **implemented** |
| Google sync if connected; banner if not | **implemented** (partial fail OK) |
| Home plan card + draft resume CTA | **implemented** |
| Plan UI `/study-plan/[id]` | **implemented** |
| pytest study suite | **12 passed** (focused) |
| Playwright FULL UI | **PASS** (1/1, ~29s) — evidence `frontend/test-results/study-action-flow/` |
| Gemini | Optional / absent OK |
| Google credentials | Not required to complete plan |
| Native mobile | **not verified** |

## Intent Classification Engine

| Item | Stato |
|------|--------|
| Package + AE routing via Intent | **intact** (untouched except consumption) |
| Psychology → study / exam_preparation | **working** |

## Action Engine (other flows)

| Item | Stato |
|------|--------|
| event / travel / medical / admin / generic / clarify | **unchanged** (study-only expansion) |
| Medical no-advice | **enforced** |

## Open / next

1. Run Playwright study E2E on live Expo web; archive screenshots
2. Device smoke (iOS/Android) for study plan screen
3. Wire Parla / notifications to Intent Engine
4. Harden Google create_event path across provider signatures

## Credentials / safety

- Never commit `.env` / tokens
- Study flow needs no secrets; Google/Gemini optional
