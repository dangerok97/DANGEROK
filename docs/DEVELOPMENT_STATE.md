# ORA — Development State

Last updated: 2026-08-06 (AI Document Understanding in Life Experience)

## Branch

- Active: `feature/life-experience-ai-documents` (local, no push)
- Base: `feature/life-experience-ai` @ `c518a23`

## AI Document Understanding in Life Experience (this branch)

| Item | Stato |
|------|--------|
| Real Expo file picker (web, Playwright-verified) | **implemented** |
| Real Documents V2 binary upload from conversation | **implemented** — replaces the prior synthetic-only `upload-doc` path for the UI flow |
| AI Document Understanding (`life_reasoning.py`, Gemini structured Pydantic) | **implemented**, real Gemini verified for rogito/bolletta/libretto/piano di studi |
| Document-type-specific reasoning (`type_specific` schema) | **implemented** for 8+ types |
| Life Profile mapping with provenance (`document_mapping.py`) | **implemented** |
| Cross-document reasoning (link/conflict/duplicate) (`cross_document.py`) | **implemented** |
| Confidence-driven field status (extracted/suggested/confirmed/corrected/rejected) | **implemented** |
| Document Result UI (Cosa ho capito / Dati trovati / Dati da verificare / Cosa posso fare) | **implemented** |
| Draft-only deadline events (no auto-create) | **implemented** (reuses Documents V2 event candidates) |
| Error/resume handling (interrupted upload, OCR failure, Gemini unavailable, timeout) | **implemented** |
| pytest `test_life_experience_documents.py` | **added, 62 passed** |
| Playwright `life-experience-documents.spec.ts` (CASA/AUTO/BOLLETTA) | **added, 3 passed** |
| Docs LIFE_EXPERIENCE_REAL_DOCUMENTS / AI_DOCUMENT_UNDERSTANDING / … | **added** |
| Mobile (iOS/Android) DocumentPicker | **NOT verified** — notes only, no device/emulator run |

## AI-first Life Experience (prior, `feature/life-experience-ai` @ `c518a23`)

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

1. Consent UI esplicita per bozze calendario dallo strategist (draft events esistono, conferma verso Google non ri-testata in questa sessione)
2. 9/13 tipi documento senza conferma Gemini reale dedicata (bolletta gas, mutuo, contratto locazione, polizza auto, prestito auto, dispensa, calendario esami, contratto, comunicazione, ricevuta — vedi `LIFE_EXPERIENCE_DOCUMENT_VERIFICATION.md`)
3. Mobile nativo (iOS/Android) DocumentPicker — non verificato su device/emulatore
4. Non aggiungere Email / Open Banking / WhatsApp / Weather come integrazioni reali qui

## Credentials / safety

- Never commit `.env` / tokens
- Strategist works without Gemini (`AI_LIFE_STRATEGIST_GEMINI=0`)
- AI cannot delete profile facts or overwrite confirmed values
