# ORA — AI Changelog

## 2026-08-06 — Proactive Engine foundation

### Request

Build ORA Proactive Engine foundation on `feature/proactive-engine` from `feature/goal-aware-home` @ `6297bc3`. Decide IF/WHEN/HOW/WHY to intervene; Home **ORA TI CONSIGLIA** max 3; Email/Finance/Weather/WhatsApp predisposed only.

### Actions

- Package `backend/proactive_engine/` (models, generators, scoring, decision gate, notification policy, learning, explain, dedupe, lifecycle, accept, repo, service, router)
- Real generators: study (skip→recovery), travel (≤7d prep), calendar (overlap), documents (education→flashcards path)
- Stub generators: emails/finance/weather/health always empty
- Mount `/api/suggestions/*`; flag `PROACTIVE_ENGINE_ENABLED` (default ON); indexes on startup
- Home `ora_ti_consiglia` + FE `OraTiConsiglia` (Accetta/Ignora/Ricordamelo/Apri)
- Fixtures `backend/tests/fixtures/proactive_scenarios.json` (~224 scenarios)
- Docs: PROACTIVE_ENGINE_PRODUCT/ARCHITECTURE, SUGGESTION_MODEL, DECISION_ENGINE; ROADMAP/ARCHITECTURE/DEVELOPMENT_STATE/HOME updates

### Results

- pytest `test_proactive_engine.py`: **232 passed** (224 fixture scenarios + focused tests)
- `compileall proactive_engine` OK; `tsc --noEmit` OK
- Playwright `e2e/proactive-engine.spec.ts` vs `:8011`: **2 passed** (skip→Home→Accept recovery; stubs never invent)
- Secret scan: only E2E test password literal (same pattern as other e2e)
- Email/Finance/Weather/Health/WhatsApp: **not** claimed complete
- Commit: `feat: introduce proactive engine foundation`

---

## 2026-08-06 — Goal-aware Home complete (full checklist)

### Request

Align/complete Goal-aware Home against full checklist on `feature/goal-aware-home` (base `a702d1e` / Foundation `7352f7c`). No Goal UX. Commit message exactly `feat: make Home goal-aware`.

### Gaps filled vs `a702d1e`

- Schema refs: `goal_type`, `goal_target_date`, `goal_blockers`, `goal_project_id` (+ existing fields)
- Ranking bumped `home-rank-1.1` → `home-rank-1.2` (blockers/status/stale/skipped/prep/calendar; travel soft progress)
- Primary focus enrich (`Obiettivo:` / Blocco); idle Goal proposal; resume ≠ same-goal duplicate
- AdessoCard: obiettivo/progresso/target/next/stato/blocchi; travel no fake %
- Tests expanded (≥12 checklist cases); Playwright Study/Travel + refresh/logout
- Canonical doc `docs/GOAL_AWARE_HOME.md`; `HOME_GOAL_AWARE.md` alias; FUNCTIONAL_AUDIT + HOME_V2_* / FOUNDATION / DEVELOPMENT_STATE

### Results

- Goal UX: **NOT implemented**
- pytest `test_home_goal_aware` + `test_home_v2`: **39 passed**
- pytest `test_goal_engine`: **9 passed**
- `compileall home` OK; `tsc --noEmit` OK
- lint: pre-existing `settings.tsx` unescaped-entities error (unrelated); no new errors in Home files
- Playwright `e2e/home-goal-aware.spec.ts` vs `:8010` (GOAL_ENGINE_ENABLED): **2 passed**
- Secret scan on touched paths: clean

### Commit

`feat: make Home goal-aware`

---

## 2026-08-06 — Goal-aware Home V2 (no Goal UX) — initial

### Request

Make Home V2 Goal-aware for primary focus, next action, progress, motivation, dedupe, resume, insights — without Goal tab/list/module UX. Branch `feature/goal-aware-home` from Goal Engine Foundation `7352f7c`.

### Actions

- Added `backend/home/goal_context.py` (load/attach/dedupe/insights/resume enrich/ranking delta)
- Wired into `HomeService.build_home` + `ranking.py` (`home-rank-1.1`); adapters pass `meta.goal_id`
- Minimal FE: optional progress field on Adesso + `HomeItem` goal_* types
- Docs: `HOME_GOAL_AWARE.md` + HOME_V2_* / GOAL_ENGINE_* / ARCHITECTURE / DEVELOPMENT_STATE
- Tests: `test_home_goal_aware.py`; Playwright `e2e/home-goal-aware.spec.ts`

### Results

- Goal UX: **NOT implemented** (confirmed — no Goals section/tab)
- Flag OFF: no `goal_*` on Home items
- Same Goal → single focus/priority representative
- pytest `test_home_goal_aware` + `test_home_v2` + `test_goal_engine`: **38 passed**
- pytest study + action_engine regression: **22 passed**
- Playwright `e2e/home-goal-aware.spec.ts`: **2 passed** (API assert on `:8003`)

### Commit

`a702d1e` — `feat: make Home V2 Goal-aware without Goal UX`

---

## 2026-08-06 — Goal Engine Foundation (shadow, backend-only)

### Request

Implement ORA Goal Engine Foundation: invisible backend layer, shadow Goals on Study/Travel confirm, API unused by UI, no Goal UX / Home changes. Branch `feature/goal-engine-foundation`, commit, no push.

### Actions

- Created `backend/goal_engine/` (models, service, repository, router, dedupe, progress, types, strategy, events, lifecycle)
- Mounted `/api/goals/*`; startup indexes for `goals` / `goal_events`
- Wired `GoalService.upsert_from_*_confirm` into Study/Travel confirm (flag `GOAL_ENGINE_ENABLED`, default ON)
- Docs: `GOAL_ENGINE_FOUNDATION.md`, `GOAL_DATA_MODEL.md`, `GOAL_LIFECYCLE.md` + ARCHITECTURE / ROADMAP / DEVELOPMENT_STATE
- Tests: `backend/tests/test_goal_engine.py`; Playwright `frontend/e2e/goal-engine-shadow.spec.ts`
- Included prior audit doc if still uncommitted

### Results

- Goal UX: **NOT implemented** (confirmed)
- Home ranking / screens: unchanged
- pytest `test_goal_engine.py`: **9 passed**
- pytest study + travel regression: **22 passed**
- Playwright `e2e/goal-engine-shadow.spec.ts`: **2 passed** (API assert after Study/Travel confirm; no Goal UI)

### Commit

`feat: introduce Goal Engine Foundation`

---

## 2026-08-05 — Goal Engine architectural audit (docs only)

### Request

Architectural audit only for introducing ORA Goal Engine — no feature implementation.

### Actions

- Added `docs/GOAL_ENGINE_ARCHITECTURAL_AUDIT.md` (current map, overlaps, proposed model/flow, migration, phased plan)

### Results

- Audit complete on `feature/travel-action-flow`; no application code changes

---

## 2026-08-05 — Verify travel action flow browser and Google sync

### Request

Close verification gaps: Playwright travel E2E green; live Google Calendar create/cleanup for connected test account; docs + local commit. No push.

### Actions

- Restarted travel-branch API on `:8001` (stale `:8000` lacked `/travel-projects`); Expo web `:8081` → 8001
- Playwright `e2e/travel-action-flow.spec.ts` hardened; evidence under `frontend/e2e-evidence/travel-action-flow/`
- Script `backend/scripts/verify_travel_google_sync.py` — confirm + 3 Google events + cleanup
- Fixed travel Google persist/cleanup (`calendar_events` full-array write; delete uses `google_sync.synced` fallback)

### Results

- Playwright: **PASS** 1/1 (~29s) — screenshots + `run-log.json`
- Google: **PASS** — event ids `pak7nvaer40p9v6b9cji5hl8o4` / `7gj9vqeu21lb74qp2ekn0s0h2g` / `f0m3kb7sahnkk19e54ctblltr8` created then `cancelled`; calendar `francesconicolocefala@gmail.com`
- Remaining: weather, email auto-find, native mobile

### Commit

`test: verify travel action flow browser and google sync`

---

## 2026-08-05 — Complete Travel Action Flow (Life Planner slice)

### Request

Build ORA Travel / Vacation Action Flow as first real Life Planner: Intent reuse, study-like conversational AE, Travel Project, calendar confirm, Maps, Home phases, Brain, tests, docs, local commit `feat: complete travel action flow`. No push.

### Actions

- Package `backend/action_engine/travel/` (models, period parser, flow, maps, docs, prep, google_sync, brain, project_service)
- Service confirm gate (no silent Google create); router `/travel-projects`
- Intent entities: `start_date` / `end_date` / `period` extraction for vacation text
- Home adapter phases + catalog; FE travel preview + `/travel-project/[id]`
- pytest `test_travel_action_flow.py` (12 passed); Playwright spec authored
- Docs: `TRAVEL_ACTION_FLOW_*.md` + DEVELOPMENT_STATE / PRODUCT / ARCHITECTURE updates

### Result

Backend travel suite **PASS** (12). Weather/email/native/Google-live travel: honest incomplete. Branch `feature/travel-action-flow` local only.

---

## 2026-08-05 — Verify study plan Google Calendar sync (real)

### Request

Google Calendar manually connected for local test user. Verify real study-plan sync create/update/delete; update verification docs; local commit; no push.

### Root cause (blocking sync)

Study sync looked up `connector_id: "google_calendar"` but instances use `calendar_google`, and create called a missing `get_provider_for_user` with wrong `create_event` signature.

### Actions

- Rewrite `action_engine/study/google_sync.py` to use `GoogleCalendarService` + real provider create/update/delete; store `google_calendar_id`
- Wire snooze → Google PATCH; plan delete → Google DELETE
- Script `backend/scripts/verify_study_google_sync.py` against live Google
- Docs: `STUDY_ACTION_FLOW_VERIFICATION.md`, this changelog

### Evidence (PASS)

- Account / calendar: `francesconicolocefala@gmail.com` (primary)
- `google_event_id`: `bj6unbrqrfhce10afscmoh89so`
- `sync_status`: `synced` → update OK → Google status `cancelled` after delete
- Title / Europe/Rome times correct; no duplicates; synthetic event cleaned up

### Result

PASS. Commit message: `test: verify study plan Google Calendar sync`. No push.

---

## 2026-08-05 — Google OAuth works on localhost and 127.0.0.1

### Request

Connect Google works on `http://127.0.0.1:8081/` but fails on `http://localhost:8081/` (Windows). Fix redirect/origin mismatch; accept both in local/dev; document Console checklist; commit locally; no push.

### Root cause

`localhost` and `127.0.0.1` are **different origins** to Google and to the browser. If Cloud Console only lists `127.0.0.1:8081` (Sign-In) or only one of the `:8000` Calendar callbacks, the other host fails with `redirect_uri_mismatch` / origin errors. Frontend also preferred `127.0.0.1` in docs/env while Calendar env used `localhost:8000`.

### Actions

- Calendar OAuth: auto-expand loopback twin in development; pick callback URI from API request host; store per-session `redirect_uri`; sanitize `redirect_after`; browser redirect after callback
- FE: pass `window.location.origin` for Calendar return + Sign-In `redirectUri`
- Docs / `.env.example`: require both hosts in Google Console
- Unit tests: `test_oauth_loopback_hosts.py`

### Google Cloud Console checklist (manual)

**Sign-In Web client** (`EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`):
- Origins: `http://localhost:8081`, `http://127.0.0.1:8081`
- Redirect URIs: `http://localhost:8081`, `http://127.0.0.1:8081`

**Calendar Web client** (`GOOGLE_OAUTH_CLIENT_*`):
- Redirect URIs:  
  `http://localhost:8000/api/connectors/google-calendar/oauth/callback`  
  `http://127.0.0.1:8000/api/connectors/google-calendar/oauth/callback`

### Result

Code + docs accept both loopback hosts. Live localhost connect still needs the Console entries above (cannot be fixed by code alone).

### Open

- User adds Console URIs; restart Expo if env changed; re-test both hosts

---

## 2026-08-05 — Complete end-to-end Study Action Flow

### Request

Finish study Action Flow end-to-end from Intent Engine commit `66b7775`: audit → plan model → conversational steps → Documents V2 → generator → preview/confirm → sessions → flashcards/Interrogami → Brain → Google → Home → resume → API → tests → Playwright → docs → commit. Study only; no Intent Engine rewrite; no push.

### Actions

- Branch `feature/complete-study-action-flow` from `66b7775`
- Package `backend/action_engine/study/` (models, date parser, docs search, generator, plan service, tools, Google, Brain, flow)
- AE service/router: back/draft/search-docs/preview/modify/confirm; `/api/study-plans/*`; confirm-gated side effects
- Home study adapter + actions catalog for plans; FE action UI multi/preview + `/study-plan/[id]`
- pytest `test_study_action_flow.py` **12 passed**; AE study test updated
- Playwright `frontend/e2e/study-action-flow.spec.ts` (UI-only completion after fixture seed)
- Docs: `STUDY_ACTION_FLOW_*.md`, `STUDY_PLAN_GENERATION.md` + PRODUCT/ARCHITECTURE/DEVELOPMENT_STATE/CHANGELOG

### Result

Study priorities produce real confirmed plans (not mock). Intent still routes. Google/Gemini optional. Native mobile not verified. No push/merge.

### Open

- Live Playwright evidence archive when Expo web running
- Device smoke for plan screen

---

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
