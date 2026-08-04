# ORA — Development State

Last updated: 2026-08-04 (unified Google/Apple auth implementation)

See also: `docs/SOCIAL_AUTH_ARCHITECTURE.md`, `docs/SOCIAL_AUTH_SETUP.md`, `docs/SOCIAL_AUTH_VERIFICATION.md`.

## Branch

- Feature (local, no push): `feature/social-auth` (from documents commit on `ora/cursor-platform` lineage)
- Prior: `feature/documents-ui-alignment` → documents workflow verified

## Environment (verified on this machine)

| Tool | Status |
|------|--------|
| Windows | OK |
| Python 3.12 + venv | OK |
| Node / npm | OK |
| MongoDB service | OK |
| Backend `:8000` | OK |
| Expo web `:8081` | OK (when Metro running) |

## Auth status

| Method | Code | Mock/unit tests | Real provider E2E |
|--------|------|-----------------|-------------------|
| Email/password | operativo | pass | pass (locale) |
| Google ID token | implementato | pass (claims mock) | **bloccato da credenziali** |
| Apple ID token | implementato | pass (claims mock) | **bloccato da credenziali** |
| iOS / Android native | codice + plugins | — | **non verificato su device** |

## Tests (latest)

- `pytest tests/test_social_auth_unit.py tests/test_local_smoke.py` — 19 passed
- `tsc --noEmit` — OK
- `GET /api/auth/providers` — OK (`google/apple.configured=false` senza env)

## Credenziali ancora necessarie

Vedi `docs/SOCIAL_AUTH_SETUP.md`:

- `GOOGLE_WEB_CLIENT_ID` (+ iOS/Android) e mirror `EXPO_PUBLIC_GOOGLE_*`
- Apple Team/Key/Services ID + `.p8` path; `EXPO_PUBLIC_APPLE_SERVICE_ID` per web

## Priorities next

1. Fornire credenziali Google Web → verifica reale browser
2. Fornire Apple Services ID / key → verifica web o iOS build
3. BACKLOG-003 LLM UX messages
4. Non iniziare Attività/Promemoria finché social auth non è verificata dove possibile
