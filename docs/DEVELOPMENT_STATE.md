# ORA — Development State

Last updated: 2026-08-06 (Home Presentation Aggregation)

## Branch

- Active: `feature/home-goal-presentation-dedupe` (local, no push)
- Base: `feature/conversation-engine` @ `e1cbe43`

## Home Presentation Aggregation

| Item | Stato |
|------|--------|
| `backend/home/presentation.py` one card / Goal | **implemented** |
| `GET /api/home` presentation fields | **implemented** |
| Priorities max one / Goal; resume/suggestion/CE fold-in | **implemented** |
| Legacy audit/migrate `scripts/audit_home_goal_links.py` | **implemented** (non-destructive) |
| Backend tests `test_home_presentation_aggregation.py` | **implemented** (≥13) |
| Playwright `home-presentation-dedupe.spec.ts` | **implemented** |
| Docs HOME_PRESENTATION_AGGREGATION / HOME_DEDUPLICATION_VERIFICATION | **implemented** |

## Conversation Engine (prior)

| Item | Stato |
|------|--------|
| Package `backend/conversation_engine/` | **intact** |
| Home PARLA CON ORA + CE resume | **intact** (CE for a Goal → action on Goal card, not duplicate card) |

## Proactive Engine (prior)

| Item | Stato |
|------|--------|
| Generators + Home ORA TI CONSIGLIA | **intact** (deduped vs Goal presentation cards) |
| Email/Finance/Weather/Health/WhatsApp | **stubs** |

## Open / next

1. Real STT behind voice origin (same CE path)
2. Wire email/WA/open_banking connectors into stub origins
3. Richer study card flashcard counts when tools linked
4. Optional Google `ora_goal_id` write on sync for stronger calendar attach

## Credentials / safety

- Never commit `.env` / tokens
- Presentation layer needs no new secrets
- Legacy migration never auto-deletes artifacts
