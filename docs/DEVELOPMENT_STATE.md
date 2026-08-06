# ORA — Development State

Last updated: 2026-08-06 (Proactive Engine foundation)

## Branch

- Active: `feature/proactive-engine` (local, no push)
- Base: `feature/goal-aware-home` @ `6297bc3`

## Proactive Engine foundation

| Item | Stato |
|------|--------|
| Package `backend/proactive_engine/` | **implemented** |
| Generators Study / Travel / Calendar / Documents | **implemented** (grounded) |
| Scoring + Decision gate + Dedupe + Learning + Explain | **implemented** |
| Notification policy (no push blast) | **implemented** (policy layer only) |
| API `/api/suggestions/*` + flag `PROACTIVE_ENGINE_ENABLED` | **implemented** |
| Home `ora_ti_consiglia` max 3 + FE Accetta/Ignora/Snooze/Apri | **implemented** |
| Accept study recovery session | **implemented** (planned session; honesty documented) |
| Email / Finance / Weather / Health | **predisposed stubs only** — never invent |
| WhatsApp | **NOT implemented** |
| Push notifications | **NOT implemented** (policy defers) |

## Goal-aware Home V2 (prior)

| Item | Stato |
|------|--------|
| Goal attach / dedupe / ranking 1.2 / Adesso context | **intact** |
| Goal tab / Goals Home section | **NOT implemented** (by design) |

## Open / next

1. Wire real email/finance/weather connectors into stub generators (still gate ruthlessly)
2. Progress refresh on session complete / travel phase tick
3. Optional FE Goals read surface (later)
4. Push channel behind notification policy (opt-in)

## Credentials / safety

- Never commit `.env` / tokens
- Proactive Engine needs no new secrets
- Flag off → no suggestions; Home section empty
