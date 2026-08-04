# ORA — Development State

Last updated: 2026-08-04 (functional audit + roadmap)

See also: `docs/FUNCTIONAL_AUDIT.md`, `docs/ROADMAP.md`, `docs/BACKLOG.md`.

## Branch

- Working branch: `ora/cursor-platform`
- Commits: platform scaffold + local Emergent isolation

## Environment (verified on this machine)

| Tool | Status |
|------|--------|
| Windows 10/11 | OK |
| Python 3.12.10 | Installed |
| Node v24 / npm 11 | OK |
| MongoDB Server 8.x service | Running (`MongoDB`) |
| Docker | Not installed (compose file provided for later) |
| Yarn | Not required (npm used) |

## Operative locally (verified)

- Backend uvicorn on `127.0.0.1:8000`
- MongoDB ping + health `database.ok=true`
- `GET /api/` → `{app:ORA,status:ok}`
- `GET /api/health` → app/db/llm/integrations status (no secrets)
- Email register/login against live API
- Google session returns 503 when Emergent bridge off
- Expo Metro web on `127.0.0.1:8081` (HTML 200, bundle completed)
- `tests/test_local_smoke.py` — 5 passed (`-n 0`)
- Python `compileall` OK
- Frontend `tsc --noEmit` OK after `tokens.color.error` fix

## Incomplete / needs credentials

| Feature | Status |
|---------|--------|
| LLM resolve / memory ask | Needs `LLM_PROVIDER=openai` + `OPENAI_API_KEY` (or Emergent provider) |
| Google login | Needs first-party OAuth or `EMERGENT_GOOGLE_AUTH=1` + Emergent bridge |
| Google Calendar sync | Needs `GOOGLE_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI` |
| Apple Sign-In | UI placeholder |
| Native iOS/Android device run | Not verified in this session (web only) |

## Emergent isolation summary

- Boot no longer requires `EMERGENT_LLM_KEY`
- LLM behind `backend/llm/provider.py`
- Local deps: `backend/requirements-local.txt` (no Emergent CDN wheel)
- Google login gated; FE shows explicit “non configurato”
- cmd-guard: `node` preinstall + `ORA_SKIP_CMD_GUARD=1`

## URLs used

- Backend: `http://127.0.0.1:8000`
- Frontend web: `http://127.0.0.1:8081`
- LAN hint for phones: `192.168.0.123` (machine-specific; see `frontend/.env` `EXPO_PUBLIC_LAN_IP`)

## Priorities

1. Optional: wire OpenAI key for AI features
2. First-party Google OAuth for login
3. Generate frontend lockfile (`package-lock.json` present after npm install — keep committed if desired)
4. Verify mobile emulator/device separately
