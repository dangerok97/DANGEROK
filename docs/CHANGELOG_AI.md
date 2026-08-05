# ORA — AI Changelog

## 2026-08-05 — Gemini real verification on synthetic docs

### Request

Store `GEMINI_API_KEY` locally and verify Provider Manager with real Gemini.

### Actions

- Key in gitignored `backend/.env` only
- Default model → `gemini-flash-lite-latest` (`gemini-2.0-flash` hit 429)
- Coerce Gemini dict-shaped `definitions` into list for Pydantic
- Honest docs update

### Tests

- Real Gemini AI enrich: concerto, dispensa, admin, visita — **4/4 ai_used**
- Avg latency ~1.6–2.6s; provider `gemini`; no failover needed on success path

### Result

Gemini verified as default working provider for document intelligence (free-tier lite model).

---

## 2026-08-05 — Multi-provider Manager with Gemini default

### Request

Provider-agnostic AI: Gemini default, keep OpenAI, add Ollama, Emergent optional, failover, settings UI.

### Actions

- `backend/llm/manager.py` + adapters (`gemini`, `openai`, `ollama`, `emergent`)
- Common interface (`chat`, analyze/classify/summarize/ask/extract_*)
- API `GET /api/llm/providers`, `PATCH /api/llm/preferences` (no restart)
- Settings → AI Provider radios
- Docs `AI_PROVIDER_MANAGER.md`; `.env.example` updated
- OpenAI retained; Gemini preferred in priority chain

### Tests

- `test_ai_provider_manager.py` (failover mock) + intel suite green
- Real Gemini: later verified (see entry above)
- OpenAI: configured but quota exceeded

### Result

Architecture multi-provider ready; Gemini subsequently verified with flash-lite.

---

## 2026-08-05 — Real verification of intelligent documents

### Request

Portare Documenti da “fixture mock” a verifica reale (OpenAI, OCR, formati, UI, Brain, calendario interno, worker). No Google Calendar.

### Actions

- Branch `feature/intelligent-documents-real-verification`
- Structured LLM (`llm/structured.py`, Pydantic enrichment), cost controls, content-hash dedupe
- OCR host path + scanned PDF fallback; DOCX/PPTX extractors
- Worker locks / recovery / max attempts
- Synthetic fixtures A–F + OCR/office samples
- Docs matrix + privacy/architecture/verification updates

### Tests

- pytest intel suites: 28 passed, 1 skipped (real OpenAI)
- Real OCR verified (Tesseract)
- HTTP upload/analyze/confirm/ask/maps/isolation
- Real OpenAI: **not run** (API key absent)

### Result

Local+OCR+HTTP verification advanced; OpenAI real enrichment still blocked by credentials.

---

## 2026-08-05 — Intelligent document understanding and actions

### Request

Evolvere Documenti: pipeline, classificazione, event candidate, studio, Brain, calendario interno, Maps, UI.

### Actions

- Branch `feature/intelligent-documents`
- `backend/documents/intelligence/*` (pipeline, taxonomy, analyzer, worker, calendar adapter)
- API analyze / events / ask / search / calendar drafts
- FE detail: stato, evento, studio, ask; list titles/status
- Docs INTELLIGENT_DOCUMENTS_*
- No Google Calendar write

### Tests

- `test_intelligent_documents.py` + documents local: 13 passed
- tsc OK

### Result

Archivio esistente preservato; comprensione strutturata locale verificata con fixture; AI esterna opzionale.

---

## 2026-08-04 — Unified Google and Apple authentication

### Request

Consolidare autenticazione sociale (Google, Apple, email) con identità unica ORA, verifica backend, linking sicuro.

### Actions

- Branch `feature/social-auth`
- Package `backend/social_auth/` (JWKS verify, identities, link/unlink, migrate password)
- Endpoint `/api/auth/google|apple|link/*|identities|providers`
- FE: expo-auth-session / apple-authentication; login + settings metodi di accesso
- Docs `SOCIAL_AUTH_*`; env examples; gitignore `.p8`
- Legacy Emergent `google-session` resta gated

### Tests

- pytest social + smoke: 19 passed (mock claims; non prove reali provider)
- tsc OK
- Real Google/Apple E2E: bloccati da credenziali

### Result

Codice completato; verifica reale provider in attesa secret utente.

---

## 2026-08-04 — Documents UI alignment + verified workflow

### Request

Correggere BACKLOG-001 (label “In arrivo”) e verificare end-to-end il modulo Documenti su branch `feature/documents-ui-alignment`.

### Actions

- Branch locale `feature/documents-ui-alignment` da `ora/cursor-platform` (no push)
- Profilo: Documenti in “IL TUO SPAZIO” → tab documenti
- Aggiungi: Documento attivo (“Carica un file”); Foto resta “In arrivo”
- Documenti: filtro `archived` booleano; post-upload → dettaglio; empty upload loading/disabled
- pytest `backend/tests/test_documents_local.py` (auth, isolation, mime, 404, empty, roundtrip)
- `.gitignore`: `backend/data/` (blob locali)
- Docs: `DOCUMENTS_VERIFICATION.md` + aggiornamenti audit/backlog/state

### Tests

- pytest documents + local smoke: 11 passed
- tsc `--noEmit`: OK
- expo lint: 0 errors
- HTTP persistenza post re-login: OK
- Browser web: Profilo/Aggiungi labels + Documenti empty state

### Result

Release locale piccola: UI coerente + workflow documenti verificato (web/API). Native non verificato.

### Open issues

- File picker UI non automatizzato end-to-end
- Insights/actions UI non tutte cliccate
- Storage solo locale

---

## 2026-08-04 — Functional audit + product roadmap

### Request

Full functional verification (no new features) and roadmap/backlog docs.

### Actions

- Inventory of screens, APIs, DB, integrations
- HTTP audit script: 30/30 checks (auth, decisions, memory, daily, docs list, calendars gated, registries)
- pytest `test_local_smoke.py`: 5 passed
- UI web: login, home with seeded decisions, aggiungi, documenti empty, memoria, profilo, settings, how-it-works
- Updated `docs/PRODUCT.md`; created `FUNCTIONAL_AUDIT.md`, `ROADMAP.md`, `BACKLOG.md`

### Tests

- HTTP functional suite (ad hoc): 30 passed
- pytest local smoke: 5 passed
- UI navigation (authenticated web session)

### Result

Documentation-only delivery; recommended next: BACKLOG-001 UI coherence.

### Open issues

- LLM / Google OAuth still credential-gated
- Document upload not re-verified in this UI pass
- Native mobile not verified

---

## 2026-08-04 — Verified local development without Emergent

### Request

First verified local boot of ORA; isolate Emergent blockers; commit platform + fix.

### Actions

- Commit 1: Cursor autonomous platform scaffold
- Installed Python 3.12 + MongoDB Server via winget
- Added `backend/requirements-local.txt` (no Emergent packages)
- LLM adapter `backend/llm/` (`none`/`openai`/`emergent`)
- Made `EMERGENT_LLM_KEY` optional at boot
- Added `GET /api/health`
- Gated Emergent Google login (`EMERGENT_GOOGLE_AUTH`)
- Honest Google button message on FE
- Fixed Windows `preinstall` (`node ./scripts/cmd-guard.js`)
- cmd-guard skip via `ORA_SKIP_CMD_GUARD`
- Local `.env` files (gitignored) with generated JWT
- Smoke tests `tests/test_local_smoke.py`
- Fixed `tokens.color.danger` → `error`
- docker-compose.yml for optional Mongo
- Docs/README updated

### Tests

- `pytest tests/test_local_smoke.py -n 0` → **5 passed**
- Live HTTP: `/api/`, `/api/health`, register, google-session 503
- `tsc --noEmit` → OK
- `compileall` → OK
- Expo web: Metro bundled, HTTP 200 on `:8081`

### Result

Local backend + Mongo + Expo web verified without Emergent runtime.

### Open issues

- AI features need an LLM API key
- Google login/calendar need OAuth credentials
- Mobile native not verified this session

---

## 2026-08-04 — Cursor autonomous platform bootstrap

### Request

Configure Cursor as Emergent-like autonomous platform; analysis then automation files.

### Result

`AGENTS.md`, `.cursor/*`, docs, scripts, env examples on `ora/cursor-platform`.
