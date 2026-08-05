# ORA — Development State

Last updated: 2026-08-05 (Documents V2 completion)

## Branch

- Active: `feature/documents-v2-completion` (local, no push)
- Base: `feature/rebuild-intelligent-documents` @ `3ff825d`
- Ancestor Google Calendar: `213ea4f` (real Google create/update verified earlier)

## Documents V2

| Item | Stato |
|------|--------|
| Hub API + prefs (auto-add default off) | **implementato + verified API** |
| Pipeline states V2 + migration stamp | **implementato + verified API** |
| FE hub `documenti.tsx` | **implementato + verified browser** |
| FE detail `DocumentUtilityPanel` by macro | **implementato + verified browser** |
| Study tools + flashcards + Interrogami | **implementato + verified API + verified browser** |
| Admin extract + complete + deadline + edit | **implementato + verified API** |
| Provenance survive reanalyze | **implementato + verified API** |
| Auto-add gates (0.89, multi, ambiguous, dedupe) | **implementato + verified API** |
| Intelligent search + user isolation | **implementato + verified API + browser search** |
| Synthetic fixtures intel_docs | **verified API**; study+event **verified browser** |
| pytest `test_documents_v2.py` | **15 passed** |
| Browser Chromium E2E | **ok** (`e2e_documents_v2_browser.py`) |
| Google Calendar live | prior session verified; **not re-run** this session |
| Gemini live | **not verified this session** |
| Mobile native | **not verified** |

## Open / next

1. Device smoke (iOS/Android) for upload + study UI
2. Optional Gemini real smoke on fixtures when key present
3. Re-verify Google confirm on connected account after OAuth secret rotation
4. Admin multi-document compare (still deferred)

## Credentials / safety

- Never commit `.env` / tokens
- Rotate OAuth client secret if it was pasted in chat (still recommended)
