# ORA — Development State

Last updated: 2026-08-05 (Documents V2 + real Gemini/Google smoke)

## Branch

- Active: `feature/documents-v2-completion` (local, no push)
- Completion commit: `ff42f7bea2ff405ae100ce28f1428b3be03d4c0a`
- Base: `feature/rebuild-intelligent-documents` @ `3ff825d`

## Documents V2

| Item | Stato |
|------|--------|
| Hub / pipeline / study / quiz / admin / browser E2E | **complete** (see verification doc) |
| pytest `test_documents_v2.py` | **15 passed** |
| Browser Chromium E2E | **ok** |
| Gemini live (study fixture) | **verified this pass** — `ai_used`, model `gemini-flash-lite-latest` |
| Google Calendar live | **verified this pass** — Google event id `4rtfghqbv5de67vfvn32te0e3k` |
| Mobile native | **not verified** |

## Open / next

1. Device smoke (iOS/Android) for upload + study UI
2. Admin multi-document compare (still deferred)
3. Rotate OAuth client secret if it was pasted in chat (still recommended)

## Credentials / safety

- Never commit `.env` / tokens
- Rotate OAuth client secret if it was pasted in chat (still recommended)
