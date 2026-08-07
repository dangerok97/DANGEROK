# ORA — Architecture

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

## Life Experience / Strategist (2026-08-06)

- AI-first Life Experience: reasoning loop every turn → structured `StrategistPlan`.
- Gemini via Provider Manager with structured context JSON; deterministic Italian fallback.
- CE origin `life_setup` accepted; route `/life-setup` = Life Experience UX (not wizard).
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
| Design system | **ORA Quiet Premium** — `design_guidelines.json`, `frontend/src/theme/*` (tokens, palettes light/dark, ThemeProvider, motion/haptics/shadows), primitives in `frontend/src/components/ui/` |
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
  src/api/client.ts      # HTTP client incl. /home
  src/auth/              # Google/Apple client helpers
  src/components/home/quiet/ # Home Quiet Premium V1 (DailyFocus, OraInput, Horizon, …)
  src/components/home/v2 # Legacy helpers + /situazione PrioritaList
  src/action-engine/     # ActionEngine.open(item) central entry
  src/conversation-engine/ # ConversationEngine.start → bridges to AE UI
  src/theme/          # Quiet Premium: tokens, palettes, ThemeProvider, motion, haptics, shadows
  src/components/ui/  # Design primitives (AppScreen, AppCard, AppButton, …) + legacy ActionBtn
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
- `GET /api/home` → Home V2 aggregate (`primary_focus`, situation, priorities, insights, resume, `ora_ti_consiglia` ≤3, warnings); Goal-aware when `GOAL_ENGINE_ENABLED` (`home-rank-1.2`, item `goal_*` refs + dedupe; no Goals section — `docs/GOAL_AWARE_HOME.md`); Proactive when `PROACTIVE_ENGINE_ENABLED` — `docs/PROACTIVE_ENGINE_ARCHITECTURE.md`; Conversation resume via CE adapter — `docs/CONVERSATION_ENGINE_ARCHITECTURE.md`
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
