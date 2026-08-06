# ORA — Development State

Last updated: 2026-08-06 (Life Object Engine — shadow core)

## Branch

- Active: `feature/life-object-engine` (from `feature/life-experience-ai-documents` @ `b80d18a`)
- No push / no merge

## Life Object Engine (this batch)

**Framing:** Life Objects = modello canonico della realtà utente. Conversation / Goal / Documents / Brain / Proactive / Home **non eliminati** — satelliti che leggono/scrivono oggetti.

| Item | Stato |
|------|--------|
| Package `backend/life_objects/` | **implemented** |
| Model + types (HOME/VEHICLE/…) | **implemented** |
| Dedupe (address/cadastral/POD/plate/…; never title alone) | **implemented** |
| Reasoner Gemini + deterministic fallback | **implemented** |
| Shadow hooks: Documents / Goal / Travel / Study | **implemented** |
| API `/api/life-objects` | **implemented** (unused by main UI) |
| `LIFE_OBJECT_ENGINE_ENABLED` default ON | **yes** |
| `LIFE_OBJECT_HOME_UI_ENABLED` default OFF | **yes** — Home UX unchanged |
| Home V3 Life Objects view | **PREDISPOSTO / NOT shipped** (SHADOW) |
| Unit tests Casa/Auto/merge/flag/isolation | **added** |
| Playwright shadow API (single HOME) | **added** (extends life-experience-documents) |
| Altri motori eliminati? | **NO** — restano satelliti / fonti |

## Prior on documents branch (still valid)

| Item | Stato |
|------|--------|
| AI Document Understanding v2 | **implemented** |
| Real Expo file picker + Documents V2 | **implemented** |
| Goal-aware Home | **unchanged** (still primary Home) |
| Gemini live smoke docs | **optional** gated |

## Open / next

1. Home V3 Life Objects UI (solo quando `LIFE_OBJECT_HOME_UI_ENABLED=1`) — **non fare ora**
2. Conversation/Proactive: suggerimenti guidati da oggetti (light)
3. Trend bollette multi-periodo più ricco
4. Merge UI quando `propose_merge`
5. Non aggiungere Email / Open Banking / WhatsApp / Weather come integrazioni reali qui

## Credentials / safety

- Never commit `.env` / tokens
- CI green senza secret a pagamento; Gemini gated
- AI cannot invent Life Object facts; no silent Casa 2
