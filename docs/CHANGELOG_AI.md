# ORA — AI Changelog

## 2026-08-08 — Home Quiet Premium V1 — technical consolidation (2.2)

### Request

PROMPT 2.2 — no visual change. Tokenize Focus Glow, remove redundant ternaries, coherent CTA busy (disable siblings), verify nav+action dual-step, light DailyFocus helpers, a11y busy. No commit/push.

### Actions

- `frontend/src/theme/focusGlow.ts` + `getFocusGlow(scheme)` consumed by DailyFocus
- `focusPresentation.ts` for typeLabel/focusMeta
- FocusActions: any-busy lock + accessibilityState busy/disabled; documented intentional navigate→onAction
- Cleared `isDark ? colors.surface : colors.surface` in DailyFocus/OraInput
- index onDynamicAction comment for dual-step semantics

### Results

- Visual intent unchanged; race on double-tap CTA mitigated

### Open

- Playwright Life Setup / ranking_version mismatches remain pre-existing
- Prompt 3 (other screens) not started

---

## 2026-08-08 — ORA Home Quiet Premium Polish (2.1)

### Request

PROMPT 2.1 — polish Home only: less card chrome, felt Focus Glow, CTA hierarchy, editorial Perché adesso, Apple-Search Ask Bar, refined header, rewrite Horizon, quieter priorities/borders/motion. No backend/engines/other screens.

### Actions

- Refined DailyFocus (surface-not-card + diffuse glow + FocusActions primary/secondary/tertiary)
- OraInput taller/quieter; AmbientHeader smaller; FocusHorizon vertical sections; Priority/Continue/Situation/Google quieter
- Home max-width 860; removed entry FadeIn on scroll
- Docs DEVELOPMENT_STATE / CHANGELOG

### Results

- Behavior/testIDs preserved; presentation only

### Open

- Signature system (Prompt 3+)
- Theme toggle in Profilo
- Full visual QA with authenticated Home (Life Setup gate)

---

## 2026-08-07 — ORA Home Quiet Premium V1

### Request

PROMPT 2 — Redesign Home presentation only with Quiet Premium. No backend/ranking/engines/API changes. Daily Focus, Ask Bar, Focus Horizon, light priorities, unified Aggiornamenti.

### Actions

- New `frontend/src/components/home/quiet/*` (AmbientHeader, OraInput, DailyFocus, FocusHorizon, PrioritySection, UpdatesSection, SituationSummary, ContinueSection, loading/notices/modals)
- `app/(tabs)/index.tsx` orchestration + `AppScreen`/`useTheme`
- EmptyHome + DynamicActions + ParlaConOra re-export themed
- Docs PRODUCT / ARCHITECTURE / DEVELOPMENT_STATE

### Results

- Preserved testIDs: `adesso-card`, `perche-adesso`, `parla-*`, `dynamic-actions`, `priorita-list`, `situazione-card`, `google-banner`, suggestion/insight actions, modals
- Focus Horizon from real `start_at`/`due_at`/`goal_target_date` only
- tsc / lint (Home files) / expo web export OK

### Open

- Theme toggle UI in Profilo
- Tab bar / Login restyle (Prompt 3)
- Playwright Home against live API when stack available

---

## 2026-08-07 — ORA Quiet Premium Design System (Visual Foundation v1)

### Request

PROMPT 1 — Design System + Tokens + Primitives + Theming. Leave backend / ranking / Action / Conversation / Home logic untouched. Language: ORA Quiet Premium (Apple HIG; Deep Indigo; light+dark designed; glass chrome-only).

### Actions

- Rewrote `frontend/src/theme/*`: palettes, typography, spacing, radius, shadows, motion, haptics, icons, tokens (legacy aliases), ThemeProvider, responsive helpers
- Added UI primitives under `frontend/src/components/ui/` (AppScreen, AppCard, AppButton variants, IconButton, FAB, headers, ListItem, inputs, Chip, Badge, Divider, Glass/BottomSheet, Skeleton, Empty/Error, Avatar, Metric, TimelineDot)
- Wired `ThemeProvider` in `frontend/app/_layout.tsx`
- Updated `design_guidelines.json` + PRODUCT / ARCHITECTURE / DEVELOPMENT_STATE

### Results

- Existing screens keep working via legacy token aliases (`brand`→accent, `onSurface`→textPrimary, …)
- Static `tokens` defaults to dark Quiet Premium (deep surfaces, not #000)
- Primitives available; not mass-migrated yet

### Open

- Prompt 2: restyle key screens + tab bar glass with new primitives
- Profile theme toggle UI
- Gradual `useTheme()` migration off static StyleSheet colors

---

## 2026-08-07 — Introduce Digital Twin Knowledge Model

### Request

On `feature/life-object-engine` (~`a5b490c`): Digital Twin Knowledge Model — facts/hypotheses/decisions/goals(link)/memory + timeline. Fact never deleted (supersede). Gemini=consultant. Read APIs + minimal write for tests. No Home UX. Commit exact message. No push/merge.

### Actions

- Package `backend/life_objects/knowledge_model/` (models, facts, hypotheses, decisions, memory, timeline, migration, integration, prompts, service)
- LifeObject fields: `facts`, `hypotheses`, `decisions`, `memory`, `knowledge_migrated`
- Wire ingest on document create/update; never_ask_again filters on enrichment
- API: `GET .../facts|hypotheses|decisions|timeline|knowledge`; POST propose/confirm/reject/outcome
- Home V3 predisposed `knowledge_summary` (flag OFF)
- Tests: `test_knowledge_model.py` + full suite regression
- Playwright: `e2e/life-object-knowledge-model.spec.ts`
- Docs: `LIFE_KNOWLEDGE_MODEL.md`, `DIGITAL_TWIN_MODEL.md`, `FACTS_HYPOTHESES_DECISIONS.md` + LIFE_OBJECT_* / ARCHITECTURE / DEVELOPMENT_STATE

### Results

- pytest `life_objects/tests/`: **31 passed**
- FAIL criteria: Fact hard-delete blocked; hypotheses not auto-promoted; supplier supersede keeps history
- Home UX: **unchanged**
- Commit: `feat: introduce Digital Twin Knowledge Model` (no push)

### Open

- Confirm/reject UI not shipped
- Conversation → knowledge hooks partial
- Home V3 UI off

---

## 2026-08-07 — Harden Life Object semantic integrity and AI validation

### Request

On `feature/life-object-engine` (~`0ab2f2b`): Life Object Engine v2 — Semantic Integrity & AI Validation. Gemini=consultant, backend=authority. Validator before persist. Titles/registry/gaps/assimilation/link states/Health 2.0/provenance/Home V3 DTO. Tests + docs. Commit. No push/merge. No Home UX.

### Actions

- `semantic_validator.py`, `title_generator.py`, `property_registry.py`, `assimilation.py`, `link_states.py`, `knowledge_gaps.py`, `provenance.py`
- Models: Health 2.0 dimensions, typed provenance, `last_validation`, `assimilated_kinds`
- Service: validator ALWAYS before persist; quiet assimilate vs REAL_CONFLICT only
- Enrichment: consultant narrative, concept gaps, observation insights, Health 2.0
- Home V3 DTO: `life_object_id`, `life_domain`, health, next_action, benefits, questions, insights, timeline, related_*
- Tests: `test_semantic_integrity.py`, `test_real_life_growth.py` + existing suite
- Docs: LIFE_OBJECT_*, ARCHITECTURE, DEVELOPMENT_STATE, CHANGELOG

### Results

- pytest `life_objects/tests/`: **23 passed**
- FAIL criteria checked: no HOME title «Lavoro»; mutuo/bolletta assimilati; no merge piles on clear updates
- Home UX: **unchanged** (`LIFE_OBJECT_HOME_UI_ENABLED=0`)
- Commit: `feat: harden Life Object semantic integrity and AI validation` (no push)

### Open

- Home V3 UI not shipped
- Conversation provenance hooks not fully wired
- Gemini live optional

---

## 2026-08-07 — Enrich Life Objects with AI narrative and reasoning

### Request

On `feature/life-object-engine` (~`253fa65`): AI narrative, questions, insights, temporal reasoning, explainable life health, identity vs state, APIs, Home V3 prep only (flag OFF). No Home UX / no Life Objects screen. Gemini via Provider Manager + Italian deterministic fallback. Commit exact message. No push/merge.

### Actions

- Models: `identity`/`state`, `AINarrative`, `AIInsight`, `TemporalComparison`, explainable `LifeObjectHealth`, enrichment Pydantic results
- `identity_state.py` — split non-distruttivo da `properties`
- `enrichment.py` — narrative/questions/insights/temporal/health (Gemini + fallback IT)
- `memory.py` — `detect_state_changes`
- `home_v3.py` — DTO card PREDISPOSTO
- Service: best-effort enrich after shadow upserts; API helpers
- Router: `/narrative`, `/questions`, `/insights`, `/health`, `/history`, `/relationships`, `/temporal`, `/enrich`, `/home-v3-feed`
- Tests: Casa/Auto/Università/Lavoro enrichment, fallback, isolation, Home V3 OFF
- Playwright: assert enrichment after Casa chain + feed OFF
- Docs: LIFE_OBJECT_* + DEVELOPMENT_STATE + CHANGELOG

### Results

- pytest `life_objects/tests/test_life_object_engine.py`: **15 passed**
- Gemini: **optional** — CI/tests use deterministic Italian fallback (`LIFE_OBJECT_GEMINI=0`)
- Home UX: **unchanged**; Home V3 PREDISPOSTO
- Commit: `feat: enrich Life Objects with AI narrative and reasoning` (no push)

### Open

- Home V3 UI not shipped
- Live Gemini enrichment not required for green CI

---

## 2026-08-06 — Introduce Life Object Engine as the core of ORA (SHADOW)

### Request

Life Objects as **canonical model of user reality** (shadow) from `feature/life-experience-ai-documents` @ `b80d18a`. Branch `feature/life-object-engine`. Other engines keep existing as satellites that read/write objects — they no longer own “the truth” alone. No major UX; Home stays Goal-aware. No push/merge.

### Actions

- Package `backend/life_objects/` — models, types, repository, dedupe, reasoner, linking, memory/trends, service, shadow, router, tests
- Flags: `LIFE_OBJECT_ENGINE_ENABLED=1`, `LIFE_OBJECT_HOME_UI_ENABLED=0`, `LIFE_OBJECT_GEMINI=1`
- Shadow hooks: `life_setup.consume_document`, `GoalService.upsert` (+ `life_object_id`), Travel/Study confirm
- Goal model: optional `life_object_id` (non-breaking)
- API `/api/life-objects` mounted; Mongo indexes at startup
- Playwright: API-driven Casa chain assert single HOME
- Docs: `LIFE_OBJECT_*.md` + ARCHITECTURE/PRODUCT/STATE/MATRIX

### Results

- pytest `life_objects/tests/test_life_object_engine.py`: **11 passed**
- Home UX: **unchanged** (SHADOW / Home V3 PREDISPOSTO)
- Framing: Life Objects = verità canonica; altri motori restano satelliti R/W
- Commit: `feat: introduce Life Object Engine as the core of ORA` (no push)

### Open

- Home V3 Life Objects UI not shipped
- Richer Conversation/Proactive object-driven suggestions later

---

## 2026-08-06 — Deepen AI Document Understanding + harden analysis versions

### Request

Refine AI Document Understanding on `feature/life-experience-ai-documents` @ `36da3b6`: fix `int("2.0")`, strengthen Document Reasoner with life context, Life Profile hypotheses, cross-doc, AI actions, reminder titles, memory, Gemini prompt, tests, Playwright, CI. No push/merge.

### Actions

- `documents/intelligence/versions.py` — schema string vs int revision; never `int("2.0")`
- `migration.py` / `service.py` / `analyzer.py` / `life_reasoning.py` / profile — all bump/compare/heal paths
- `document_context.py`, `document_actions.py`, `document_memory.py`, `document_reasoner.py`
- Prompt rewrite (assistente/segretario); schema arricchito (context/benefit/knowledge/deadlines/…)
- Bolletta → contratto energia + ownership **suggested**; cross-doc affinity casa/auto/studio
- Titoli promemoria con fornitore; «Cosa posso fare» AI-first
- Tests: `test_analysis_versions.py`, `test_ai_document_understanding.py` (+ fixture nuove)
- CI: `.github/workflows/ci.yml` (pytest focused, tsc, compileall, Playwright, secret scan)
- Docs: AI_DOCUMENT_UNDERSTANDING, DEVELOPMENT_STATE, CAPABILITY_MATRIX, verification

### Results

- pytest focused (`test_analysis_versions` + `test_ai_document_understanding` + `test_documents_v2`): **32 passed**
- pytest LE docs: **62 passed**
- Gemini live smoke (key present): **VERIFICATO** contratto_telefono / busta_paga / verbale → `docs/evidence_ai_document_understanding_gemini.json`
- Playwright CASA/AUTO/BOLLETTA: **3 passed** (re-login harden con clear storage)
- Commit: `42e3cc2` (no push)

### Open

- Brain UI still absent (API memory best-effort only)

---

## 2026-08-06 — Fix: reminder draft for admin document deadlines

### Request

Finish interrupted fix on `feature/life-experience-ai-documents` @ `9a12db3`: utility bills with a due date must surface an actionable draft reminder («Salva promemoria su ORA» / deadline-calendar) requiring confirmation — no irreversible auto calendar. Pytest + Playwright bolletta + docs + local commit. No push/merge.

### Root cause

1. Documents V2 built `event_candidates` only for event/travel/medical macros — admin/financial bills never got a deadline candidate despite extracting `due_date`.
2. Label matcher required exact `Scadenza:` and missed real-world `Scadenza pagamento:`.
3. (Wiring gap found while finishing) Life Setup `DOC_PIPELINE_TERMINAL` omitted `awaiting_confirmation`, so once a deadline candidate existed the UI never reached consume / Document Result.

### Actions

- `backend/documents/intelligence/admin_extract.py` — compound deadline labels; line-anchored match
- `backend/documents/intelligence/analyzer.py` — `_build_admin_deadline_event` → proposed deadline `event_candidate`
- `backend/life_setup/service.py` — treat `awaiting_confirmation` / `action_required` as ready to consume
- Tests: `test_documents_v2.py`, `test_life_experience_documents.py`; Playwright BOLLETTA hard-asserts reminder confirm
- FE testIDs on draft-event confirm control; E2E API default aligned to `:8000`

### Results

- pytest `test_documents_v2.py` + `test_life_experience_documents.py`: **78 passed**
- Playwright BOLLETTA: **passed** (reminder button → «Promemoria salvato su ORA.»)
- Live API smoke: bolletta → deadline proposed → confirm → `google_sync=null`, draft persisted
- Commit message (exact): `fix: surface reminder draft for admin document deadlines`

### Open

- Google Calendar confirm path not re-exercised live
- ~~`analysis_version` string `"2.0"`~~ → fixed in deepen batch above

---

## 2026-08-06 — AI Document Understanding in Life Experience

### Request

Real document upload + AI Document Understanding wired into ORA Life Experience on `feature/life-experience-ai` @ `c518a23`: real Expo file picker (not synthetic-only), Documents V2 as the only pipeline, Gemini structured document understanding, Life Profile mapping with provenance, cross-document reasoning, confidence-driven confirmation, draft-only calendar events, Home/Proactive updates, ≥30 backend tests, 3 UI-driven Playwright scenarios, Gemini real verification, docs. Branch `feature/life-experience-ai-documents`. No push/merge.

### Actions

- `backend/documents/intelligence/life_reasoning.py` — AI Document Understanding: `DocumentReasoning` (Pydantic), Gemini call with chunking, deterministic fallback, content-hash cache, per-type `type_specific` schemas (rogito/mutuo/bolletta/libretto/polizza/piano di studi/…)
- `backend/life_setup/document_mapping.py` — declarative mappers → `MappedField` with provenance, confidence-driven status (`extracted`/`suggested`)
- `backend/life_setup/cross_document.py` — link (never merge) related documents, conflict/duplicate detection
- `backend/life_setup/{models,profile_service,service,router}.py` — field provenance/status enum, `attach/status/consume/retry/detach` + `confirm-field/correct-field/reject-field/resolve-confirmation` endpoints, pending-document resume on reopen
- `frontend/app/life-setup/index.tsx` — real `expo-document-picker` flow (upload → attach → poll → consume), Document Result UI (Cosa ho capito / Dati trovati / Dati da verificare / Cosa posso fare / Documento originale), inline field correction (cross-platform, replaces `Alert.prompt`)
- `frontend/src/api/client.ts` — new `lifeSetup*` document API functions + types
- `backend/tests/fixtures/life_documents/` + `frontend/e2e/fixtures/life-documents/` — synthetic (fake data) PDF/TXT fixtures per document type
- `frontend/e2e/life-experience-documents.spec.ts` (new) — CASA/AUTO/BOLLETTA scenarios, real file picker via `page.waitForEvent('filechooser')`
- Docs: `LIFE_EXPERIENCE_REAL_DOCUMENTS.md`, `AI_DOCUMENT_UNDERSTANDING.md`, `LIFE_DOCUMENT_MAPPING.md`, `CROSS_DOCUMENT_REASONING.md`, `LIFE_EXPERIENCE_DOCUMENT_VERIFICATION.md` (new); `PRODUCT_AUDIT_MASTER`, `CAPABILITY_MATRIX`, `PRODUCTION_READINESS`, `LIFE_EXPERIENCE`, `AI_REASONING_LOOP`, `DOCUMENTS_V2_ARCHITECTURE`, `DEVELOPMENT_STATE` (updated)

### Results

- pytest `test_life_experience_documents.py`: **62 passed**; regression `life_setup`+`ai_life_strategist`+`documents`: **92 passed**
- `python -m compileall`, `npx tsc --noEmit`, `npx eslint` (changed files clean, pre-existing issues untouched): all OK
- Playwright `e2e/life-experience-documents.spec.ts`: **3 passed** (CASA, AUTO, BOLLETTA — real file picker, real Documents V2 upload, real Document Result UI); regression `e2e/life-experience-ai.spec.ts`: **2 passed**
- Real Gemini verified (provider=`gemini`, model=`gemini-flash-lite-latest`) for rogito (conf. 0.99), bolletta (1.00), libretto (1.00), piano di studi (0.98) — latency ~4.5–5.8s each
- 9/13 catalogued document types have classification + generic mapping tested but **no dedicated real-Gemini verification** in this session (see `LIFE_EXPERIENCE_DOCUMENT_VERIFICATION.md` for the full honest per-type matrix)
- Mobile (iOS/Android) DocumentPicker: compatibility notes written, **not verified** on device/emulator

### Open

- Consent UI for calendar drafts → Google (draft-only events exist; Google confirm path not re-exercised here)
- Extend real-Gemini verification to the remaining 9 document types
- Mobile native verification (device/emulator)

---

## 2026-08-06 — Product capability audit (CTO docs)

Docs-only: `PRODUCT_AUDIT_MASTER.md`, `CAPABILITY_MATRIX.md`, `PRODUCTION_READINESS.md`, `FEATURE_STATUS.md` — base `09404f1`; message `docs: complete product capability audit`.

---

## 2026-08-06 — AI-first Life Experience

### Request

Build AI-first Life Experience on `feature/ai-life-setup-foundation` @ `b68cbdc`: natural conversation (not wizard), AI reasoning loop every turn, Gemini structured prompting (Italian), deterministic Italian fallback, document strategy, Home/Proactive benefit cards, Playwright E2E, docs; commit exactly `feat: introduce AI-first Life Experience`. Branch `feature/life-experience-ai`. No push/merge.

### Actions

- `reasoning_loop.py` + structured Gemini context (`to_gemini_context_json`) + task «Qual è la prossima domanda…»
- Extended `StrategistPlan` / `ReasoningContext` (refused/postponed, user_explanation, summaries)
- Benefit Engine Italian `home_signal` / `proactive_signal` + Home/Proactive adapters
- Domains any order (gain-ranked); piano di studi in document strategy
- FE Life Experience markers + multi-doc upload; Playwright `life-experience-ai.spec.ts`
- Docs: LIFE_EXPERIENCE, AI_REASONING_LOOP, AI_PROMPTING_GUIDE, AI_DECISION_POLICY, CONVERSATION_EXPERIENCE + ARCHITECTURE/ROADMAP/DEVELOPMENT_STATE/PRODUCT/BENEFIT_ENGINE

### Results

- Anti-wizard UX; Home benefits after setup; Proactive never «Completa il profilo»
- pytest `test_life_experience.py` + `test_strategist_foundation.py`: **30 passed**
- Playwright `e2e/life-experience-ai.spec.ts`: **2 passed**
- Commit message (exact): `feat: introduce AI-first Life Experience`
- No push

### Open

- Real Documents V2 binary upload from conversation
- Calendar consent UI for strategist drafts

---

## 2026-08-06 — AI Life Setup + AI Life Strategist foundation

### Request

Build ORA Life Setup + AI Life Strategist foundation: first-launch natural conversation (not wizard), structured strategist plans via Gemini Provider Manager + deterministic fallback, Life Profile domains, APIs, integrations, tests, Playwright, docs; commit `feat: introduce AI-driven ORA Life Setup`. Branch `feature/ai-life-setup-foundation` from semantic-extraction tip. No push/merge.

### Actions

- Packages `backend/ai_life_strategist/` + `backend/life_setup/` (profile, sync, stubs, router)
- Flags `LIFE_SETUP_ENABLED` / `AI_LIFE_STRATEGIST_ENABLED` (+ cache/gemini) in `.env.example`
- CE origin `life_setup`; Home/Proactive soft resume (never «Completa il profilo»)
- FE `/life-setup` conversation + first-launch gate; no permanent Life Setup section
- Tests: `test_ai_life_setup_foundation.py` / strategist suite; Playwright `life-setup-strategist.spec.ts`
- Docs: LIFE_SETUP_PRODUCT, AI_LIFE_STRATEGIST, LIFE_PROFILE, LIFE_GRAPH, BENEFIT_ENGINE, QUESTION_PLANNING + PRODUCT/ARCHITECTURE/ROADMAP/DEVELOPMENT_STATE

### Results

- Conversation-first UX (anti-wizard markers); Casa→rogito→profile/goal path; interrupt hides module
- pytest `ai_life_strategist/tests/test_strategist_foundation.py`: **19 passed**
- Playwright `e2e/life-setup-strategist.spec.ts`: **3 passed**
- Email/Open Banking/WhatsApp/Weather: stubs only (honest)
- Commit message (exact): `feat: introduce AI-driven ORA Life Setup`
- No push

### Open

- Full Documents V2 binary upload UX from Life Setup beyond synthetic path
- Real Gemini plans when `GEMINI_API_KEY` set (fallback always available)

---

## 2026-08-06 — Semantic Extraction + Gap Analyzer (Playwright + exact commit message)

### Request

Close Playwright + commit-message gaps: tip must carry exact message `feat: add semantic extraction and dynamic gap analysis`; run real Playwright against API+Expo.

### Actions

- Restart tip API on `:8001` with `SEMANTIC_ENGINE_ENABLED=1` (+ CE/Goal/Proactive)
- Expo web on `:8081` → `EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:8001`
- Playwright `e2e/semantic-extraction-gap.spec.ts` — both scenarios PASS; evidence under `frontend/e2e-evidence/semantic-extraction-gap/`
- Docs: `SEMANTIC_ENGINE_VERIFICATION.md` updated with live results
- CE soft-override when Intent clarifies but Semantic has strong travel/study

### Results

- Playwright: **2 passed** (Fra due settimane → Dove andrai?; Vibo → lodging). Forbidden combo-dates Q absent.
- Tip commit message (exact): `feat: add semantic extraction and dynamic gap analysis`
- Prior package tip remains `d4f6d64` (`… and gap analyzer`); no history rewrite; no push

---

## 2026-08-06 — Semantic Extraction + Gap Analyzer

### Request

Implement ORA Semantic Extraction Layer + Gap Analyzer on branch `feature/semantic-extraction-gap-analyzer` from Home tip `90b3fb1`. Fix travel bug: “Fra due settimane parto.” must not ask “Quando parti e quando torni?”. Gemini optional via Provider Manager. Full E2E + docs.

### Actions

- Package `backend/semantic_engine/` (models, dates, deterministic, gemini optional, normalizer, context_merge, gap_analyzer, schemas, cache, service, router)
- Wire Conversation Engine → Semantic → Gap → Action Engine; session entity fields
- Travel AE: split departure_date / return_date; lodging when core known; ban combined dates Q
- FE: dynamic questions + understood summary (Partenza/Destinazione/Ritorno)
- Tests: `test_semantic_engine.py` (**17 passed**) + corpus ≥200; Playwright `semantic-extraction-gap.spec.ts`
- Docs: SEMANTIC_ENGINE_*, ENTITY_MODEL, GAP_ANALYZER, SEMANTIC_ENGINE_VERIFICATION + architecture updates

### Results

- pytest `tests/test_semantic_engine.py`: **17 passed**
- Travel proof: fortnight → «Dove andrai?»; after Vibo → return only; full Vibo → lodging
- Commit (package): `d4f6d64` `feat: add semantic extraction and gap analyzer`
- Limits: Gemini optional; deterministic sufficient for mandatory Italian cases

---

## 2026-08-06 — Home Goal presentation aggregation

### Request

Fix ORA Home so each Goal shows ONE main card via a Presentation Aggregation Layer. Branch `feature/home-goal-presentation-dedupe` from `feature/conversation-engine` @ `e1cbe43`. Non-destructive; legacy audit/migrate; ≥13 tests + Playwright Psicologia/Vibo.

### Actions

- `backend/home/presentation.py` — aggregate by `goal_id`, preference order, supporting_details/actions/source_refs
- Wire into `HomeService.build_home`; ranking `home-rank-1.3` / `home-pres-1.0`
- Stronger GoalIndex + adapter refs (life_nodes, reminders, decisions, Google extended props)
- Legacy `scripts/audit_home_goal_links.py` (audit/migrate/archive-fixtures; no deletes)
- FE: presentation fields on `HomeItem`; Adesso/Priorità show supporting details
- Docs: HOME_PRESENTATION_AGGREGATION, HOME_DEDUPLICATION_VERIFICATION + architecture updates
- Tests: `test_home_presentation_aggregation.py`, Playwright `home-presentation-dedupe.spec.ts`

### Results

- pytest `test_home_presentation_aggregation.py` + `test_home_goal_aware.py`: **33 passed**
- Playwright `e2e/home-presentation-dedupe.spec.ts`: **2 passed** (Psicologia collapsed 7 artifacts → 1 card; Vibo 1 card; relogin ok)
- Commit: `fix: aggregate Home artifacts by Goal`
- Limits: orphans without reconstructible refs stay ungrouped; no auto-delete of legacy fixtures

---

## 2026-08-06 — Conversation Engine orchestration

### Request

Build ORA Conversation Engine on `feature/conversation-engine` from `feature/proactive-engine` @ `319859e`. Stateful orchestrator (NOT chatbot): Input → CE → Intent → Goal → Action → Projects → Brain → Proactive → Home. Home PARLA CON ORA; Playwright travel + study phrases.

### Actions

- Package `backend/conversation_engine/` (models, repo, memory, orchestrator, service, router, adapters)
- Wire indexes in `server.py`, router in `ALL_ROUTERS`, flag `CONVERSATION_ENGINE_ENABLED`
- Home adapter + PARLA CON ORA FE; resume Continua; Proactive resume_conversation generator + accept handoff
- Intent patterns for natural “parto…” phrases; AE known_slots seed from CE memory
- Docs: CONVERSATION_ENGINE_PRODUCT/ARCHITECTURE, SESSION_MODEL, ORCHESTRATION + ARCHITECTURE/ROADMAP/DEVELOPMENT_STATE
- Tests: `backend/tests/test_conversation_engine.py`, `frontend/e2e/conversation-engine.spec.ts`

### Results

- pytest `tests/test_conversation_engine.py`: **9 passed**
- Playwright `e2e/conversation-engine.spec.ts`: **2 passed** (travel + study via CE → AE → artifacts → Home)
- Commit: `feat: introduce Conversation Engine orchestration`
- Limits: STT stub; email/WA/open_banking stubs; no chatbot UX; Metro may need `--clear` for PARLA bundle

---

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
