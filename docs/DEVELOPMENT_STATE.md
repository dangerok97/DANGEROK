# ORA — Development State

Last updated: 2026-08-04 (documents UI alignment + verified workflow)

See also: `docs/FUNCTIONAL_AUDIT.md`, `docs/ROADMAP.md`, `docs/BACKLOG.md`, `docs/DOCUMENTS_VERIFICATION.md`.

## Branch

- Base: `ora/cursor-platform`
- Feature (local, no push): `feature/documents-ui-alignment`
- Prior commits on platform: scaffold + Emergent isolation + functional audit docs

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
- Expo Metro web on `127.0.0.1:8081`
- Documents: upload / list / detail / user isolation / empty list / invalid MIME / 404 (pytest + HTTP)
- Documents UI labels: Profilo + Aggiungi allineati; empty state web verificato
- `tests/test_local_smoke.py` + `tests/test_documents_local.py` — 11 passed (`-n 0`)
- Frontend `tsc --noEmit` OK
- `expo lint` — 0 errors (warnings preesistenti)

## Incomplete / needs credentials

| Feature | Status |
|---------|--------|
| LLM resolve / memory ask | Needs `LLM_PROVIDER=openai` + `OPENAI_API_KEY` (or Emergent provider) |
| Google login | Needs first-party OAuth or `EMERGENT_GOOGLE_AUTH=1` + Emergent bridge |
| Google Calendar sync | Needs `GOOGLE_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI` |
| Apple Sign-In | UI placeholder |
| Native iOS/Android device run | Not verified in this session (web only) |

## Documents storage (local)

- Path: `backend/data/documents/<user_id>/…` (gitignored)
- Max size: 25 MB default
- No cloud storage in this phase

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

1. BACKLOG-003 — messaggi UI quando LLM assente
2. BACKLOG-004 — E2E Decision complete/postpone in UI
3. Optional: OpenAI key / Google OAuth locale
4. Verify mobile emulator/device separately
