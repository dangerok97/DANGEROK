# ORA — Development State

Last updated: 2026-08-05 (Travel Action Flow — first Life Planner slice)

## Branch

- Active: `feature/travel-action-flow` (local, no push)
- Base: `feature/complete-study-action-flow` @ `eca96af`

## Travel Action Flow (Life Planner slice)

| Item | Stato |
|------|--------|
| Intent travel/vacation + period extract | **implemented** |
| Conversational missing-only + preview/confirm | **implemented** |
| TravelProject model + calendar propose | **implemented** |
| Google sync only after confirm (`calendar_google`) | **implemented** |
| Maps deep link + honest estimates | **implemented** |
| Home phases (upcoming→welcome_back) | **implemented** |
| Brain trip↔destination↔docs | **implemented** |
| Prep optional; weather/email honest stubs | **implemented** |
| FE `/travel-project/[id]` + AE preview | **implemented** |
| pytest travel suite | **12 passed** |
| Playwright travel UI | **authored** — run when servers up |
| Google live travel events | **optional manual** |
| Weather / email auto-find / native mobile | **not verified / not implemented** |

## Study Action Flow

| Item | Stato |
|------|--------|
| Full study plan E2E + Google sync verify | **intact** (prior branch) |
| Playwright study FULL UI | **PASS** (prior) |

## Intent Classification Engine

| Item | Stato |
|------|--------|
| Package + AE routing via Intent | **intact** (+ travel period entities) |

## Action Engine (other flows)

| Item | Stato |
|------|--------|
| event / medical / admin / generic / clarify | **unchanged** |
| travel | **upgraded** to Travel Project confirm path |
| Medical no-advice | **enforced** |

## Open / next

1. Playwright travel E2E with servers running + evidence screenshots  
2. Live Google travel sync for connected test user + cleanup  
3. Device smoke (iOS/Android) for travel project screen  
4. Weather API when credentials available (honest until then)  
5. Email auto-find module (hook only today)

## Credentials / safety

- Never commit `.env` / tokens  
- Travel flow needs no secrets; Google/Nominatim/weather optional  
- Never invent weather/traffic/medical advice  
