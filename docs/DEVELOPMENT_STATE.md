# ORA — Development State

Last updated: 2026-08-07 (Life Object AI narrative/reasoning enrichment)

## Branch

- Active: `feature/life-object-engine` (tip ~`253fa65` + enrichment commit)
- No push / no merge

## Life Object Engine (this batch — AI enrichment)

**Framing:** Life Objects = modello canonico. Satelliti restano. Home UX **invariata**.

| Item | Stato |
|------|--------|
| Identity vs State split | **implemented** (migrazione non distruttiva da `properties`) |
| AI Narrative (versionata) | **implemented** — Gemini opzionale + fallback IT |
| AI Questions | **implemented** — refresh su nuove fonti |
| AI Insights | **implemented** — da storia completa |
| Temporal reasoning | **implemented** — presente vs storia |
| Life Health explainable | **implemented** — completeness/reliability/missing/opportunities/risks/reasons |
| API narrative/questions/insights/health/history/relationships/enrich | **implemented** |
| Home V3 DTO interno | **PREDISPOSTO** (`home-v3-feed`, flag OFF) |
| Home UX / schermata Life Objects | **NON toccata** |
| Gemini | **opzionale** — pytest con `LIFE_OBJECT_GEMINI=0` |

## Prior (shadow core — ancora valido)

| Item | Stato |
|------|--------|
| Package + dedupe + reasoner + shadow hooks | **implemented** |
| `LIFE_OBJECT_ENGINE_ENABLED=1` / `HOME_UI=0` | **yes** |
| Altri motori eliminati? | **NO** — satelliti / fonti |
| Goal-aware Home | **unchanged** |

## Open / next

1. Home V3 Life Objects UI (solo quando `LIFE_OBJECT_HOME_UI_ENABLED=1`) — **non fare ora**
2. Conversation/Proactive: suggerimenti guidati da oggetti (light)
3. Merge UI quando `propose_merge`
4. Non aggiungere Email / Open Banking / WhatsApp / Weather come integrazioni reali qui

## Credentials / safety

- Never commit `.env` / tokens
- CI green senza secret a pagamento; Gemini gated / fallback
- AI cannot invent Life Object facts; no silent Casa 2
- Privacy: contesto Gemini minimale, no secrets
