# ORA — Development State

Last updated: 2026-08-05 (Home V2 intelligence dashboard)

## Branch

- Active: `feature/home-v2-intelligence` (local, no push)
- Base: `feature/documents-v2-completion` @ `03028dc` (includes `ff42f7b` Documents V2 completion)

## Home V2

| Item | Stato |
|------|--------|
| Aggregator `GET /api/home` + actions + situation | **implemented** |
| Deterministic ranking `home-rank-1.0` (no Gemini required) | **implemented** |
| Frontend Home blocks (Adesso → resume) | **implemented** |
| Large Google card / 100/100 / Dopo numbering | **removed from Home** |
| pytest `test_home_v2.py` | **21 passed** |
| Expo web + Playwright | **2 passed** (`e2e/home-v2.spec.ts`) |
| Native mobile Home V2 | **not verified** |

## Documents V2

| Item | Stato |
|------|--------|
| Hub / pipeline / study / quiz / admin | **complete** (base branch) |
| Mobile native | **not verified** |

## Open / next

1. Device smoke (iOS/Android) for Home V2 + Documents
2. Wire more Brain/Memory signals into ORA osserva when real patterns exist
3. Rotate OAuth client secret if it was pasted in chat (still recommended)

## Credentials / safety

- Never commit `.env` / tokens
- Home ranking works without LLM keys
