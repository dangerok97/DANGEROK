# ORA — Development State

Last updated: 2026-08-06 (Conversation Engine foundation)

## Branch

- Active: `feature/conversation-engine` (local, no push)
- Base: `feature/proactive-engine` @ `319859e`

## Conversation Engine foundation

| Item | Stato |
|------|--------|
| Package `backend/conversation_engine/` | **implemented** |
| Adapters Intent/Goal/Action/Projects/Brain/Suggestions/Maps (+ stubs) | **implemented** |
| API `/api/conversation/*` + flag `CONVERSATION_ENGINE_ENABLED` | **implemented** |
| Mongo `conversation_sessions` + indexes | **implemented** |
| Home **PARLA CON ORA** + resume Continua | **implemented** |
| Bridge to AE one-question UI (no chat bubbles) | **implemented** |
| Proactive resume interrupted CE sessions | **implemented** |
| Email / WhatsApp / Open Banking | **stubs only** |
| Real STT / voice | **NOT implemented** (mic stub → same engine with typed text) |
| Push notifications | **NOT implemented** |

## Proactive Engine (prior)

| Item | Stato |
|------|--------|
| Generators + Home ORA TI CONSIGLIA | **intact** |
| Email/Finance/Weather/Health/WhatsApp | **stubs** |

## Open / next

1. Real STT behind voice origin (same CE path)
2. Wire email/WA/open_banking connectors into stub origins (still no invented data)
3. Progress refresh on CE complete → Home focus
4. Optional richer resume copy from session artifacts

## Credentials / safety

- Never commit `.env` / tokens
- Conversation Engine needs no new secrets
- Flag off → `/api/conversation/*` disabled; PARLA fails soft
