# ORA — Development State

Last updated: 2026-08-06 (AI-first Life Experience)

## Branch

- Active: `feature/life-experience-ai` (local, no push)
- Base: `feature/ai-life-setup-foundation` @ `b68cbdc`

## AI-first Life Experience

| Item | Stato |
|------|--------|
| Reasoning loop (`reasoning_loop.py`) | **implemented** |
| Gemini structured context + task IT | **implemented** |
| Deterministic Italian fallback | **implemented** |
| Domini in qualsiasi ordine (benefit/gain) | **implemented** |
| Document strategy (rogito, libretto, piano di studi, …) | **implemented** |
| Home benefit cards italiane | **implemented** |
| Proactive benefit suggestions | **implemented** |
| asked / refused / postponed memory | **implemented** |
| pytest `test_life_experience.py` | **added** |
| Playwright `life-experience-ai.spec.ts` | **added** |
| Docs LIFE_EXPERIENCE / AI_REASONING_LOOP / … | **implemented** |
| Email/Banking/WhatsApp/Weather | **stubs only** |

## Prior (intact)

- AI Life Setup foundation @ `b68cbdc`
- Semantic Extraction + Gap Analyzer
- Conversation Engine / Proactive / Goal / Home / Intent / Action

## Open / next

1. Upload binario Documents V2 reale dalla conversazione (oltre path sintetico e2e)
2. Consent UI esplicita per bozze calendario dallo strategist
3. Non aggiungere Email / Open Banking / WhatsApp / Weather come integrazioni reali qui

## Credentials / safety

- Never commit `.env` / tokens
- Strategist works without Gemini (`AI_LIFE_STRATEGIST_GEMINI=0`)
- AI cannot delete profile facts or overwrite confirmed values
