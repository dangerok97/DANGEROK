# ORA — Architecture

## Stack

| Layer | Choice |
|-------|--------|
| Mobile/Web client | Expo 54, React Native, TypeScript, expo-router |
| API | FastAPI + Uvicorn |
| DB | MongoDB via Motor |
| Auth | JWT ORA (HS256) + bcrypt; Google/Apple ID-token verify (`backend/social_auth/`); Emergent bridge legacy optional |
| LLM | Provider adapter `backend/llm/` — `none` / `openai` / `emergent` (not required at boot) |
| Design tokens | `design_guidelines.json`, `frontend/src/theme/tokens.ts` |
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
  daily_intelligence/    # daily summary
  behavioral_intelligence/
  behavior_aware_decisions/
  explainability/
  action_center/
  social_auth/           # Google/Apple verify, identities, linking
  security/              # token vault
  tests/                 # pytest
frontend/
  app/                   # expo-router screens
  src/api/client.ts      # HTTP client
  src/auth/              # Google/Apple client helpers
  src/components/        # UI
  src/theme/tokens.ts
docs/                    # living engineering docs (+ SOCIAL_AUTH_*)
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
- `documents`, `admin`, `memory`

Health:

- `GET /api/` → `{ "app": "ORA", "status": "ok" }`
- `GET /api/health` → app + database + llm configured flag + integration flags (no secrets)

## Local topology

```
MongoDB :27017  →  FastAPI :8000  →  Expo web :8081 (EXPO_PUBLIC_BACKEND_URL)
```

## Data store

MongoDB collections created/indexed at startup (users, tasks, decisions, life_nodes/edges, node_knowledge, link_proposals, context_snapshots, memories, permission_*, ingestion_events, connector_instances, secret_vault, google_oauth_sessions, documents-related, behavioral collections, …).

Document binaries: local storage under `backend/data/documents/` (S3 backend stubbed for future).

## External integrations

| Integration | Path | Local notes |
|-------------|------|-------------|
| Emergent Google login | `auth.emergentagent.com` + demobackend session-data | Not portable |
| Emergent LLM | `emergentintegrations` + `EMERGENT_LLM_KEY` | Key + package required |
| Google Calendar OAuth | Google Cloud OAuth env vars | Needs local redirect URI |
| Apple Calendar | expo-calendar / mock flag | Device or mock |
| litellm wheel | Emergent asset URL in requirements | May fail outside Emergent |

## Hosting / deploy (current)

- Historical preview: `https://ora-decision-engine.preview.emergentagent.com`
- iOS package id: `com.emergent.oradecisionengine.b7escs`
- Cursor-local target: Mongo + uvicorn `:8000` + Expo (`EXPO_PUBLIC_BACKEND_URL`)

## Local run (summary)

See `README.md` and `scripts/dev`. Details and gaps live in `docs/DEVELOPMENT_STATE.md`.
