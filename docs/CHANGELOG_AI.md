# ORA — AI Changelog

## 2026-08-05 — Intent Classification Engine (flow router brain)

### Request

Critical rebuild: wrong flow for “devo studiare l'esame di psicologia” (event/ticket). Replace Action Engine text/type heuristics with reusable Intent Classification Engine; tests ≥100 phrases; Playwright; docs; local commit; no push.

### Actions

- Branch `feature/intent-classification-engine` from `feature/ora-action-engine` @ `6b3831b`
- Package `backend/intent_engine/` (KB, deterministic classifier, entities, optional LLM enricher, mapping, `POST /api/intent/classify`)
- Restructured `action_engine` open path: Intent → flow registry; clarify flow; persist Intent on decisions
- Home decisions adapter + FE labels prefer Intent; decision create classifies on write
- Corpus 124 IT phrases; pytest **147 passed**; Playwright `intent-psychology.spec.ts` **1 passed**
- Docs: `INTENT_ENGINE_*.md` + PRODUCT / ARCHITECTURE / DEVELOPMENT_STATE; `.env.example` `INTENT_LLM_ENRICH`

### Result

Psychology phrase → study / exam_preparation → first question exam date (never ticket). Works without Gemini. No push/merge.

### Open

- Wire Parla / email / notifications to same Intent brain
- Native mobile re-verify

---

## 2026-08-05 — Verify Action Engine collaborative feel (Playwright)

### Request

Verify guided flow on live backend + Expo web: Inizia → first question/chips → multi-step answers → Home evolves. Commit only if Playwright/docs evidence added.

### Actions

- Confirmed tip `cca0acb`; restarted stale uvicorn (was 404 on `/action-engine`) and Expo web for `/action/*`
- Added `frontend/e2e/action-engine.spec.ts`
- Playwright **1 passed** (~19–24s); screenshots + `smoke-log.json` under `frontend/test-results/action-engine-smoke/`
- Updated `docs/ACTION_ENGINE_VERIFICATION.md`, DEVELOPMENT_STATE

### Result

**PASS** collaborative feel on Expo web: not blank; 3 UI chip steps; Home primary became «Sessione 1: Esame Analisi E2E». Native still unverified.

---

## 2026-08-05 — ORA Action Engine (guided priority flows)

### Request

Build core Action Engine from `feature/home-v2-intelligence` @ `01e50de`: central guided flows for Home Apri/Organizza/Inizia (never empty page), Brain/projects/calendar hooks, tests, docs, local commit only.

### Actions

- Branch `feature/ora-action-engine` from Home V2 tip
- Backend package `action_engine/` (flows, service, brain, projects, effects, router)
- Home catalog + adapter wired to Action Engine; frontend `ActionEngine.open` + conversational screen
- Docs: `ACTION_ENGINE_*.md` + PRODUCT / ARCHITECTURE / DEVELOPMENT_STATE / FUNCTIONAL_AUDIT / BACKLOG
- Tests: `tests/test_action_engine.py` **11 passed**; regression `test_home_v2` + `test_documents_v2` **36 passed**; `npx tsc --noEmit` **OK**; `compileall action_engine` **OK**

### Result

Action Engine implemented. Empty Apri fixed in code paths (guided entry via `ActionEngine.open`); full device/web collaborative feel **must be manually verified**. No push/merge. Google login untouched.

---

## 2026-08-05 — Rebuild Home as ORA intelligence dashboard

### Request

Rebuild Home V2 on branch from Documents V2 completion: real ranking dashboard, `/api/home`, type-specific UI, remove seed/static/dead CTAs, Expo web + Playwright, docs, local commit only.

### Actions

- Branch `feature/home-v2-intelligence` from `feature/documents-v2-completion` @ `03028dc`
- Backend package `home/` (models, ranking `home-rank-1.0`, adapters, service, router)
- Frontend Home rewrite + `/situazione` + `components/home/v2/*`
- Removed large Google hero, 100/100, Dopo numbering from Home
- Tests: `tests/test_home_v2.py` (21 passed); Playwright `e2e/home-v2.spec.ts`
- Docs: HOME_V2_*, PRODUCT, ARCHITECTURE, DEVELOPMENT_STATE, FUNCTIONAL_AUDIT, ROADMAP, BACKLOG

### Result

Home V2 implemented and backend-tested. Native mobile **not** claimed.

---

## 2026-08-05 — Documents V2 real Gemini + Google Calendar smoke

### Request

Follow-up after completion commit: confirm whether Gemini and Google Calendar live paths were verified; run minimal real smokes if credentials present; document honestly.

### Actions

- Confirmed branch `feature/documents-v2-completion` @ `ff42f7b`
- Ran `backend/scripts/smoke_documents_v2_real.py`
- Gemini: study fixture analyzed with `ai_used=true`, model `gemini-flash-lite-latest`
- Google: synthetic concert confirmed; Google event id `4rtfghqbv5de67vfvn32te0e3k` (`sync_status=synced`)
- Updated `DOCUMENTS_V2_VERIFICATION.md`, `DEVELOPMENT_STATE.md`, this changelog

### Result

Both live smokes **passed** this pass. Mobile still not verified.

---

## 2026-08-05 — Complete and verify intelligent Documents V2

### Request

Finish Documents V2: dynamic detail by macro, study tools (flashcards, Interrogami), admin actions, auto-add gates, provenance, Brain/search, fixtures, real browser E2E, tests, docs, local commit only.

### Actions

- Branch `feature/documents-v2-completion` from `3ff825d`
- Backend: `study_tools.py`, `admin_extract.py`, study/quiz/admin routes, provenance merge on reanalyze, stricter auto-add, richer search
- Frontend: wire `TabInfo` → `DocumentUtilityPanel`; editable admin fields; client types
- Tests: expanded `test_documents_v2.py` (15 passed)
- Browser: Playwright Chromium E2E vs Expo web (flashcards/quiz/dynamic detail verified)
- Docs: DOCUMENTS_V2_*, DEVELOPMENT_STATE, FUNCTIONAL_AUDIT, BACKLOG, this changelog

### Tests / verify

- pytest V2: 15 passed
- tsc --noEmit: OK
- compileall intelligence: OK
- Browser E2E: ok (see `docs/DOCUMENTS_V2_VERIFICATION.md`)
- Gemini live / Google live: not re-run this session
- Mobile: not verified

### Result

Documents V2 completion criteria met for web: flashcards, Interrogami, dynamic detail, and real browser E2E verified. Mobile and live Gemini re-check remain open.

---

## 2026-08-05 — Rebuild Documents as intelligent actions engine (V2)

### Request

Replace archival Documents UX with dynamic intelligent pipeline: classify, utility, calendar auto-add opt-in, Brain, Maps, non-destructive migration, full docs, local commit.

### Actions

- Branch `feature/rebuild-intelligent-documents` from Google Calendar sync work
- Pipeline V2 states + version fields; hub + preferences APIs; auto-add gates
- FE hub rebuild; detail utility tabs; settings auto-add
- Docs `DOCUMENTS_V2_*.md` + product/state updates
- Tests `test_documents_v2.py`

### Result

Module reframed as actions engine; data preserved. Advanced study flashcards / multi-doc compare deferred.

---

## 2026-08-05 — Google Calendar write sync (document events)

### Request

Integrate ORA internal calendar with real Google Calendar write when user confirms a document event. Separate login OAuth from Calendar OAuth. Encrypt tokens. Conflict/idempotency/privacy. Commit local only.

### Actions

- Branch `feature/google-calendar-sync` from `a12fae3`
- Scopes: `calendar.events` + `calendar.calendarlist.readonly` (+ openid/email/profile)
- Vault: `TOKEN_VAULT_BACKEND=local` alias Fernet; `OAUTH_TOKEN_ENCRYPTION_KEY` accepted
- Provider write API + `GoogleCalendarSyncService` (create/update/delete/conflict/idempotency)
- Confirm event: `sync_to_google`; draft sync fields
- API under `/api/documents/calendar/google/*` and draft sync/retry/conflict/delete
- UI: document “Salva solo in ORA” / “ORA + Google Calendar”; Settings write status + reconnect
- Docs: `GOOGLE_CALENDAR_{ARCHITECTURE,SETUP,VERIFICATION,PRIVACY}.md` + product/arch/state updates

### Tests

- `tests/test_google_calendar_write_sync.py` (fake provider — not real Google)
- Real Google event creation: **not run** (missing `GOOGLE_OAUTH_CLIENT_*`)

### Result

Code path complete for local/fake verification. **Integration not complete** until a synthetic event appears on real Google Calendar.

### Open issues

- Configure Google OAuth client + complete real verification checklist
- Users with old read-only scopes must reconnect
- Mobile native Calendar connect not verified

---

## 2026-08-05 — Migrate Gemini provider to google-genai

### Request

Non-functional migration from deprecated `google.generativeai` to official `google.genai`. Keep behavior, schemas, fallback, Provider Manager, tests, `GEMINI_API_KEY`, configurable model.

### Actions

- Branch `chore/migrate-gemini-sdk` from `80a4300`
- Rewrote `backend/llm/providers/gemini.py` → `google.genai.Client` (API key only)
- Model chain: `GEMINI_MODEL` → alternate → Provider Manager failover; usage telemetry without prompts/keys
- Removed `google-generativeai` from venv + `requirements.txt` / `requirements-local.txt`; kept `google-genai==2.15.0`
- Updated unit mocks; docs + `.env.example` (`GEMINI_FALLBACK_MODEL`)

### Tests

- `pytest tests/test_ai_provider_manager.py` → 9 passed (incl. real Gemini optional)
- Broader: `test_ai_provider_manager` + iter15 + iter17 → 35 passed
- Real smoke fixtures concerto/dispensa/admin/visita → **4/4 ai_used** (`gemini-flash-lite-latest`, `google-genai`)
- `compileall` llm; frontend `tsc --noEmit` OK

### Result

Migration complete; old SDK unused/removed; real Gemini success confirmed on new SDK.

### Open issues

- Rotate Gemini key (exposed in prior session chat)
- OpenAI real failover still blocked by quota
- Optional cleanup of leftover `google-ai-generativelanguage` pin

---

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
