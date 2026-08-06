# ORA — Development State

Last updated: 2026-08-06 (AI Life Setup + AI Life Strategist foundation)

## Branch

- Active: `feature/ai-life-setup-foundation` (local, no push)
- Base: `feature/semantic-extraction-gap-analyzer` @ `8cddcac` (history includes `a7cae9e`)

## AI Life Setup + Strategist

| Item | Stato |
|------|--------|
| Package `backend/ai_life_strategist/` | **implemented** |
| Package `backend/life_setup/` (+ Life Profile) | **implemented** |
| Structured StrategistPlan (Pydantic) | **implemented** |
| Gemini via Provider Manager + deterministic fallback | **implemented** |
| API `/api/life-setup/*` + `/api/strategist/*` | **implemented** |
| FE `/life-setup` natural conversation (not wizard) | **implemented** |
| First-launch gate in `app/index.tsx` | **implemented** |
| Sync Life Graph / Goal shadow / Proactive / Home | **implemented** |
| Email/Banking/WhatsApp/Weather | **stubs only** |
| pytest foundation suite | **run in session** |
| Playwright `life-setup-strategist.spec.ts` | **added** |
| Docs LIFE_SETUP_* / AI_LIFE_STRATEGIST / LIFE_PROFILE / … | **implemented** |

## Prior (intact)

- Semantic Extraction + Gap Analyzer
- Conversation Engine / Proactive / Goal / Home / Intent / Action

## Open / next

1. Richer Documents V2 upload UX from Life Setup (beyond synthetic/e2e path)
2. Calendar drafts from strategist only with explicit consent UI
3. Do **not** add Open Banking / Email / WhatsApp / Weather as real integrations here

## Credentials / safety

- Never commit `.env` / tokens
- Strategist works without Gemini (`AI_LIFE_STRATEGIST_GEMINI=0` → deterministic planner)
- AI cannot delete profile facts or overwrite confirmed values
