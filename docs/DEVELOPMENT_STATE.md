# ORA — Development State

Last updated: 2026-08-04 (Cursor platform bootstrap)

## Branch

- Working branch: `ora/cursor-platform` (from `origin/conflict_040826_1759`)
- `master` on origin still contains only the empty README — do not assume master has the app

## Operative (imported from Emergent)

- Decision engine, life graph, knowledge, auto-link
- Permissions, connectors framework
- Google Calendar connector code paths
- Documents pipeline + document actions (Iter 23)
- Daily intelligence, explainability, action center
- Behavioral intelligence modules (feature-flagged)
- Email/password auth + JWT
- Expo UI shells for home, memoria, documenti, profilo, calendars

## Incomplete / blocked locally

| Item | Why |
|------|-----|
| Google login | Depends on Emergent OAuth bridge |
| LLM resolve / memory ask | Needs `EMERGENT_LLM_KEY` + `emergentintegrations` |
| `pip install` full requirements | `litellm` wheel hosted on Emergent CDN |
| Apple Sign-In | UI placeholder only |
| Production deploy from Cursor | Not configured |
| Frontend lockfile | No `yarn.lock` / `package-lock.json` in repo |
| `.env` files | Not in git (expected); examples added |

## Bugs / risks

- ~900+ binaries under `backend/data/documents/` may include user uploads — treat as sensitive; avoid spreading.
- Many pytest “live smoke” tests default to Emergent preview URL.
- `frontend/scripts/cmd-guard` may interfere with installs outside Emergent — watch preinstall failures.

## Missing credentials (fill locally, never commit)

Copy examples:

- `backend/.env.example` → `backend/.env`
- `frontend/.env.example` → `frontend/.env`

Required minimum for API boot:

- `MONGO_URL`
- `DB_NAME`
- `JWT_SECRET`
- `EMERGENT_LLM_KEY` (or later a portable LLM key after migration)

For Google Calendar:

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_URI`

For Expo:

- `EXPO_PUBLIC_BACKEND_URL=http://localhost:8000`

## Priorities (suggested)

1. Finish local setup verification (`scripts/setup` → `scripts/dev` → health check)
2. Make requirements installable offline (replace Emergent litellm URL)
3. First-party Google OAuth for login (replace Emergent bridge)
4. Portable LLM provider adapter behind the same service interface
5. Add lockfile for frontend

## Cursor automation

Present:

- `AGENTS.md`
- `.cursor/rules/*`
- `.cursor/agents/*`
- `.cursor/hooks.json` + safety gate
- `docs/*` living docs
- `scripts/*` setup/dev/test/verify/build
