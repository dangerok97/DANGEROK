# ORA — AI Changelog

## 2026-08-18 — V2.8.3a Provider Reliability & Error Taxonomy

- Split manager-level `LLMNotConfigured` (no enabled/configured provider) from
  `LLMProviderUnavailable` (configured chain exhausted).
- Added typed quota, rate-limit, timeout, network, authentication,
  configuration, model, provider-response and internal ORA failures with one
  explicit failover policy.
- Added bounded, sanitized provider-attempt metadata and safe outcome logs;
  prompts, responses, credentials and raw provider errors are never recorded.
- Added a conservative process-local circuit breaker. `Retry-After` extends a
  bounded cooldown without sleeping or blocking a worker.
- Made `/llm/status` passive: configured/enabled and recent runtime state are
  exposed without provider probes or extra quota consumption.

## 2026-08-18 — V2.8.3 Memory Proposal & Governed Learning

- Extended the optional AI `MemoryCandidate` with open semantic identity,
  epistemic status, temporal scope, authority, provenance, sensitivity and
  explicit correction/forget relationships.
- Added deterministic, user-scoped Memory Governance with bounded outcomes:
  promotion, clarification, rejection, supersession and governed forgetting.
- Added idempotent persistence by reasoning epoch, non-destructive history,
  revisions, cache invalidation and startup indexes on the existing `memories`
  source of truth.
- Re-entered AI reasoning from a structured governance observation so ORA never
  claims an unconfirmed write and can resolve identity collisions explicitly.
- Preserved Situation/Memory separation, inference/fact distinction, raw device
  exclusion and cross-session Context Broker retrieval.
- Added deterministic and opt-in real-provider V2.8.3 evaluation suites.
- Final live QA on the canonical local backend added Memory-specific
  persist-before-claim/result-consistency re-entry, a minimized Stage A Memory
  existence index, source-hint-aware Stage B ranking and explicit separation
  between governed mutation refs and read-only derived Life Memory evidence.
- Made `identity_key` the canonical collision key when present (with open `kind`
  as fallback), preventing duplicate active facts when provider label wording varies.
- Final provider-real gate hardened the AI contract for explicit remember/correct/forget
  instructions: no redundant confirmation, governed Memory retrieval before mutation,
  canonical `identity_key`/ref reuse, and no correction degraded into a fresh proposal.
- Added a terminal persist-before-claim guard so an exhausted reasoning budget can never
  emit a durable-memory success claim without a persisted governance outcome.
- Verified live promotion, cross-session retrieval, temporary rejection,
  correction/supersession, inference isolation and user-scoped logical forget.

## 2026-08-18 — V2.8.2 Context Broker V3

- Added optional, bounded `ContextNeed` to `CognitiveDecision`; legacy
  `context_query` remains an explicit compatibility alias.
- Added one general-purpose source registry for Profile, Memory, Situations,
  Life OS, Goals, file metadata and calendar metadata. Presence remains behind
  its consent-aware capability.
- Stage A remains small and signals hidden/unresolved Situation detail; Stage B
  retrieves only after AI request and always re-enters reasoning.
- Added authority/provenance-aware evidence, conflict preservation, diversity,
  context budgets and failure-safe observability without personal payload logs.
- Added deterministic V2.8.2 coverage and opt-in real-provider evals for travel,
  non-travel, arbitrary context, cross-session continuity and conflict.

## 2026-08-17 — Home dedupe e legacy E2E hygiene

- Normalized exact title/hour dedupe keys consistently across legacy Home sources while preserving `goal_id` isolation.
- Aligned legacy `/priorities` tests with its canonical default `limit=3`; the seven-decision seed contract is now tested directly.
- `test_ora_backend.py` now requires explicit `ORA_TEST_BACKEND_URL` and never falls back silently to a preview backend.

## 2026-08-17 — Google Login V2 multipiattaforma

### Architettura

- Web: Google Identity Services lazy, popup/callback `credential`; nessun token negli URL ORA
- iOS/Android: `@react-native-google-signin/google-signin` `16.1.4`; development/EAS build, non Expo Go
- Adapter unico consumato da Login e Settings; assenza config non monta provider e lascia Email/Register operativi
- ID token effimero → backend ORA → JWT ORA; nessun access token Google persistito
- Persistenza JWT atomica prima di aggiornare `AuthContext` e fare routing
- Audience backend esplicite via `GOOGLE_ALLOWED_CLIENT_IDS`; fallback legacy documentato ai soli client Login
- Errori temporanei JWKS → `503`; token invalidi → `401`; `email_verified` normalizzato rigorosamente
- Google Login e Google Calendar OAuth restano contratti separati

### Verifica iniziale

- Frontend auth regression: **8 passed**
- Backend `test_social_auth_unit.py`: **20 passed**
- `expo config --type public` senza Google config: **ok**
- V2.7.1 Home handoff + location: **52 passed**
- TypeScript: **ok**; lint **0 errori** (42 warning preesistenti); Expo web export **ok**
- Dev server offline `/login`: HTTP **200**; UI browser/Incognito/Google OAuth **non verificati** per runtime browser locale indisponibile

**NO COMMIT / NO PUSH.** stash@{0} untouched.

---

## 2026-08-16 — V2.7.1 Home → ORA first-turn handoff

### Exact root cause

Home `startOraConversation` correctly called `POST /ai-core/start` (runs `run_cognitive_loop`, may return `client_actions` / `ora_text`), then **discarded the response** and navigated with only `sessionId`. `OraConversationScreen` mount only `GET` history and never resumed `pending_turn` / `client_actions`. Location worked on a second in-ORA send; the first user bubble could vanish due to **text-based** consecutive-user dedupe + backend text duplicate skip.

### Fix

- Persist generic `pending_turn` (`awaiting_client` + `client_actions` + id) in AI state on client pause
- `GET /ai-core/{id}` returns `pending_turn` + `client_actions` for mount resume
- ORA mount fulfills pending client actions once (idempotent Set) → client-resume → render; never re-sends user text
- History / message identity via `message_id` / `step_id`; remove text-only dedupe
- `client_message_id` idempotency on message endpoint

### Tests

- `test_ai_native_home_handoff_v271.py` + location v271: **52 passed**
- V1 / life_os / context_change: **45 passed**
- `tsc --noEmit`: **ok**

Live Home Chrome re-QA: **pending CPO** after backend reload.

**NO COMMIT / NO PUSH.** stash@{0} untouched.

---

## 2026-08-16 — V2.7.1 STALE → fresh foreground refresh (live fix)

### Exact root cause

STALE `get_current_location` set `needs_client: True` but historically could omit `client_action`. The cognitive loop only pauses when `needs_client` **and** `client_action.type` exist — so the FE never ran `navigator.geolocation`, never POSTed `/location/signal`, and the model answered from the stale observation (often with incorrect “could not obtain / permission” wording).

Place-label “Vibo Marina” was already correct; Chrome site Location was already granted. First failing layer = **capability → loop bridge** (missing/ignored `client_action`), not browser permission and not reverse-geocode.

### Fix

- STALE + ORA `while_using` → `client_action: request_foreground_location` (`refresh: true`)
- STALE + ORA `off` → still `request_location_permission` (product consent ≠ Chrome)
- Loop: defensive synthesize `client_action` if `needs_client` without one; `pending_client_capability` for generic follow-up retries; location nudge ignores non-terminal STALE/needs_client obs
- Preserve acquisition_error on failed refresh (timeout/denied/unavailable) so resume is terminal; clear transient errors on next user turn for retry
- FE: skip consent sheet on `request_foreground_location`; `maximumAge: 0` when `refresh`; distinct outcome recording; signal POST failure → resume with failure state
- Honesty: permission wording only on `denied`

### Tests

- `test_ai_native_location_v271.py`: **46 passed**
- AI-native V1 / life_os v23 / context_change v262: **45 passed**
- Frontend `tsc --noEmit`: **ok**

### Live browser QA

Instrumented path verified in unit/loop tests. Full Chrome re-QA of Dove sono / retry after backend reload: **pending CPO** (no commit).

**NO COMMIT / NO PUSH.** stash@{0} untouched.

---

## 2026-08-16 — V2.7.1 live label trace: CURRENT cache + settlement order

### Exact root cause (proven on live Mongo)

1. Fresh `/ora` still reused **user-scoped** CURRENT/RECENT `LocationSignal` → no new GPS, no reverse-geocode.
2. Persisted `place_label=Vibo Valentia` from old municipality-only mapper (`place_resolver_version` absent).
3. Provider on that signal actually returned `village=Vibo Marina` + `neighbourhood=Pennello` + `town=Vibo Valentia`; early v2 resolver preferred neighbourhood first.

### Fix

- `place_resolver_version` + semantic re-resolve from stored coords when version outdated (no wipe, no forced prompt if GPS still fresh)
- Settlement-first locality order: village/suburb before neighbourhood/quarter
- Version bump `v2_locality_settlement`

Live upgrade on stored signal → display **Vibo Marina**, municipality **Vibo Valentia**. Signal now STALE → next ask may refresh GPS via needs_client.

**NO COMMIT / NO PUSH.**

---

## 2026-08-17 — V2.8.1 Situation Model V1

- Added domain-neutral, user-scoped `situations` persistence with canonical ids,
  optimistic revisions, terminal transitions, provenance/history and bounded schema.
- Extended `CognitiveDecision` with optional AI-owned `situation_update`.
- Context Broker now supplies a minimized session/recent Situation slice.
- Situation persistence failures re-enter cognition before user-facing success claims.
- Client resume reuses the same reasoning epoch; later user turns remain mutable.
- Situation remains separate from Life Memory and does not implicitly change linked
  Life OS plans/objects.
- Added dedicated V2.8.1 contract/regression tests and canonical cognitive architecture.
- No domain handler, dependency, migration, commit or push.

## 2026-08-16 — V2.7.1 place-label precision (locality vs municipality)

### Live QA

“Sei a Vibo Valentia” while physically in Vibo Marina (frazione). GPS consistent; mapper wrong.

### Root cause

`nominatim_reverse_city` used `zoom=10` (hides locality) and preferred `city`/`town` before `village`/`suburb`.

### Fix

- `location/place_label.py`: generic resolver; Nominatim zoom=16; structured `display_label` / locality / municipality / region / country
- Accuracy gate: poor GPS → admin-only label
- Life Setup keeps city-only reverse helper

**NO COMMIT / NO PUSH.**

---

## 2026-08-16 — V2.7.1 live QA fix: foreground geolocation consent bridge

### Root cause

Default `location_mode=off` was advertised to the model as `runtime_capabilities.current_location=disabled_by_user`. On “Dove sono adesso?” the LLM answered without calling `get_current_location`, so no `client_actions` reached the FE and Chrome never prompted.

### Fix

- Caps: `requires_consent` (not device-disabled); observation `consent_required` + `request_location_permission`
- Loop: location-before-claim nudge when answering a current-location ask without a location tool obs
- Distinct outcomes: denied / timeout / position_unavailable / unavailable
- Resume: `resume_client=True` does not duplicate user in `recent_turns`; history/UI dedupe guards
- FE: consent sheet → preference → `getCurrentPosition`; sending lock

**NO COMMIT / NO PUSH.** stash@{0} untouched.

---

## 2026-08-15 — Prompt V2.7.1 Foreground location + PresenceContext (slice 1)

### Request

Implement foreground web location, short-lived LocationSignal, PresenceContext, AI Core location caps, Context Broker presence, permission honesty, minimal settings control, tests. No background/geofence/TravelFlow/MeaningfulPlace. No commit/push.

### Decisions

- Raw signal TTL **2 hours** (Mongo `expires_at` TTL index) — shorter than permissions registry’s illustrative 7-day consent metadata; raw GPS is sensor evidence, not Memory.
- Freshness: CURRENT ≤5m, RECENT ≤30m, else STALE; no signal → UNKNOWN.
- Bridge: capability `needs_client` → `client_actions` on turn → FE geolocation → `POST /api/location/signal` → `POST .../client-resume`.
- Reverse geocode: reuse `nominatim_reverse_city` (Life Setup); soft-fail → coordinate-only presence.
- Native: unsupported (no `expo-location`); background: unavailable.

### Files (main)

- `backend/location/*` (models, repo, service, caps, router)
- AI Core: registry, loop pause, orchestrator resume, prompt, context_broker, trace redact, life_os_context caps
- FE: `foregroundGeo.ts`, LocationPermissionSheet, OraConversationScreen bridge, settings Posizione, client APIs
- Tests: `test_ai_native_location_v271.py`

### Tests

- Location suite + V1–V2.6.2 focused: **180 passed** (`-n0`)
- Live interactive browser permission QA: **pending CPO**

**NO COMMIT / NO PUSH.** stash@{0} untouched.

---

## 2026-08-15 — Prompt V2.6.2 Context change & persistent replanning

### Request

After file reconciliation, Continua con ORA + “vincolo tempo cambiato” answered “Sto evitando di ripetere la stessa operazione.” Fix generic cross-turn adaptation. No commit/push.

### Root cause

`run_cognitive_loop` loaded `tool_signatures` from **session** state. Prior-turn `update_plan`/`update_object` fingerprints blocked later turns. Governance converted the block into user-facing copy.

### Fix

- Reasoning epoch per turn; idempotency only within the turn; reuse prior observation on same-turn duplicate
- Clear cross-turn ban list; keep `last_mutations` for observability
- Prompt + Life OS context: new facts may supersede persisted constraints
- `user_fact_summary` → conversational evidence; merge must not let conversation supersede `user_file`

### Live (scripted)

Plan `lop_93e3f8760a2c4e` same; object `lgo_95b229af1a934e` rev 2→3; script item 12→5; session `ces_2930e157b4094e`.

**NO COMMIT / NO PUSH.**

---

## 2026-08-14 — Prompt V2.6.1 Source-grounded reconciliation

### Request

After V2.6 file evidence, Goal Workspace showed old assumed plan items **plus** new ones (append). Fonti showed internal ids. Fix generic reconciliation + human sources + light theme renderer. No commit/push.

### Root cause

`LifeOsService.update_plan` only supported `add_items` (append) and `item_updates`. V2.6 QA / AI path used `add_items`, so assumptions survived. Fonti fell back to `ev.ref` (`lcf_`/`doc_`). GenerativeObjectRenderer used static `tokens.color` (dark default) inside light Workspace cards.

### Fix

- `replace_items` + `reconciliation_mode` + `remove_item_ids`; observation retained/removed/added
- PlanItem `origin`; EvidenceRef `display_name`/`status`/`source_*`; `public_evidence_sources`
- Workspace Fonti from `public_sources`; renderer `useTheme`

### Live QA

- Plan `lop_0aecb72a15cf49` same; target `2026-08-23`; session `ces_d45b4b7de74d42`
- Items: 8 mixed → 5 official modules; Spazi/QR/legacy gone
- Object `lgo_44b1f457f1c247` rev 8→9
- Fonti: `Programma ufficiale QA Matematica Computazionale.pdf` · Fornito da te

**NO COMMIT / NO PUSH.**

---

## 2026-08-14 — Prompt V2.6 AI-native files, evidence & context

### Request

Give ORA a general capability to receive user files as evidence, make them available to AI Core, and let AI decide whether to update existing plans/objects — no domain PDF workflows. Fix capability honesty (paperclip was a stub). No commit/push.

### Audit (Phase A summary)

| Component | Class |
|-----------|--------|
| Documents V2 upload/extract/storage | REUSE |
| OraComposer paperclip stub | EXTEND |
| AI Core MessageBody / orchestrator | EXTEND |
| evidence_refs / Life OS update_* | EXTEND |
| Life Setup DocumentPicker UX pattern | EXTEND (pattern only) |
| Gemini chat multimodal vision | DO NOT USE (unavailable) |
| Drive connectors / StudyFlow / Prompt 7.x | DO NOT USE |

### Implemented

- `ContextFile` + `ContextFileService` (Documents V2 blob + `life_os_context_files`)
- Upload API `POST /api/conversation/ai-core/files/upload`
- Caps: `list_session_files`, `get_file_context`, `get_file_content`, `link_file_context`
- Orchestrator bind attachments; file-only turns; session_files in life_os context
- Prompt: untrusted file data, capability honesty, same-plan adaptation
- FE: real OraComposer attachments + `aiCoreFileUpload`; Workspace Fonti
- Tests: `test_ai_native_files_v26.py` (16); live script `_qa_files_v26_live.py`

### Live QA (scripted cognition on real DB)

- Plan **before/after**: `lop_0aecb72a15cf49` (same)
- Object **before/after**: `lgo_44b1f457f1c247` rev **7 → 8**
- Evidence: `USER_PROVIDED_CONTENT` / `doc_8f6a9d2aeeef` / `programma_ufficiale_qa.txt`
- AI_CALLS=4 TOOL_CALLS=3; session_files=1; memory injection dump=0
- HTTP upload 200; ownership cross-user get=None
- Non-study uploads: bolletta / contratto / ambiguo (generic, no handlers)
- Image vision: `unavailable` (honest)

### Result

Plumbing proven: upload → extract → AI read → same plan/object update + evidence. **NO COMMIT / NO PUSH.**

---

## 2026-08-13 — Prompt V2.5.1 Blank Home runtime fix

### Request

After V2.5, `http://127.0.0.1:8081/` was a blank white page. Fix frontend/runtime only. No commit/push.

### Exact error (Metro)

```
Unable to resolve "./nav" from "src\ora\startOraConversation.ts"
```
Import stack: `OraInput` → `startOraConversation` → `./nav` (Home/Ambient pull this into the app graph). Later also `Unable to resolve "@/src/ora/nav"`.

### Root cause

Metro could not resolve module `nav.ts` under `frontend/src/ora/` (file existed on disk; Node could see it; Expo bundler could not). Blank page = failed web bundle.

### Fix

Rename to `oraNav.ts`, update imports, delete `nav.ts`. Regression: `test_ora_nav_module_resolvable_for_metro`.

### Result

Metro `Web Bundled` succeeds; `/ora` production surface renders. **NO COMMIT / NO PUSH.**

---

## 2026-08-13 — Prompt V2.5 Production ORA surface integration

### Request

Integrate AI-native runtime into Home / Ambient ORA / Goal Workspace so there is one ORA. `/ora-ai` becomes DEV-only. Quiet Premium Workspace. No commit/push.

### Implemented

- Production routes `/ora`, `/ora/{sessionId}` + shared `OraConversationScreen` / `OraComposer`
- Home `OraInput` + Ambient tab → `startOraConversation` → AI Core (no CE→AE)
- Workspace Continua / per-object CTA → `/ora` + `lifeOsSessionFocus`
- `buildOraConversationHref` / opaque URL state; AI Core `route` → `/ora/{id}`
- Goal Workspace Quiet Premium (`AppScreen`, `ScreenHeader`, `AppCard`)
- Daily Focus card press uses canonical Home nav (no Life OS → AE bypass)
- Tests `test_ora_surface_v25.py` + `nav.regression.mjs`

### Result

One conversation runtime for production entry points. `/ora-ai` marked DEV. Stash 7.x untouched. **NO COMMIT / NO PUSH.**

---

## 2026-08-13 — Prompt V2.4.3 GenerativeObject reveal contract

### Request

Goal Workspace “Tocca per rivelare” left the card blank. Fix generic GenerativeObject render/interaction contract only. No AI cognition / Home / commit / push.

### Audited live object (`lgo_44b1f457f1c247`, rev 7)

`content.blocks`: heading, text, then `card` with `title` set and **empty** `front`/`back`. No hidden reveal text existed in persistence.

### Root cause

**A + B + D** (not CSS): AI left reveal fields empty; schema accepted it; FE mapped only `front`/`back` and always showed reveal affordance → blank on click.

### Implemented

- Canonical item: `{ front, back, revealable }` via `normalize_reveal_card_item`
- Compat aliases: front←`front|question|prompt|title|text`; back←`back|answer|reveal|hidden|body|detail`
- Validator: `card_deck` requires non-empty front+back after normalize; single `card` may be static
- API display normalize in `GenerativeObject.public()`
- FE `revealCard.ts` + `CardDeck`: reveal only if `revealable`; fallback never blank; `reveal` event; nav resets

### Tests

- `test_generative_card_reveal_v243.py` + `revealCard.regression.mjs`
- V2.4 / V2.4.2 / V2.1–V2.3 AI suites: **106 passed** (38+68 focused batches)

### Live QA

`public()` → front from title, `revealable: false`. Browser workspace blocked (no bearer). Stash 7.x untouched. **NO COMMIT / NO PUSH.**

---

## 2026-08-13 — Prompt V2.4.2 Persistent object adaptation

### Request

Conversational “spiegamelo più semplice” did not call `update_object`; Goal Workspace stayed stale. Fix generically. No Home ranking changes. No commit/push.

### Root cause

AI payload only had `active_plan_id` / bare ids — no `active_object_ref`. Prompt under-specified durable vs chat-only adapt. Persist-before-claim ignored “ho semplificato…”. Workspace Continua did not bind object focus on the session.

### Implemented

- `ai_core/life_os_context.py` — hydrate + lightweight refs/previews
- Prompt section on durable object adaptation (AI-owned decision)
- `update_object` append/remove blocks, revision, evidence preserve, adaptation_note
- Loop: inject object_id, adapt-claim nudge, set active ref after writes
- `/life-os/session-focus` + Workspace/ora-ai continuity
- Tests `test_ai_native_object_adapt_v242.py`

### Live QA

Matematica object `lgo_44b1f457f1c247`: rev 1→2 (simplify) →3 (append example); same id. Non-study checklist shorten via same path.

### Tests

V1–V2.4.2 focused suite: **117 passed**. Stash 7.x untouched. **NO COMMIT / NO PUSH.**

---

## 2026-08-13 — Prompt V2.4.1 Canonical Home integration

### Request

Life OS plan visible in Contesti but Home Daily Focus still dominated by expired/legacy Psychology Study/Decision state. Fix canonical ownership, ranking, routing, stale suppression. No AI cognition redesign. No commit/push.

### Root cause (audited, not guessed)

1. Past plan deadlines received bill-style **overdue boosts** (+26–40) plus Goal Engine factors.
2. Legacy `action_engine_study` **decisions** were not plan shells → treated as real overdue debt.
3. `EXPIRED_RECOVERABLE` study shells + Goal boosts could still become Daily Focus.
4. Primary selection did not prefer freshest **Life OS plan shell** over reminders/decisions.

### Implemented

- `home/temporal.py` + ranking `home-rank-1.4` (canonical_active, fresh_canonical, expired penalties)
- Study / decision / reminder adapters: `plan_shell`, ownership, temporal_state
- Daily Focus: skip stale/recoverable when canonical actionable exists; pick freshest Life OS shell
- Horizon FE: skip EXPIRED_STALE / past calendar days
- Contesti: hide exam-day study with no open session; DEV presentation_trace
- `dev_rank_trace` on HomeResponse; DEV cleanup script (QA provenance only)
- GenerativeObject `revision` bump on `update_object`
- Tests: `test_home_canonical_life_os_v241.py` (A–T style)

### Live QA (user with Life OS + 13 legacy study plans)

- Daily Focus: **Matematica Computazionale** Life OS → `/goal-workspace/lop_0aecb72a15cf49`
- Continue: same Life OS plan
- Contesti: Matematica Life OS present; past exam-day Psychology study suppressed; future distinct Psychology rows remain
- Adaptation: **no** `update_object` in linked session — object unchanged

### Tests

`test_home_canonical_life_os_v241.py` + V2.3/V2.4 generative: **55 passed** (focused). Stash 7.x untouched. **NO COMMIT / NO PUSH.**

---

## 2026-08-13 — Prompt V2.4 Generative Workspaces (remove predefined artifacts)

### Request

CPO direction: stop predefined flashcards/quiz/map/guide cognition. AI authors declarative GenerativeObjects; app provides primitives + renderer. No commit/push.

### Removed / deprecated (AI-native path)

- Closed `generate_artifact` capability + type-specific `artifact_gen` product pipeline
- Prompt/loop product nouns forcing flashcards/maps as features
- Life OS Home decisions routing into legacy Action Engine `/action`

### Added

- `GenerativeObject` + `validate_generative_spec` (safe UI primitives)
- Caps: `create_object`, `update_object`, `get_object`, `list_goal_objects`, `record_object_interaction`
- Goal Workspace FE `/goal-workspace/[planId]` + `GenerativeObjectRenderer`
- HTTP `/api/life-os/plans/{id}`, `/objects/{id}`, interact
- Stale-context demotion for ambiguous new goals vs historical subjects
- Tests `test_ai_native_generative_v24.py`; V2.3 suite updated

### Retained

LifeOsPlan, create_plan/update_plan/create_actions, evidence calibration, persist-before-claim, Home/Life Map wiring (routes → Goal Workspace).

### Result

`conversation_engine/tests/`: **90 passed**. Stash 7.x untouched. **NO COMMIT / NO PUSH.**

---

## 2026-08-13 — Prompt V2.3 generic Life OS plans, artifacts & Home execution

### Request

Extend AI-native core so conversation can create durable Life OS state (plans, actions, artifacts) without StudyFlow/TravelFlow/etc. Wire Home/Continue/Horizon. Fix raw Markdown in `/ora-ai`. No commit/push. Stash 7.x untouched.

### Implemented

- `backend/life_os/` — domain-neutral `LifeOsPlan` / `PlanItem` / `LifeOsArtifact` + evidence calibration
- Capabilities: `create_plan`, `update_plan`, `create_actions`, `generate_artifact`, `get_active_plan`, `mark_plan_progress`
- Goal Engine upsert (generic) + Decision actions for Home
- Home adapter `life_os_plan` + actions/Continue route to `/ora-ai/{session}`
- Life Map situations for active Life OS plans
- Staged generation budgets (writes/artifacts); partial failure first-class
- `/ora-ai` `RichOraText` (headings/lists/emphasis/math cleanup)
- Tests `test_ai_native_life_os_v23.py` A–Z

### Principle

AI decides what. Life OS capabilities execute how. Legacy Study/Travel remain infrastructure, not conversational brains.

### Live QA (2026-08-13, local)

Exam dialogue → `create_plan` + `create_actions` (and staged artifacts). Mongo: plan `target_date=2026-08-23`, Home `primary_focus` from Decision `origin=life_os`, surface `life_os_plan`, structured `flashcards`/`concept_map`/`guide` persisted. Persist-before-claim soft re-entry added so `note_intention` cannot fake durable plans. Trace aggregates always expose `tool_names` / `write_calls` / `artifact_generations`.

### Tests

`conversation_engine/tests/test_ai_native_life_os_v23.py` + V1/V2.1 regression: **51+ passed** (local). Full suite re-run before CPO stop.

---

## 2026-08-13 — Prompt 7 V2.2 general tool use & grounded external knowledge

### Request

Live Rome travel QA invented operational drive times/traffic without tools. Fix general epistemic/tool architecture (not a TravelFlow). No commit/push. Stash 7.x untouched.

### Implemented

- Tool Registry V2 (capability metadata: classification, side_effect, freshness, availability)
- `web_search` capability + provider failover Tavily → Brave → Gemini Search
- `ExternalObservation` evidence re-entry (search ≠ synthesis)
- Tool-before-claim + autonomous READ_ONLY policy in prompt/governance
- Query minimization; failure taxonomy; loop bounds (MAX_STEPS=6, tools=3, external=2)
- `current_facts.*` temporal scope (temporary overrides for active goal; no Profile rewrite)
- Quiet harness “Controllo…” + optional source lines
- Tests `test_ai_native_tools_v22.py` A–J; combined AI-core suite **55 passed**
- `.env.example`: `RESEARCH_ENABLED`, `TAVILY_API_KEY`, `BRAVE_SEARCH_API_KEY`, `GEMINI_SEARCH_ENABLED`

### Principle

AI reasons. Context = personal knowledge. Tools = external capabilities. Governance = epistemic confidence + side effects. Observations return to the same loop.

---

## 2026-08-12 — Prompt 7 V2.1 AI-Native personal context retrieval

### Request

Live “Come mi chiamo?” asked for the name despite account/Profile/Memory identity. Fix must be general (AI → Context Broker → re-entry), not keyword name branches. No commit/push.

### Root cause

Context Broker Stage A treated `LifeProfile` as a flat dict (always empty) and never loaded `users.name`. Gemini therefore saw no identity facts.

### Fix

- Stage A baseline: authenticated account display name + active goal (tiny, high authority)
- Stage B: semantic personal-context query → Profile/Memory with provenance/authority/status
- Prompt: authority-aware answers; prefer context before asking
- Loop: preserve original `user_message` on context re-entry; DEV payload size trace
- Governance: block over-broad context queries
- Tests: `test_ai_native_personal_context_v21.py` A–L

### Result

34 AI-core tests passed (20 V2 + 14 V2.1). No domain/name hardcoding. STOP for CPO.

---

## 2026-08-12 — Prompt 7 V2 AI-Native Cognitive Core (foundation)

### Request

Rebuild cognition AI-first after abandoning Prompt 7.x. No domain flows, no slot question templates. Foundation only. No commit/push.

### Implemented

- `backend/conversation_engine/ai_core/` — orchestrator, decision contract, prompt, context broker, tool registry, governance, bounded loop, fallback, trace
- API: `POST /api/conversation/ai-core/start|/{id}/message`, `GET /api/conversation/ai-core/{id}`
- Minimal FE harness `/ora-ai` with ScrollView + pinned composer
- Tests `test_ai_native_core_v1.py` A–T + generality (**20 passed**)
- Provider via existing `llm.manager.get_manager().chat` (mocked in tests)

### Principle

AI owns cognition. Deterministic code validates tools/state/memory candidates — does not script dialogue.

---

## 2026-08-12 — ORA Cognitive Reset (abandon Prompt 7.x)

### Request

Stop Prompt 7.x experimental cognitive architecture after failed live QA. Safety-stash uncommitted work; restore clean HEAD. Do not reimplement. No commit/push.

### Action

- Confirmed branch `feature/ora-quiet-premium-design-system` at `258cd85`
- `git stash push -u -m "backup: abandoned Prompt 7.x cognitive architecture"`
- Working tree clean at committed Life Memory baseline
- Recorded AI-first rebuild principle; no new cognitive engine code

### Result

Abandoned architecture recoverable from stash only. Stable product surfaces unchanged. Next: CPO architecture review for AI-first conversation loop.

---

## 2026-08-10 — Memory epistemic authority (Prompt 6.1.1)

### Request

Fix wrong clarify persona (“mi chiamo…”); stop marking Life Setup–stated facts as ambiguous; GPS ≠ residence. No commit/push.

### Root causes

- Life Setup NLP wrote first-person facts as `inferred`/`suggested` (skipped `user_said` when NLP hit the same key).
- Memory mapped inferred+0.55 → ambiguous → false “Da chiarire”.
- Gemini clarify prompt lacked fixed ORA-vs-USER roles.

### Fix

- Authority bands + `needs_clarification`; Life Setup utterance → `user_said`/`confirmed`; repair inferred durable utterance keys; account name boost; device/GPS cannot create known residence; Gemini persona constraints + reject bad questions.

### Tests

`test_life_memory_authority.py` A–J (+ account boost). Suite green.

---

## 2026-08-10 — Memory clarification loop (Prompt 6.1)

### Request

Turn Memory “Da chiarire” into an AI-native clarification loop via Gemini + governance + Life Profile write; Focus UX; no forms/taxonomy; no commit/push.

### Actions

- Clarification contract on MemoryItem (`slot`, `profile_targets`, `clarifiable`, soft statement language)
- `POST /api/life-memory/clarify/start|…/answer` + CE `origin=memoria` bridge (non-AE)
- Gemini question + free-text resolution; validate ids/targets; Profile `correct_fact` authority
- Additional facts → suggest only; Focus screen `/memory-clarify/[sessionId]`
- Memoria actionable “Da chiarire”; tests clarify A–O style

### Result

Ambiguous memories open ORA clarification Focus; confirmed/corrected update Profile and recompute Memory. Gemini failure keeps ambiguity.

---

## 2026-08-10 — Memoria Life Memory V1 (Prompt 6)

### Request

Redesign Memoria into AI-native personal memory: “Che cosa sa e ricorda ORA di me?” — not DB inspector, not Contesti clone. Audit sources; canonical API; identity/contradiction; optional Gemini wording; Quiet Premium UI; no commit/push.

### Architecture

- Package `backend/life_memory/`: assemble → identity → contradiction → optional Gemini polish → `GET /api/life-memory`
- Sources: Life Profile facts, durable study subject, user notes. Skip sensitive keys, weak inference, exam countdown (Contesti).
- FE: `frontend/src/components/memory/quiet/*` + `memoria.tsx`; prefer API; no silent FE invent on failure
- Legacy `/api/memory` notes+ask preserved

### Tests / verify

- `pytest life_memory/tests` (A–N)
- Frontend map unit test + tsc/eslint/export as run in session

### Gaps

Conversation→durable promotion; LO evidence hybrid deferred; Correct/Forget UI deferred (read-only V1).

---

## 2026-08-10 — Life Map Contesti runtime integration debug (Prompt 5.3.1)

### Request

Authenticated Contesti still showed Psicologia ×3 despite 5.3 tests. Trace real `/api/life-map`, FE fallback, cache, semantic SAME/RELATED; minimal fix; no visual changes; no commit/push.

### Root cause

Live uvicorn (started 2026-08-09, no `--reload`) predated Prompt 5.3: OpenAPI had **no** `/api/life-map` → Contesti `getLifeMap` 404 → `buildContextsMap` fallback → one row per study_plan. Identity code on disk was correct; runtime never served it. `life_map_snapshots` empty (cache not the mask).

### Semantic truth (three plans)

SAME situation (not two distinct exams): shared `home_item:hi_e56b48d7ae1a7ec2` lineage merges Aug-12/Aug-13; polluted `Studio: Psicologia` merges same-day via entity+anchor; pair with different dates alone is RELATED but transitive SAME via middle plan. Freshest → Aug-13 / “Esame tra 3 giorni”.

### Actions

- Restarted backend with current `life_map` router
- Contesti: validate API payload; DEV warn on fallback; pull-to-refresh `force=true`
- `LIFE_MAP_DEBUG` identity trace; regression tests CASE N + stale-lineage SAME
- Docs + `.env.example`

### Verification

- `GET /api/life-map?force=true` → **1** Psicologia + Vibo (`API_PSICO_COUNT 1`)
- `pytest life_map/tests` → **38 passed**
- Zero Contesti visual redesign

---

## 2026-08-10 — Life Map semantic identity & deduplication (Prompt 5.3)

### Request

Entity resolution so Contesti shows life situations, not duplicate DB rows (Psicologia ×3). No title hacks; SAME≠RELATED; Gemini consultant only; freeze Contesti visuals; no commit/push.

### Root cause (traced)

For `user_0ea622447cfc`: three active `study_plans` — `Psicologia` (Aug 12), `Studio: Psicologia` (Aug 12, Home title leaked into subject), `Psicologia` (Aug 13, same `source_priority_id` as first). Assemble emitted one row per `study_plan_id`.

### Actions

- `life_map/identity.py` + `gemini_identity.py`; assemble emits `SituationCandidate`; service resolves before presentation
- Level 1 lineage/source_id; Level 2 entity keys + temporal anchor; Level 3 capped Gemini; structured temporal conflict blocks unsafe Gemini SAME
- Canonical title prefers clean entity; freshest plan wins dates/href
- Tests A–N in `test_life_map_identity.py`

### Result

Screenshot shape → one Psicologia + Vibo when evidence establishes identity. No taxonomy hack.

---

## 2026-08-10 — Grounded Gemini Life Map vertical slice (Prompt 5.2)

### Request

Close 5.1 gap: grounded novel situations must reach Contesti presentation without taxonomy enums; evidence validation, stable IDs, dedup, det>AI, Gemini down/off. No commit/push.

### Root cause (5.1)

`merge_presentation` kept AI situations on interpretation only; Contesti filtered to `study|travel` + href.

### Actions

- `governance.py`: presentability, stable evidence IDs, merge/dedup
- Novel presentable situations → Life Map `situations` (empty href OK)
- FE: open `kind`, informational `LiveSituationRow`, `mapFromLifeMapApi`
- Tests: novel / hallucination / ambiguity / conflict / dedup / Gemini down / feature-off
- Docs: Life Map = derived projection; open semantics; conversation out

### Result

End-to-end vertical slice for open-semantic grounded situations. `LIFE_MAP_GEMINI` still default off.

---

## 2026-08-09 — AI-Native Life Map foundation (Prompt 5.1)

### Request

Audit Gemini / LO / Contesti; choose A/B/C; prepare Contesti for semantic Life Map without giant engine. No Contesti UI redesign. No commit/push.

### Decision

**Option B** — thin `backend/life_map/` on shared Provider Manager. Contesti UI unchanged; deterministic fallback preserved. `LIFE_MAP_GEMINI=0` by default.

### Actions

- Models + evidence-gated validation + deterministic assemble (profile/study/travel)
- Optional Gemini interpret + fingerprint cache `life_map_snapshots`
- `GET /api/life-map`; Contesti prefers API, FE compose on failure
- Docs: cognition principle; PRODUCT / DEVELOPMENT_STATE / CHANGELOG; `.env.example`

### Result

Foundation only — not “ORA understands whole life.” Novel AI situations stay on interpretation (not Contesti rows yet). Conversation→evidence not wired.

---

## 2026-08-09 — Contesti Life Map V1 (Prompt 5)

### Request

Replace Contesti placeholder with Life Map V1 on `feature/ora-quiet-premium-design-system`: IA/UX/presentation from real data only; Quiet Premium quieter than Home; no hardcoded taxonomy; no “+ Nuovo contesto”; no backend/Context Engine; Home/Life Setup/Memoria/Shell frozen; no commit/push — stop for CPO/CDO review.

### Actions

- Audit: Contesti ← Life Profile domains + active study/travel; skip Home priorities; skip LO shadow list for V1; no generic Context Detail
- FE: `frontend/src/components/contexts/quiet/*` + rewrite `app/(tabs)/contesti.tsx`
- Thin client: `api.lifeSetupProfile` + `LifeProfile` types (existing `GET /life-setup/profile`)
- Docs + `design_guidelines.json` Contesti rule

### Files

| File | Change |
|------|--------|
| `frontend/app/(tabs)/contesti.tsx` | Life Map screen |
| `frontend/src/components/contexts/quiet/*` | Header, sections, rows, empty/loading, `buildContextsMap` |
| `frontend/src/api/client.ts` | `lifeSetupProfile` + types |
| `docs/PRODUCT.md` / `ARCHITECTURE.md` / `DEVELOPMENT_STATE.md` / `CHANGELOG_AI.md` | Contesti Life Map |
| `design_guidelines.json` | Contesti = Life Map rule |

### Tests / verify

- Baseline: `npx tsc --noEmit` PASS; eslint Contesti PASS
- Final: `node --experimental-strip-types src/components/contexts/quiet/buildContextsMap.test.ts` OK; `tsc` PASS; eslint Contesti components PASS (client.ts pre-existing array-type warnings only); `npx expo export --platform web` PASS → `frontend/dist`
- Visual QA: authenticated Contesti screenshots deferred to CPO/CDO (browser automation blocked; Expo :8081 + API :8000 available locally)

### Result

Contesti is an editorial life map from existing contracts. Gaps: Context Detail, relationships, Life Objects UI, history. No commit/push.

---

## 2026-08-09 — Login Quiet Premium visual polish (Prompt 4.1)

### Request

Visual polish only on `frontend/app/login.tsx`: stronger ORA wordmark, editorial rhythm, Google > Email hierarchy without Deep Indigo on Google, quieter Email / “oppure” divider, readable register cue. No auth/routing/backend changes; no commit/push.

### Files

| File | Change |
|------|--------|
| `frontend/app/login.tsx` | Prompt 4.1 presentation polish |
| `docs/CHANGELOG_AI.md` | this note |

### Tests / verify

- `npx tsc --noEmit` PASS; `eslint app/login.tsx` PASS; `npx expo export --platform web` PASS → `frontend/dist`
- Visual QA: Screenshot A/B/C still manual (see OUTPUT §25)

### Result

Login hierarchy and typography tightened; handlers / modes / testIDs preserved.

---

## 2026-08-09 — Login Quiet Premium V1 (Prompt 4)

### Request

Presentation-only Login restyle on `feature/ora-quiet-premium-design-system`: Immersive canvas, Quiet Premium identity, no card; preserve auth methods / `routeAfterAuth` / Life Setup gate. No backend, no Shell/Home/Life Setup redesign, no commit/push.

### Actions

- Rewrote `frontend/app/login.tsx` on `ImmersiveScreen` + `useTheme` + `AppButton` / `AppInput` / `AppDivider`
- Canonical copy; desktop column max-width 460, optically above center; modes `buttons` | `email` + register toggle preserved
- Providers secondary/ghost; email submit primary Deep Indigo; tertiary register/toggle; humanized auth errors; double-submit guard
- Docs: PRODUCT / DEVELOPMENT_STATE / CHANGELOG

### Files

| File | Change |
|------|--------|
| `frontend/app/login.tsx` | Quiet Premium Immersive login presentation |
| `docs/PRODUCT.md` | Login Quiet Premium note |
| `docs/DEVELOPMENT_STATE.md` | Prompt 4 status |
| `docs/CHANGELOG_AI.md` | this entry |

### Tests / verify

- Baseline: `npx tsc --noEmit` PASS; `eslint app/login.tsx` PASS
- After: `npx tsc --noEmit` PASS; `eslint app/login.tsx` PASS; `npx expo export --platform web` PASS → `frontend/dist`
- No dedicated FE login unit tests; auth E2E helpers still use same `login-*` testIDs
- Visual QA: manual desktop Light/Dark + mobile (see DEVELOPMENT_STATE)

### Result

Login presents as Quiet Premium Immersive; auth contracts and post-auth routing unchanged.

### Open

- Manual Screenshot A/B/C for CPO/CDO review
- Google/Apple still credential-gated per environment
- Forgot password still absent (by design — no dead link)

---

## 2026-08-09 — Micro-batch 3.S Human Presentation Semantics

### Request

Human Italian `reason_summary` from structured factors (no `"Tipo travel"` leakage); study exam questions must not use Home/insight titles as exam identity. No ranking score/order change; no Shell/Home visual redesign; no commit/push.

### Actions

- Added `backend/home/reason_presentation.py` — `format_reason_summary` from factor codes + item type
- Wired in `ranking.score_item` / dampen path (replaced `"; ".join(labels)`)
- Study: removed `display_title`/`title` from exam identity; known/unknown question conventions; `plan_service` ignores `session.title`
- Removed DailyFocus `contains("Tipo ")` omit
- Docs: INTERNAL ≠ PRESENTATION

### Files

| File | Change |
|------|--------|
| `backend/home/reason_presentation.py` | new presentation formatter |
| `backend/home/ranking.py` | use formatter for `reason_summary` |
| `backend/action_engine/study/flow.py` | exam identity / questions |
| `backend/action_engine/study/plan_service.py` | no session.title as exam |
| `backend/action_engine/service.py` | doc search without title-as-subject |
| `frontend/src/components/home/quiet/DailyFocus.tsx` | remove Tipo omit |
| `backend/tests/test_home_v2.py` | human summary + score invariant |
| `backend/tests/test_study_action_flow.py` | A/B/C/D exam identity |
| `docs/ARCHITECTURE.md` / `DEVELOPMENT_STATE.md` / `CHANGELOG_AI.md` | 3.S |

### Tests / verify

- `pytest` focused 3.S + study e2e — **9 passed** (reason summary invariant; exam identity A/B/C/D; e2e Psicologia)
- Full `test_home_v2` + presentation + study: **48+ passed**; pre-existing `test_dedupe_same_event` still fails (unrelated)
- `npx tsc --noEmit` — **PASS**
- eslint `DailyFocus.tsx` — **PASS**
- `npx expo export --platform web` — **PASS** → `frontend/dist`

### Result

Presentation summaries human; ranking math unchanged; study questions use entity subjects only.

### Open

- Expanded “Perché” factor rows may still show internal `Tipo …` labels (summary fixed)
- Pre-existing `test_dedupe_same_event` failure
- Authenticated Screenshot A/B from 3.1 still manual

---

## 2026-08-09 — Application Shell V1 Visual Correction (Prompt 3.1)

### Request

Correct Shell V1 visuals on `feature/ora-quiet-premium-design-system`: desktop rail 72–88px (not 50/50), quiet rail polish, Action Focus decision width ~720, hide Focus understood-summary noise, safe Home presentation omit / document semantics; no backend, no Home redesign, no commit/push.

### Actions

- `AmbientTabBar` railWrap: removed `flex:1`; fixed `AMBIENT_RAIL_WIDTH` (80) + `alignSelf: 'stretch'`; quieter active (weight; no rail dots; ORA not FAB)
- `Tabs` `_layout`: `tabBarStyle` width/maxWidth synced to 80
- `useAmbientInset`: `paddingLeft` always 0; bottom clearance only for floating bar
- `FOCUS_DECISION_MAX_WIDTH` (720) + `FocusScreen.maxWidth`; Action uses it
- Action: `SHOW_UNDERSTOOD_SUMMARY = false` (keep `buildUnderstoodSummary` / session data)
- DailyFocus: omit `explanation.summary` when it contains `"Tipo "` (no Tipo→Viaggio map)
- Docs: Presentation Semantics Issue + exam title backend-only + visual QA repro

### Home files touched

| File | Reason |
|------|--------|
| `frontend/app/(tabs)/index.tsx` | **none this batch** (already shell paddingBottom only) |
| `frontend/src/components/home/quiet/DailyFocus.tsx` | Safe omit of engine `reason_summary` line with `"Tipo "` |

### Tests / verify

- `npx tsc --noEmit` — **PASS**
- eslint modified files — **PASS** (0 issues)
- `node --experimental-strip-types src/shell/actionLabels.test.ts` — **PASS**
- `npx expo export --platform web` — **PASS** → `frontend/dist`
- Screenshots A/B: auth-gated; manual steps in DEVELOPMENT_STATE (not captured this session)

### Result

Shell rail geometry + Focus presentation corrections applied; Home Frozen except safe summary omit; no backend/commit/push.

### Open

- Presentation Semantics Issue (full human Perché / factor labels)
- Backend exam title fix (`study/flow.py`)
- Authenticated Screenshot A/B capture

---

## 2026-08-08 — Application Shell V1 (Prompt 3 / Signature Language)

### Request

Implement Application Shell V1 on `feature/ora-quiet-premium-design-system`: Ambient / Focus / Immersive modes; Ambient IA Home · Contesti · ORA · Memoria · Profilo; Contesti placeholder; ORA → ConversationEngine; Focus chrome on Action; Home Frozen (padding only); no Life Setup / backend / commit / push.

### Actions

- New `frontend/src/shell/*` — modes, AmbientTabBar (+ desktop rail), FocusScreen/Chrome, ImmersiveScreen, transitions, ambient insets, action labels
- Tabs layout: custom Ambient tabBar; Contesti + ORA routes; Documenti/Aggiungi `href: null`
- Action `[sessionId].tsx` → Focus chrome + `useTheme`; Continua primary; hide fake 0%; map flow → Studio/Viaggio/…
- Home/Memoria/Profilo: Ambient clearance padding only; PrioritySection omits raw `insight` type label
- Docs + `design_guidelines.json` Signature Language / Shell V1
- Exam title bug documented (backend `study/flow.py`) — no FE hack

### Tests / verify

- `npx tsc --noEmit` — pass
- eslint changed files — pass (1 pre-existing unused `e` warning in memoria)
- `node --experimental-strip-types src/shell/actionLabels.test.ts` — pass
- `npx expo export --platform web` — pass (dist)
- Screenshots: Ambient shell auth-gated; manual repro in DEVELOPMENT_STATE checklist

### Result

Application Shell V1 foundation shipped in FE; Life Setup and backend untouched; no commit/push.

### Open

- Login Quiet Premium polish
- Backend exam title fix
- Visual QA on device / authenticated web

---

## 2026-08-08 — Sprint 4.2 Final Fix: question intent constrained

### Request

Gemini ACTIVE drifted on `mlc.life_places.home` (“gestire la giornata” / workplace) and used judgmental ack (“giustamente”). Constrain AI rendering to planner-owned question intent. Architecture A (one StrategistPlan call). Freeze MLC/gate/location/Docs/Home/auth/soft-exit. No FE. No commit/push.

### Actions

- `minimum_life_context.py`: `QUESTION_GOALS` + `question_goal_for_gap` / `safe_question_for_gap` (home + identity/situation/priority/responsibilities)
- `question_planner.py`: attach `question_goal` on MLC plans; `bind_planner_intent` merges planner gap into Gemini plan
- `reasoning_loop.py` / `reasoner.py`: binding `question_goal` in Gemini context; prompt forbids judgment + intent drift; planner computed before ONE Gemini call
- `conversational_voice.py`: `validate_spoken_question_for_goal`, `sanitize_acknowledgement`, `resolve_turn_question` (drift → deterministic SAFE question; judgment → sanitize/`Capito.`)
- Tests 4.2ff A–F in `test_conversational_experience.py`

### Results

- conversational + MLC + strategist foundation + life_experience: **88 passed**
- Workplace / “gestire la giornata” spoken_question → deterministic home-city fallback
- Ack “giustamente” sanitized; work+family meaning preserved without judgment

### Open

- Review before commit

---

## 2026-08-08 — Fix: acknowledgement reflects full user meaning

### Request

Acknowledgements dropped family/desire meaning when NLP only set `mlc.current_situation=lavoro`; rich `build_acknowledgement` override then emitted situation-only “il lavoro occupa…”. Prefer Gemini ack from `latest_user_message`; SAFE fallback = “Capito.” + question. Freeze MLC/gate/location. No commit/push.

### Actions

- `reasoner.py`: `latest_user_message` as primary ack evidence; work+family both required in prompt/regole
- `reasoning_loop.py`: `latest_user_message` + `acknowledgement_instruction` in Gemini context
- `life_setup/service.py`: stop passing rich `build_acknowledgement` as default override
- `conversational_voice.py`: SAFE “Capito.” when Gemini ack missing
- Tests 42b A–F + regression in `test_conversational_experience.py`

### Results

- conversational + MLC + strategist foundation + life_experience: **82 passed**
- Free-text path no longer overrides with situation-only `build_acknowledgement`

### Open

- Review before commit

---

## 2026-08-08 — Sprint 4.2: AI-Native Conversational Rendering (Architecture A)

### Request

Extend same-call Gemini `StrategistPlan` with user-facing copy (`acknowledgement`, `spoken_question`, `conversational_bridge` XOR ack). Validate then SAFE fallback. Fix critical bug: never `lavori come {priority sentence}`. Optional ONE Gemini wrap synthesis. Freeze MLC/gate/location/soft-exit/Home. No commit/push.

### Actions

- `models.py`: spoken fields on `StrategistPlan`
- `reasoner.py`: fact-bounded SYSTEM_PROMPT + schema + parse spoken fields
- `conversational_voice.py`: `looks_like_role_title` / `structured_work_role`, `validate_rendered_text`, `render_conversational_turn`, `safe_*_fallback`, `render_wrap_synthesis`; harden `_situation_phrase` / synthesize
- `conversation_planner.py` + `service.py`: prefer validated AI spoken text; async wrap
- Docs: DETERMINISTIC vs AI split in ARCHITECTURE.md
- Tests A–F + walkthrough + validation + mocked Gemini JSON

### Results

- conversational + MLC + strategist foundation + life_experience + documents: **137 passed**
- FE untouched (no tsc/eslint)

### Open

- Review before commit

---

## 2026-08-08 — Sprint 4.1 final: USER→ORA priority perspective

### Request

Fix synthesis/ack leaking user first-person priority text (`il mio tempo libero…` → “Ti preme soprattutto il mio…”). Render-time only; do not rewrite stored MLC facts. No MLC/gate/location/softExit/FE/docs sprawl.

### Actions

- `conversational_voice.py`: `render_priority_for_ora` (semantic Italian patterns + careful perspective rewrite); used in `synthesize_first_picture` and `build_acknowledgement`
- `near_mlc_bridge` unchanged (truthiness only)
- Tests A–F in `test_conversational_experience.py`

### Results

- Perspective tests A–F + conversational experience + MLC + strategist foundation + life_experience (+ documents): **127 passed**
- FE untouched (no tsc/eslint)

### Open

- Review before commit

---

## 2026-08-08 — Sprint 4.1 residual: Esci/Più tardi first-run soft-exit

### Request

Fix incorrect soft-exit visibility: Esci/Più tardi were tied to wrap `done` (`firstRunMandatory = !done`), so they never appeared until wrap and first-run vs resume was wrong. FE-only; no commit/push.

### Actions

- Source of truth: `allowSoftExit = Boolean(?resume=) || Boolean(start.resumed)`
- `showEsci` / `showPostpone` = `allowSoftExit && !done`
- Helper `frontend/src/life-setup/softExit.ts` + unit tests A–D
- `lifeSetupStart` client type includes `resumed?: boolean`
- `onExit` force start does not promote soft-exit (stays hidden unless `?resume=1`)

### Results

- Soft-exit unit tests A–D: **passed** (`node --experimental-strip-types src/life-setup/softExit.test.ts`)
- `tsc --noEmit`: **PASS**; ESLint on changed life-setup files: **0 errors**
- Backend actions (exit/postpone) left unchanged; FE gates visibility

### Open

- Review before commit

---

## 2026-08-08 — Sprint 4.1: Life Setup Walkthrough Corrections

### Request

Walkthrough UX/copy fixes on top of Sprint 4: auth CTA, hide Esci/Più tardi on first-run, thinking state, near-MLC + synthesis paraphrase, explain tone, location-assisted life_places. No MLC/Gate/Documents/Home/auth-backend changes. No commit/push.

### Actions

- Auth: “Nuovo? Crea un account” on initial buttons → email register mode
- FE: hide Esci / Più tardi while pre-MLC (`!done`); keep Salta tema; no Home access
  *(superseded residual: visibility now from resume/`resumed`, not `!done` alone)*
- FE: on send → user bubble + disable composer + “ORA sta pensando…” dots in thread (no modal)
- Voice: `near_mlc_bridge` no false “quadro chiaro” on thin knowledge; fact-grounded ack preferred
- Voice: rewrite `synthesize_first_picture` (independent facts, paraphrased priority, Guardia di Finanza phrasing)
- Explain: NUCLEUS benefit copy first-person (esp. immediate_priority)
- Location: turn action `use_current_location`; `navigator.geolocation` + `POST /api/life-setup/reverse-geocode` (Nominatim); confirm via `/confirm-location`; city only, no coord persistence; no expo-location
- Document turn actions: Non ora / Preferisco rispondere in contract
- Tests: refusal, document proposal, synthesis regressions, location (in `test_conversational_experience.py`)
- Thinking FE: static verification (no new test stack)

### Results

- Backend strategist/MLC/conversational/life_experience: **59 passed**
- Frontend: `tsc --noEmit` PASS; ESLint changed paths: 0 errors (pre-existing array-type warnings in client.ts)
- Frozen: MLC semantics, Gate, Documents V2, Home Quiet Premium, auth backend, Google OAuth

### Open

- Native (non-web) geolocation may be unavailable without a platform API — falls back to text city
- Nominatim soft-fail when offline
- Review before commit

---

## 2026-08-08 — Sprint 4: Life Setup Conversational Experience V1

### Request

First contact feels like an AI-guided conversation (copy, rhythm, acknowledgement, final moment, CTA). No Gate/MLC/Documents/Home architecture changes. Prefer strategist over frontend if/else. No commit/push.

### Actions

- Added `conversational_voice.py` (ack, near-MLC bridge, fact-grounded final synthesis)
- Greeting: brief ORA intro + one open question (`conversation_planner` + `question_planner`)
- Answer path: contextual ack from real facts; soft progress bridge de-duplicated
- Wrap: personalized first picture + continuous-learning line; CTA **Entra in ORA**
- Document proposal / catalog reasons: optional accelerator copy; Gemini prompts avoid jargon
- Frontend: CTA label from turn action; softer Exit/Più tardi notices; quieter header hint
- Tests: `test_conversational_experience.py` (+ existing MLC/strategist/life_experience)

### Results

- Backend strategist/MLC/conversational: **48 passed**
- Frontend: `tsc --noEmit` PASS; ESLint life-setup PASS
- Frozen: Gate, MLC v1 semantics, Documents V2 pipeline, Home Quiet Premium

### Open

- Manual new-user walkthrough (tests A–G) before next sprint
- Gemini quality still depends on key / enforce_mlc; deterministic fallback covers offline
- Review before commit

---

## 2026-08-08 — Sprint 3: Minimum Life Context V1

### Request

Life Setup ends when MLC is sufficient (5 semantic nuclei), not a fixed question sequence. Extend existing strategist/planner. No Home/Gate/Documents rewrite. No commit/push.

### Actions

- Added `backend/ai_life_strategist/minimum_life_context.py` (coverage + MLC gaps)
- `plan_next` / `enforce_mlc_on_plan` / Gemini prompt: wrap only if MLC sufficient
- Expanded `infer_known_from_text` for multi-nucleus extraction
- Persist `session.meta.mlc_coverage`; free-text answers bind to current `mlc.*` gap
- Tests: `test_minimum_life_context.py` scenarios A–F; updated strategist/life_experience expectations

### Results

- 38 strategist/MLC tests passed; frontend `tsc`/eslint clean on life-setup paths
- Home Quiet Premium + Gate Sprint 2B + Documents V2 unchanged

### Open

- Gemini may still propose off-MLC questions; `enforce_mlc_on_plan` corrects wrap
- Review before commit

---

## 2026-08-08 — Sprint 2B: Mount Life Setup Conversation behind Gate

### Request

Remount `LifeSetupConversationScreen` at `/life-setup`; close all Home bypasses; reliable complete via gate; Exit/Più tardi ≠ Home. No Home/Documents rewrite. No commit/push.

### Actions

- `app/life-setup/index.tsx` mounts conversation; placeholder rollback-only
- `gate.ts`: Home only if `session.status === completed` (or disabled); `completeLifeSetupGate` no longer treats skip as success
- Conversation: early exits via `routeByLifeSetupGate`; `onComplete` requires successful `lifeSetupComplete` then gate; Exit cancel + stay; Più tardi notice without `postpone_all`/Home

### Results

- Incomplete users cannot reach Home through conversation redirects
- Documents V2 flow and Home Quiet Premium untouched

### Open

- Manual Tests A–H on device/simulator
- Review before commit

---

## 2026-08-08 — Sprint 1: Life Setup Gate (Pre-Home)

### Request

Gate so incomplete Life Setup never reaches Home Quiet Premium. Placeholder Completa Setup. Persistent flag. No Home UI changes. No commit/push.

### Actions

- `src/life-setup/gate.ts` — local flag `ora.lifeSetupCompleted.<userId>` + backend status sync; fail closed to setup
- Placeholder at `/life-setup`; conversation preserved in `LifeSetupConversationScreen.tsx`
- Cold start `app/index.tsx`, `routeAfterAuth`, login, tabs shell redirect use gate
- Home components untouched

### Results

- New users → placeholder; Completa Setup → Home; reopen → Home via persisted flag
- Gate uses `ApiUser.user_id` (not `id`); `tsc --noEmit` clean on touched path

### Open

- Swap placeholder for conversational Life Experience next sprint (same gate)
- Review before commit

---

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
# 2026-08-18 — ORA V2.8.4 unified uncertainty and clarification

- Added optional typed `CognitiveDecision.uncertainty` with bounded missing information,
  ambiguities and reversible assumptions.
- Added general-purpose repeated-question protection keyed by AI-supplied semantic refs,
  clarification/context budgets and sanitized aggregate observability.
- Preserved Context Broker re-entry, Situation assumption supersession, governed Memory,
  failure honesty and persist-before-claim. No domain question flow or keyword router added.
- Added deterministic V2.8.4 regression coverage; no DB migration or dependency.
