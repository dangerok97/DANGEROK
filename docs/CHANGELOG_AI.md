# ORA — AI Changelog

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
