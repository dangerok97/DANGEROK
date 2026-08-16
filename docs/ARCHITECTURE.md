# ORA — Architecture

## Prompt V2.7.1 — Foreground location + PresenceContext (2026-08-15; STALE refresh + Home handoff 2026-08-16)

```
Home Ask / startOraConversation
  → POST /ai-core/start (ONE cognitive turn; persist user message + message_id)
  → navigate /ora/{sessionId} only (no text/coords in URL)
  → OraConversationScreen GET history + pending_turn
  → if awaiting_client: fulfill client_actions once → client-resume
  → if completed: render history (user + ora)
```

```
AI get_current_location / get_current_presence
  → preference off → needs_client + request_location_permission (ORA consent)
  → STALE / no signal + while_using → needs_client + request_foreground_location
      (refresh: true on STALE; maximumAge 0 on FE)
  → CognitiveTurnResult.client_actions + pending_turn (persisted; survives navigation)
  → FE: sheet only for ORA consent; if while_using + Chrome granted → getCurrentPosition directly
  → POST /api/location/signal  (auth, user-scoped; reverse place label)
  → PresenceContext upsert (CURRENT)
  → POST /api/conversation/ai-core/{id}/client-resume
  → AI answers from CURRENT/RECENT — STALE never claimed as now
  → timeout/denied/unavailable recorded distinctly; transient errors clear on next user turn
  → pending_client_capability enables generic “try again” without hardcoding phrases
```

| Concept | Storage | Notes |
|---------|---------|--------|
| LocationSignal | `location_signals` | TTL **2h** via `expires_at`; not Memory |
| PresenceContext | `user_presence` | Latest per user; AI consumes `for_ai()` / broker slice |
| Preference | `users.settings.location_mode` | `off` \| `while_using` (≠ browser permission) |
| Freshness | CURRENT ≤5m, RECENT ≤30m, else STALE | UNKNOWN if none |

Native / background: **unsupported / unavailable**. No geofence→action. Residence remains Profile/Memory.

**Canonical:** Location is sensor evidence. Presence is contextual state. Meaning remains governed/AI-interpreted. Memory remains governed.

## Prompt V2.6.2 — Context change & turn-scoped idempotency (2026-08-15)

Invariant: **New evidence may invalidate persisted state. Idempotency is execution safety, not a ban on future adaptation.**

```
each user turn → new reasoning_epoch
same-turn identical tool_signature → reuse observation (no second write)
cross-turn same target + new fact → update_plan / update_object allowed
user_fact_summary → USER_PROVIDED_CONTENT (source_type=user_conversation)
user_conversation must not supersede user_file evidence
```

## Prompt V2.6.1 — Source-grounded reconciliation (2026-08-14)

```
new evidence → AI chooses reconciliation_mode
  preserve | patch | replace_scope | rebuild_from_evidence
update_plan:
  replace_items | remove_item_ids | add_items | item_updates
  → same plan_id; optional progress map by title; item.origin provenance
evidence:
  status active|superseded|historical
  public_sources[] for Workspace (human display_name only)
GenerativeObjectRenderer: useTheme() colors (not static dark tokens.color)
```

## Prompt V2.6 — ContextFile / AI Core file evidence (2026-08-14)

```
OraComposer paperclip
  → POST /api/conversation/ai-core/files/upload  (auth, Documents V2 storage)
  → ContextFile (life_os_context_files) + session_files in AI state
  → message attachments: [{file_id, display_name, mime_type}]
  → AI Core tools: list_session_files / get_file_context / get_file_content / link_file_context
  → existing Life OS: update_plan / update_object + evidence_refs (USER_PROVIDED_CONTENT)
```

- Blobs stay in Documents V2 (local/dev storage abstraction already there); messages hold refs only.
- Staged retrieval: lightweight `session_files` in Context Broker payload; full text via chunked `get_file_content`.
- No domain document routers. File text is UNTRUSTED DATA (prompt + observation notices).
- `runtime_capabilities` exposed to the model for capability honesty (`image_vision_multimodal: unavailable` today).
- Indexes: `life_os_context_files` on startup via `ContextFileService.ensure_indexes`.

## Prompt V2.5 — Production ORA surface (2026-08-13)

```
Home OraInput / Ambient ORA tab / Workspace “Continua con ORA”
       → buildOraConversationHref / startOraConversation
       → /ora/{sessionId}  (production)
       → POST /api/conversation/ai-core/*  (same AI Core runtime)
       → Life OS plans + GenerativeObjects → Goal Workspace
/ora-ai/* = DEV harness only (shared OraConversationScreen)
```

| Piece | Role |
|-------|------|
| Production ORA | `/ora`, `/ora/{sessionId}` — Quiet Premium conversation |
| Entry points | `home` \| `ora` \| `goal_workspace` \| `continue` \| `focus` \| `object` |
| Nav helpers | `frontend/src/ora/oraNav.ts`, `startOraConversation.ts` |
| Composer | `OraComposer` — shared; Home compact `OraInput` feeds same runtime |
| Session policy | Coherent thread; goal-bound work reuses `plan.conversation_session_id`; general ORA creates a new thread when starting fresh |
| Legacy boundary | CE→AE remains for genuine legacy items; new Life OS work never opens Study/Action wizards |

## Prompt V2.4 — Generative Workspaces (2026-08-13)

```
AI Core → create_plan / create_actions / create_object
       → life_os_plans + life_os_objects (declarative UI blocks)
       → Goal Workspace + Home / Contesti (same identities)
       → Observation → AI answer
```

| Piece | Role |
|-------|------|
| `GenerativeObject` | AI-authored durable object; `object_kind` is a label only |
| UI primitives | text, card_deck, timeline, task_group, relation_graph, … |
| Revealable card contract | Canonical `{front, back, revealable}`; `card_deck` requires both; API/FE normalize small legacy aliases (`title`/`question`/`answer`/…) |
| Governance | size/nesting/primitive/executable validation |
| Goal Workspace | `/goal-workspace/{planId}` + `GenerativeObjectRenderer` |
| Decisions from Life OS | route to Goal Workspace — never legacy `/action` |
| Budgets | MAX_STEPS=8, tools=5, writes=4, objects=2, external=2 |

Closed V2.3 artifact types (`generate_artifact` flashcards/quiz/…) removed from AI Core. Legacy StudyPlan/Travel/Action Engine unchanged as compatibility infrastructure.

## Prompt 7 V2.2 — Tools & grounded external knowledge (2026-08-13)

```
USER → AI
     → personal context (Context Broker) and/or READ_ONLY tool
     → Governance (capability, side-effect, query sanitize, budgets)
     → Observation (ExternalObservation / personal facts)
     → AI re-entry
     → answer | ask | finish | act
```

| Layer | Role |
|-------|------|
| Cognition | Chooses capability ids (`web_search`), never provider brands |
| Tool Registry V2 | Metadata: classification, side_effect (READ_ONLY / REVERSIBLE_WRITE / CONSEQUENTIAL_WRITE), freshness, availability |
| Provider layer | Tavily → Brave → Gemini Search failover for `web_search` only when prior fails / empty |
| Observations | Evidence snippets + authority hints; provider “answers” not authoritative |
| Epistemics | Tool-before-claim for current/operational external facts; no silent model substitution on tool failure |
| Temporal | `current_facts.*` for temporary/goal facts; durable Profile unchanged |

`web_search` ≠ live traffic / Maps routing / booking / weather APIs.

## Prompt 7 V2.1 — Personal context retrieval (2026-08-12)

```
USER → AI (Stage A: account name + goal)
     → if needs more: response_mode=context + semantic context_query
     → Context Broker Stage B (Profile/Memory, filtered, provenance)
     → AI re-entry (original question preserved) → answer
```

| Layer | Role |
|-------|------|
| Stage A | Tiny high-authority baseline (`users.name` as `structured_account`, active goal) — enables 1-call identity answers |
| Stage B | Semantic categories (identity/residence/employment/study/general) over Profile + Memory; no full dump |
| Authority | Reuses Life Memory `authority_band` / `memory_status_from_authority` — conflicts exposed, not flattened |
| Governance | Blocks over-broad queries (“entire database”, “full profile”) |

Unavoidable schema maps live only inside the Context Broker (Profile slot families via `normalize_slot`). They do **not** script dialogue.

## Prompt 7 V2 — AI-Native Cognitive Core (2026-08-12)

**AI owns cognition. Deterministic systems own capabilities and governance.**

```text
USER → AI ORCHESTRATOR → (optional Context Broker / Tool)
     → GOVERNANCE → OBSERVATION → AI again (bounded)
     → FINAL RESPONSE (answer | ask | finish | act)
```

Package: `backend/conversation_engine/ai_core/`

| Piece | Role |
|-------|------|
| `CognitiveDecision` | Structured AI decision (no domain slots) |
| Context Broker | Small relevant Profile/Memory pack (stage A/B) |
| Tool Registry | Semantic capabilities (`search_life_memory`, …) |
| Governance | Schema/tool/permission/state allowlist; memory = proposals only |
| Bounded loop | `MAX_STEPS=4`; duplicate tool signatures blocked |
| Provider | Generic `llm.manager` — not vendor-hardwired cognition |

HTTP (parallel to legacy AE Conversation path): `/api/conversation/ai-core/*`  
Production ORA: `/ora` (scroll + composer). DEV harness: `/ora-ai` (same components).

**Prompt 7.x — abandoned experiment** (stash only). Do not restore its readiness/requirements/discriminator orchestration.

## Conversation architecture reset (2026-08-12)

Prompt 7.x experimental cognitive orchestration (deterministic GoalRequirements / readiness / research discriminators owning dialogue) was **abandoned** after live QA failure. Uncommitted work is in git stash only; working tree restored to Life Memory baseline `258cd85`.

**Rebuild direction (not implemented yet):** AI-first orchestrator owns cognition (understand → ask|research|tool|act → re-enter). Deterministic layer owns auth, schemas, provenance, privacy, tool execution, safety, persistence. New domains add tools/capabilities — not question wizards.

## AI-Native cognition principle (Prompt 5.1, 2026-08-09)

```
REAL USER DATA
  → STRUCTURED ORA STATE          (= source of truth)
  → GEMINI SEMANTIC REASONING     (= cognition, optional)
  → STRUCTURED INTERPRETATION     (= validated JSON)
  → ORA VALIDATION / GOVERNANCE   (= engines)
  → HUMAN PRESENTATION            (= UI)
  → USER
```

| Layer | Role |
|-------|------|
| **Gemini** | Comprendere, classificare, collegare, sintetizzare, ambiguità — **non** database, non fatti inventati, non UI |
| **Structured data** | Source of truth (Life Profile, Study/Travel, Life Objects, …) |
| **Engines** | Governance / action / validation |
| **UI** | Presentation only |

**AI-NATIVE ≠ AI-INVENTED.**  
**AI failure must not erase deterministic user reality.**

Shared LLM path: `backend/llm/` (Provider Manager + `chat_json`). No second Gemini client.

### Life Map (`backend/life_map/`) — Contesti cognition foundation

- **Life Map = DERIVED SEMANTIC PROJECTION** — not memory, not source of truth, not taxonomy.
- **DATABASE RECORD ≠ LIFE SITUATION.** Contesti shows canonical life situations, not raw study/travel rows.
- **SAME ≠ RELATED.** Only `same` collapses Contesti rows; `related` stays separate (e.g. same subject, different exam dates).
- Pipeline:

```
evidence → identity resolution → canonical situations
        → optional Gemini interpretation → presentation → Contesti
```

- Identity (`identity.py`): Level 1 structured (`source_id`, shared `source_priority_id` lineage, future Life Object id) → Level 2 correlation (entity keys ∩ + same temporal anchor) → Level 3 Gemini consultant (capped pairs) → Level 4 do-not-merge.
- Entity keys are open-semantic (normalize + optional post-`:` segment) — **not** subject-specific hacks.
- Stable canonical IDs from sorted `source_refs` / evidence — never `hash(label)`.
- Gemini must not override structured temporal conflicts.
- **OPEN SEMANTICS:** novel situations need no frontend category enums.
- **DETERMINISTIC REALITY > AI INTERPRETATION** (`governance.py` + identity).
- `GET /api/life-map` — presentation-ready canonical rows; Contesti does not invent semantics or dedupe.
- Cache: Mongo `life_map_snapshots` = **DERIVED / REBUILDABLE**; Never SoT.
- Life Objects (future): `life_object_ids` on candidates already reserved as Level-1 identity signal — no LO refactor now.
- Contesti FE prefers `/life-map`, falls back to `buildContextsMap` only if the API fails/invalid (never overwrites a valid canonical payload). Pull-to-refresh uses `force=true`.
- `life_map_snapshots` caches optional Gemini interpretation only — identity/assemble always recomputed. Stale uvicorn without this router causes Contesti FE fallback duplicates.
- Local AI: `LIFE_MAP_GEMINI=1` + `GEMINI_API_KEY`; default `0`.

### Life Memory (`backend/life_memory/`) — Memoria cognition foundation (Prompt 6)

```
DATABASE RECORD ≠ MEMORY
MEMORY ≠ CURRENT CONTEXT (Life Map / Contesti)
AI INTERPRETATION ≠ EVIDENCE
```

Pipeline:

```
raw sources → normalize candidates → memory identity
           → contradiction governance → canonical memories
           → optional Gemini wording → Memoria UI
```

- **Sources V1:** Life Profile facts (primary), durable study *subject* (not exam countdown), user notes (`db.memories`). Travel projects / Home priorities / chat turns **out**.
- **Identity:** same slot family (e.g. `casa.city`) + same value → one memory; study entity keys merge polluted titles.
- **Contradiction:** stronger/fresher authoritative source supersedes; unresolved weak conflict → `ambiguous` (not false fact).
- **Gemini (`MEMORY_GEMINI`, default 0):** wording polish only via Provider Manager; hallucinated memory ids rejected; failure keeps deterministic statements.
- **`GET /api/life-memory`** — presentation-ready; Memoria FE must not invent memory from raw profile compose. On API failure → honest empty/error (`__DEV__` warn).
- **Cache:** `life_memory_snapshots` = Gemini wording only (fingerprint + TTL); assemble/identity always recompute.
- **Legacy:** `GET/POST /api/memory`, `POST /api/memory/ask` unchanged (notes + Q&A).
- **Life Objects:** hybrid path — LO = entity evidence authority later; V1 reads Profile first (no LO refactor).
- **Conversation→Memory:** CE slots stay session-local today; promotion to durable Profile missing (documented gap).
- **Controls:** `clarify=true` for ambiguous items; Correct/Forget form editors still off.
- **Clarification loop (Prompt 6.1):**

```
Memoria “Da chiarire”
  → POST /life-memory/clarify/start (or CE origin=memoria)
  → Gemini question (minimized pack) / deterministic fallback
  → Focus `/memory-clarify/{id}` free-text answer
  → Gemini structured resolution → validate targets/ids
  → LifeProfileService.correct_fact / apply_facts(suggest)
  → invalidate cache → recompute Life Memory
```

- Gemini never writes truth; hallucinated memory ids / unauthorized keys rejected.
- Additional facts from answers → `source=inferred` suggested only.
- CE session linked (`ui_mode=memory_clarify`) for continuity — **not** Action Engine.
- **Epistemic authority (6.1.1):** `user_confirmed` / `user_said` / account / document → **known** (not clarifiable). `inferred`/`suggested` → likely/ambiguous. Device/GPS ≠ residence known. Life Setup first-person NLP persists as `user_said` (not inferred). Clarify questions must address USER (never “mi chiamo…” as ORA).
- Local AI: `MEMORY_GEMINI=1` + `GEMINI_API_KEY`; clarify uses Provider Manager whenever available (soft-fail keeps ambiguity).
- `MEMORY_DEBUG=1` for evidence/resolution in response.

## Life Object Engine — modello canonico (SHADOW + Semantic Integrity + Digital Twin Knowledge, 2026-08-07)

**Life Objects = verità canonica sulla realtà dell’utente** (HOME, VEHICLE, UNIVERSITY, JOB, …).
**Gemini = consultant; backend = autorità** (Semantic Validator sempre prima del persist).
**Digital Twin Knowledge Model:** `facts` / `hypotheses` / `decisions` / `goals`(link) / `memory` + timeline semantica. **Fact mai cancellato** (supersede/archive). Hypothesis mai auto-promossa.
Conversation, Goal, Documents, Brain, Proactive, Home, Travel, Study **continuano a esistere**: non vengono eliminati. Diventano **satelliti / fonti** che leggono e aggiornano i Life Object — non posseggono più “la verità” da soli.
Enrichment backend: narrative versionata, questions, insights, temporal, health spiegabile; split **identity / state**. Gemini opzionale via Provider Manager; fallback italiano deterministico.

```
                 ┌──────────────────────────┐
                 │      LIFE OBJECTS        │  ← canonical truth (shadow writes)
                 └────────────▲─────────────┘
        read/write │          │          │
   Documents V2   Goal Engine   Brain / Conversation / Proactive
   Life Experience Travel/Study Home (ancora Goal-aware; V3 UI OFF)
```

- Package: `backend/life_objects/` — models, repository, service, reasoner, enrichment, semantic_validator, title_generator, property_registry, assimilation, link_states, knowledge_gaps, **knowledge_model/**, provenance, identity_state, home_v3, dedupe, linking, memory, router, shadow hooks
- Pipeline: Document → OCR → Document AI → Life Object AI → **Semantic Validator** → **Knowledge ingest** → Canonical Object
- Flags: `LIFE_OBJECT_ENGINE_ENABLED=1` (shadow ON), `LIFE_OBJECT_HOME_UI_ENABLED=0` (UX invariata), `LIFE_OBJECT_GEMINI=1` (fallback se assente)
- Collection: `life_objects` (`identity`/`state`/`facts`/`hypotheses`/`decisions`/`memory`/`narrative`/`insights`/`temporal`/`health` 2.0 + typed provenance)
- API: `/api/life-objects/*` + narrative/questions/insights/health/history/enrich + **`/{id}/facts|hypotheses|decisions|timeline|knowledge`** + minimal confirm/reject/outcome + `home-v3-feed` (auth; unused by main UI)
- Docs: `LIFE_OBJECT_*`, `LIFE_KNOWLEDGE_MODEL.md`, `DIGITAL_TWIN_MODEL.md`, `FACTS_HYPOTHESES_DECISIONS.md`
- **Home V3 Life Objects = PREDISPOSTO, non shippato.** Home resta Goal-aware.

## Life Setup Gate (Sprint 1 + 2B, 2026-08-08)

Application **initial state** before Home. Home Quiet Premium stays unaware.

```
Auth → resolveLifeSetupGate(userId) → /life-setup | /(tabs) Home
```

- Module: `frontend/src/life-setup/gate.ts`
- Local persistence: AsyncStorage `ora.lifeSetupCompleted.<userId>` (`1`/`0`)
- Unlock Home only when `session.status === 'completed'` (or feature disabled). `interrupted` / `skipped` / `cancelled` ≠ completed
- Offline: trust local completed; else fail-closed → life-setup
- Complete path: successful `lifeSetupComplete` → `completeLifeSetupGate(userId)` → `routeByLifeSetupGate`
- Entry points: cold start `app/index.tsx`, post-auth `routeAfterAuth`, tabs shell redirect (2nd line of defense)
- UI: `LifeSetupConversationScreen` at `/life-setup`; `PlaceholderLifeSetup` kept for rollback only
- Soft-exit (Esci / Più tardi): FE `allowSoftExit = ?resume= || start.resumed`; show only when `allowSoftExit && !done` (`frontend/src/life-setup/softExit.ts`). First-run incomplete never shows soft-exit; backend may still emit exit/postpone actions.

## Minimum Life Context V1 (Sprint 3, 2026-08-08)

First-launch wrap/`ui.done` is gated by **semantic MLC coverage**, not by exhausting `DOMAIN_GAPS` or a fixed question count.

```
answer → infer_known_from_text (+ profile) → evaluate_mlc_coverage → plan_next
  → wrap only if MLC sufficient → wrap_up_turn (ui.done)
```

- Module: `backend/ai_life_strategist/minimum_life_context.py` (`mlc-v1` **heuristic**, not irreversible domain law)
- Nuclei: `identity`, `current_situation`, `life_places`, `responsibilities`, `immediate_priority`
- **Addressed** = `covered` | `skipped` (explicit refuse/postpone) | `implicit` (rich core context). **Not** “question was asked” (`asked_keys` only de-prioritize)
- `immediate_priority` strongly preferred (one ask even when implicit); rich core (4 covered) can still suffice without perfect priority phrasing
- One utterance may cover multiple nuclei; planner asks highest-gain unaddressed gap
- NLP heuristics (`infer_known_from_text`) persist via profile `source=inferred` + `status=suggested` (`source_confidence` ~0.55) — not high-certainty
- Persistence: `known_facts` on sessions + `life_profiles`; `session.meta.mlc_coverage` (not a UI checklist)
- Documents V2 optional; Gate Sprint 2B unchanged

## Conversational Experience V1 + Walkthrough 4.1 + AI Rendering 4.2 (2026-08-08)

Copy/rhythm layer on top of MLC + Gate — **not** a frontend conversation engine.

```
greeting (deterministic shell + 1 open Q)
  → answer → infer facts (deterministic)
  → Gemini StrategistPlan SAME call: acknowledgement + spoken_question
      (+ conversational_bridge XOR ack) + next_best_question
  → render_conversational_turn validates AI copy → else SAFE deterministic fallback
  → MLC sufficient → ONE optional Gemini wrap synthesis (structured facts)
      → else hardened / SAFE wrap → CTA Entra in ORA
  → lifeSetupComplete → completeLifeSetupGate → Home
```

### DETERMINISTIC vs AI (Sprint 4.2 Architecture A)

| DETERMINISTIC (authority) | AI (Gemini via ProviderManager) |
|---------------------------|----------------------------------|
| MLC coverage, gaps, gate, completion | `acknowledgement` (≤1 sentence) |
| Fact inference & profile persistence | `spoken_question` (natural ask) |
| `next_best_question` + `question_goal` (intent) | Wording only — intent frozen by planner |
| Greeting shell, actions/UI contract | Optional wrap `spoken_text` (rare, end only) |
| Location / soft-exit / Home unlock | Quiet Premium Italian phrasing |
| SAFE fallbacks if Gemini fails / `force_fallback` | Must pass `validate_rendered_text` + goal check |

**Critical invariant:** never render `lavori come {x}` unless `x` is a short structured `lavoro.ruolo` title (`looks_like_role_title`). Free-text priority / responsibilities must not become a job title.

- Module: `backend/ai_life_strategist/conversational_voice.py` (`render_conversational_turn`, `validate_rendered_text`, `safe_*_fallback`, `render_wrap_synthesis`)
- Reasoner: same-call spoken fields on `StrategistPlan` (`reasoner.py`)
- Turn assembly: `conversation_planner.py` (greeting / active / wrap)
- No second Gemini call on the happy active-turn path
- No progress bar / checklist / % in UI; soft progress only when near-complete + rich facts (4.1)
- FE thinking: in-thread “ORA sta pensando…” while composer disabled (no modal)
- First-run pre-MLC: FE hides Esci / Più tardi (backend cancel/postpone unchanged)
- life_places assist: action `use_current_location` → browser geolocation → `POST /api/life-setup/reverse-geocode` (Nominatim city) → user confirm → `POST /api/life-setup/confirm-location` (city only; **no** coord persistence; **no** expo-location)
- User-facing strings must not expose MLC / coverage / Life Graph / planner jargon
- Documents V2 pipeline unchanged; proposal copy frames upload as optional accelerator; turn actions include Non ora / Preferisco rispondere

## Life Experience / Strategist (2026-08-06)

- AI-first Life Experience: reasoning loop every turn → structured `StrategistPlan`.
- Gemini via Provider Manager with structured context JSON; deterministic Italian fallback.
- CE origin `life_setup` accepted; route `/life-setup` = conversational Life Experience behind the Gate.
- Collections: `life_setup_sessions`, `life_profiles`.
- Home adapter: **Italian benefit cards** after setup («Adesso posso…») + soft resume if interrupted — **no** Life Setup section.
- Proactive generator: benefit-driven suggestions + soft resume; never «Completa il profilo».
- Docs: `LIFE_EXPERIENCE.md`, `AI_REASONING_LOOP.md`, `AI_PROMPTING_GUIDE.md`, `AI_DECISION_POLICY.md`, `CONVERSATION_EXPERIENCE.md`.
- Adapter stubs only: email, open_banking, whatsapp, weather.

## Stack

| Layer | Choice |
|-------|--------|
| Mobile/Web client | Expo 54, React Native, TypeScript, expo-router |
| API | FastAPI + Uvicorn |
| DB | MongoDB via Motor |
| Auth | JWT ORA (HS256) + bcrypt; Google/Apple ID-token verify (`backend/social_auth/`); Emergent bridge legacy optional |
| LLM | Provider Manager `backend/llm/` — Gemini (default) → OpenAI → Ollama → Emergent; failover automatico; non required at boot |
| Design system | **ORA Quiet Premium** + **Signature Language** — `design_guidelines.json`, `frontend/src/theme/*`, shell modes in `frontend/src/shell/` (`ambient` / `focus` / `immersive`), primitives in `frontend/src/components/ui/` |
| Local deps | `backend/requirements-local.txt` (Emergent CDN packages excluded) |

## Repository map

```
backend/
  server.py              # thin FastAPI entry
  deps.py                # env, db, auth helpers, service getters
  routers/               # HTTP routers mounted under /api
  decision_engine/       # ranking & decisions
  life_graph/            # nodes/edges
  knowledge/             # node knowledge
  auto_link/             # decision↔node proposals
  context_assembler/     # context snapshots
  permissions/           # consents & capabilities
  connectors/            # google_calendar, apple_calendar
  ingestion/             # event pipeline
  documents/             # document intelligence
  documents/intelligence/# pipeline, taxonomy, analyzer, calendar drafts
  home/                  # Home V2 aggregator + ranking + adapters
                         # INTERNAL ranking (codes/weights) ≠ PRESENTATION
                         # (reason_presentation.format_reason_summary → human Italian)
  intent_engine/         # Intent Classification — single brain for flow routing
  action_engine/         # Guided conversational flows (consumes Intent)
    study/               # Study plan model, generator, confirm, Google/tools/Brain
    travel/              # Travel Project: period, maps, calendar confirm, Brain/Home
  goal_engine/           # Goal identity/lifecycle (shadow; no Goal UX yet)
  proactive_engine/      # IF/WHEN/HOW/WHY intervene → suggestions + Home ORA TI CONSIGLIA
  conversation_engine/   # Entry orchestrator (NOT chatbot) → Semantic→Intent→Gap→Goal→AE
  semantic_engine/       # Structured extraction + Gap Analyzer (Gemini optional)
  ai_life_strategist/    # Life Experience reasoning loop + StrategistPlan (Gemini + IT fallback)
  life_setup/            # First-launch Life Experience session + Life Profile persistence/sync
  life_objects/          # Life Object Engine (core identity; SHADOW mode)
  daily_intelligence/    # daily summary (situation indicators)
  behavioral_intelligence/
  behavior_aware_decisions/
  explainability/
  action_center/
  social_auth/           # Google/Apple verify, identities, linking
  llm/                   # Provider Manager + adapters (gemini/openai/ollama/emergent)
  security/              # token vault
  tests/                 # pytest
frontend/
  app/                   # expo-router screens (Home Quiet Premium + /situazione)
  app/(tabs)/            # Ambient IA: Home · Contesti · ORA · Memoria · Profilo (Documenti/Aggiungi href:null)
  app/action/[sessionId] # Action Engine UI — Focus shell chrome (no Ambient nav)
  src/api/client.ts      # HTTP client incl. /home
  src/auth/              # Google/Apple client helpers
  src/shell/             # Application Shell V1: OraShellMode, AmbientTabBar, FocusScreen/Chrome, ImmersiveScreen
  src/components/home/quiet/ # Home Quiet Premium (+ polish 2.1: FocusActions, surface Focus, vertical Horizon)
  src/components/home/v2 # Legacy helpers + /situazione PrioritaList
  src/action-engine/     # ActionEngine.open(item) central entry
  src/conversation-engine/ # ConversationEngine.start → bridges to AE UI
  src/theme/          # Quiet Premium: tokens, palettes, ThemeProvider, motion, haptics, shadows
  src/components/ui/  # Design primitives (AppScreen, AppCard, AppButton, GlassContainer, …)
docs/                    # CONVERSATION_ENGINE_* + ACTION_ENGINE_* + HOME_V2_* + …
scripts/                 # local automation
.emergent/               # legacy Emergent runtime (non-portable)
.cursor/                 # Cursor autonomy rules/agents/hooks
```

## API surface (high level)

All routes under `/api` via `ALL_ROUTERS`:

- `auth` — register, login, google-session, me, logout
- `decisions`, `legacy_tasks`
- `life_graph`, `knowledge`, `auto_link`, `context`
- `permissions`, `connectors`, `ingestion`
- `google_calendar`, `apple_calendar`
- `daily`, `behavior`, `behavior_shadow`
- `documents`, `home` (V2 intelligence dashboard), `intent`, `action-engine`, `goals` (Goal Engine — backend only, unused by UI), `life-objects` (Life Object Engine — shadow; unused by main UI), `suggestions` (Proactive Engine), `conversation` (Conversation Engine orchestrator), `admin`, `memory`

Health:

- `GET /api/` → `{ "app": "ORA", "status": "ok" }`
- `GET /api/health` → app + database + llm configured flag + integration flags (no secrets)
- `GET /api/home` → Home V2 aggregate (`primary_focus`, situation, priorities, insights, resume, `ora_ti_consiglia` ≤3, warnings); ranking `home-rank-1.4` with temporal ownership (`ACTIVE` / `UPCOMING` / `EXPIRED_*` / `SUPERSEDED`) so actionable canonical LifeOsPlan shells outrank stale legacy plan decisions; Life OS CTAs → `/goal-workspace/{planId}`; optional `dev_rank_trace` when `HOME_RANK_TRACE`/`DEV`; Goal-aware when `GOAL_ENGINE_ENABLED` (item `goal_*` refs + dedupe — `docs/GOAL_AWARE_HOME.md`); Proactive when `PROACTIVE_ENGINE_ENABLED` — `docs/PROACTIVE_ENGINE_ARCHITECTURE.md`; Conversation resume via CE adapter — `docs/CONVERSATION_ENGINE_ARCHITECTURE.md`
- AI Core Life OS context: session `active_object_ref` / `current_plan_item_ref` / recent object refs (previews only); durable adaptations via `update_object` (revision + evidence preserve); `POST /api/life-os/session-focus` binds Workspace → chat continuity
- `/api/conversation/*` → start / message / continue / cancel / resume / history / summary (flag `CONVERSATION_ENGINE_ENABLED`); Conversation resume items when `CONVERSATION_ENGINE_ENABLED` — `docs/CONVERSATION_ENGINE_ARCHITECTURE.md`
- `POST /api/conversation/start|resume` + `/{id}/message|continue|cancel|pause` + history/summary — entry orchestrator (bridges to Action Engine UI)
- `GET /api/home/situation` → full situation view payload
- `POST /api/home/actions` → complete / snooze / ignore / correct / insight / banner
- `POST /api/home/refresh` → rebuild ranking snapshot
- `POST /api/intent/classify` → Intent Classification Engine (deterministic; optional LLM enrich)
- `POST /api/action-engine/open` → classify Intent → start/resume guided flow
- `GET /api/action-engine/sessions/{id}` → session + current turn
- `POST /api/action-engine/sessions/{id}/answer|back|draft|search-docs|preview|modify|confirm|complete|cancel`
- `GET/PATCH/DELETE /api/study-plans/{id}` (+ sessions actions, sync/retry)
- Mongo: `study_plans`, `study_sessions` (UTC; default TZ Europe/Rome)
- Goal Engine (shadow + Home context; **no Goal UX**): `GET/POST/PATCH/DELETE /api/goals`, `POST /api/goals/search|merge`, `POST /api/goals/{id}/archive`, `GET /api/goals/{id}/timeline`
- Mongo: `goals`, `goal_events` — Study/Travel confirm upserts Goals when `GOAL_ENGINE_ENABLED=1`
- Life Object Engine (shadow + enrichment + Digital Twin Knowledge): `GET/POST/PATCH/DELETE /api/life-objects`, search/merge/link/reason/trend/status; `/{id}/narrative|questions|insights|health|history|relationships|temporal` + refresh/enrich; `/{id}/facts|hypotheses|decisions|timeline|knowledge` (+ confirm/reject/outcome write minimi); `GET /home-v3-feed` (OFF). Mongo `life_objects`. Shadow hooks from Documents consume, Goal upsert, Travel/Study confirm → best-effort enrich + knowledge ingest. `LIFE_OBJECT_HOME_UI_ENABLED=0` → no Home UX change.
- Proactive Engine: `GET/POST /api/suggestions/*` (list, regenerate, search, dismiss/accept/complete/snooze/explain); Mongo `proactive_suggestions`, `proactive_learning`. Email/Finance/Weather/Health/WhatsApp **predisposed only** — never invent facts.

## Application Shell V1 (Signature Language)

Three presentation modes (`OraShellMode` in `frontend/src/shell/`):

| Mode | Role | Chrome |
|------|------|--------|
| `ambient` | Life OS browsing (tabs) | `AmbientTabBar` — floating glass bottom on phone/tablet; compact left rail **fixed `AMBIENT_RAIL_WIDTH` (80px)** at `desktop` breakpoint (`useBreakpoint`, not `Platform.OS===web`). Rail must not use `flex:1` (that stole ~50% width). Scene = remaining viewport. `useAmbientInset` only clears bottom bar — never `paddingLeft` for the rail. |
| `focus` | One-task guided work | `FocusScreen` + `FocusChrome` — single back **or** close, progress “N di M” when known, no Ambient nav. Action decision column uses `FOCUS_DECISION_MAX_WIDTH` (720), independent of Home editorial width. |
| `immersive` | Full attention | `ImmersiveScreen` foundation (Life Setup / deep flows keep their own UI) |

Primary Ambient IA: **Home · Contesti · ORA · Memoria · Profilo**. Documenti and Aggiungi stay as routes with `href: null` (reachable from Profilo). Center **ORA** opens the Conversation Engine Ask path (`/(tabs)/ora` + `OraInput`), not Aggiungi and not a chat. Glass via `GlassContainer` for Ambient nav only. Ambient ↔ Focus transition ~240ms; respects reduce-motion.

**Contesti Life Map V1 (Prompt 5):** Ambient screen `/(tabs)/contesti` composes existing reads only — `GET /life-setup/profile`, `GET /study-plans`, `GET /travel-projects` — via `frontend/src/components/contexts/quiet/` (`buildContextsMap`). No Contesti/Context Engine backend, no Life Graph UI, no Home priorities reuse. Sections omit when empty. Presentation labels for domains mirror `DOMAIN_LABELS_IT` (FE) without inventing missing areas. Life Objects list APIs exist (shadow) but are **not** wired into Contesti V1 to avoid duplicate/HOME-flag coupling.

Action proof path: `/action/[sessionId]` uses Focus chrome + `useTheme` (Light/Dark). Understood-summary chips are presentation-hidden in Focus (session slots unchanged).

**INTERNAL ≠ PRESENTATION (Micro-batch 3.S):** Ranking keeps `ReasonFactor` codes/weights for score/order. `reason_summary` / `explanation.summary` are human Italian from `home.reason_presentation` (never `"Tipo travel"` label joins). Study exam questions use entity `subject`/`exam` only — never Home/insight `title` / `display_title` as exam identity (`Quando è l'esame di {Subject}?` vs neutral `Quando è l'esame?`).

## Local topology

```
MongoDB :27017  →  FastAPI :8000  →  Expo web :8081 (EXPO_PUBLIC_BACKEND_URL)
```

Local Google OAuth: `localhost` and `127.0.0.1` are different browser/API origins. Dev accepts both loopback twins for Calendar callback + frontend `redirect_after`; Google Cloud Console must still list both explicitly (Sign-In web client on `:8081`, Calendar callbacks on `:8000`).

## Data store

MongoDB collections created/indexed at startup (users, tasks, decisions, life_nodes/edges, node_knowledge, link_proposals, context_snapshots, memories, permission_*, ingestion_events, connector_instances, secret_vault, google_oauth_sessions, documents-related, `home_snapshots` / `home_item_state` / `home_insights`, behavioral collections, `goals` / `goal_events`, `life_objects`, `proactive_suggestions` / `proactive_learning`, …).

Document binaries: local storage under `backend/data/documents/` (S3 backend stubbed for future).

## External integrations

| Integration | Path | Local notes |
|-------------|------|-------------|
| Emergent Google login | `auth.emergentagent.com` + demobackend session-data | Not portable |
| Emergent LLM | `emergentintegrations` + `EMERGENT_LLM_KEY` | Key + package required |
| Google Calendar OAuth + write sync | `connectors/google_calendar` + `documents/intelligence/google_sync` | Scopes `calendar.events`; vault Fernet; see `docs/GOOGLE_CALENDAR_ARCHITECTURE.md` |
| Documents V2 (intelligent actions) | `documents/` + `intelligence/{service,study_tools,admin_extract}` + FE `DocumentUtilityPanel` | Pipeline `intel-docs-2.0`; study/quiz/admin APIs; see `docs/DOCUMENTS_V2_ARCHITECTURE.md` |
| Apple Calendar | expo-calendar / mock flag | Device or mock |
| litellm wheel | Emergent asset URL in requirements | May fail outside Emergent |

## Hosting / deploy (current)

- Historical preview: `https://ora-decision-engine.preview.emergentagent.com`
- iOS package id: `com.emergent.oradecisionengine.b7escs`
- Cursor-local target: Mongo + uvicorn `:8000` + Expo (`EXPO_PUBLIC_BACKEND_URL`)

## Local run (summary)

See `README.md` and `scripts/dev`. Details and gaps live in `docs/DEVELOPMENT_STATE.md`.
