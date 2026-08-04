# ORA

Life Operating System — Expo client + FastAPI/MongoDB backend.

Primary development environment: **Cursor** (autonomous agent workflow).  
Historical origin: Emergent (code lineage from `conflict_040826_1759`).

## Prerequisites (Windows verified)

- Python 3.12+
- Node.js 20+ (npm)
- MongoDB Server running on `127.0.0.1:27017`
- Git

Optional: Docker (`docker compose up -d` uses `docker-compose.yml` for Mongo).

## Quick start

```powershell
# From repo root
.\scripts\setup.ps1

# Confirm secrets (auto-created if missing):
#   backend\.env   → MONGO_URL, DB_NAME, JWT_SECRET (LLM optional)
#   frontend\.env  → EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:8000

# Terminal 1 — API
cd backend
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000

# Terminal 2 — Expo web
cd frontend
$env:ORA_SKIP_CMD_GUARD = "1"
npx expo start --web --port 8081
```

Or: `.\scripts\dev.ps1` (starts both).

### URLs (local verification)

| Surface | URL |
|---------|-----|
| API root | http://127.0.0.1:8000/api/ |
| Health | http://127.0.0.1:8000/api/health |
| Expo web | http://127.0.0.1:8081 |
| LAN IP (phone) | set `EXPO_PUBLIC_BACKEND_URL=http://<LAN_IP>:8000` |

## Verify

```powershell
.\scripts\test.ps1
# or focused smoke:
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_local_smoke.py -n 0 -q
```

## Environment

### Backend required

- `MONGO_URL`
- `DB_NAME`
- `JWT_SECRET`

### Backend optional

| Variable | Purpose |
|----------|---------|
| `LLM_PROVIDER` | `none` (default) / `openai` / `emergent` |
| `OPENAI_API_KEY` | OpenAI provider |
| `OPENAI_MODEL` | default `gpt-4o-mini` |
| `EMERGENT_LLM_KEY` | only if `LLM_PROVIDER=emergent` |
| `EMERGENT_GOOGLE_AUTH` | `1` to enable legacy Emergent Google login bridge |
| `GOOGLE_OAUTH_*` | Google Calendar connector |

Without LLM keys the API **boots**; AI routes (`resolve`, `memory/ask`) return **503** with a clear message.

### Frontend

- `EXPO_PUBLIC_BACKEND_URL` — use `127.0.0.1` for web/emulator; LAN IP for a physical phone
- `EXPO_PUBLIC_APPLE_CALENDAR_MOCK=1` — fake Apple calendars in web/dev

## Emergent isolation

| Dependency | Treatment |
|------------|-----------|
| `emergentintegrations` / Emergent litellm wheel | Removed from `backend/requirements-local.txt` |
| `EMERGENT_LLM_KEY` at boot | No longer required; LLM via `backend/llm/` adapter |
| Google login via `auth.emergentagent.com` | Disabled unless `EMERGENT_GOOGLE_AUTH=1`; UI shows honest message |
| `.emergent/` cron | Ignored for local Cursor workflows |
| Preview URL in old tests | Local smoke tests use TestClient / `127.0.0.1` |

Upstream `backend/requirements.txt` is kept for reference; **local installs use `requirements-local.txt`**.

## Agent automation

See `AGENTS.md`, `.cursor/rules/`, `.cursor/agents/`, and living docs under `docs/`.
