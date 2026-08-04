# ORA

Life Operating System — Expo client + FastAPI/MongoDB backend.

Primary development environment: **Cursor** (autonomous agent workflow).  
Historical origin: Emergent (`conflict_040826_1759` lineage).

## Quick start (Windows)

```powershell
# 1) Prerequisites: Git, Python 3.11+, Node 20+, MongoDB running
.\scripts\setup.ps1

# 2) Edit secrets
#    backend\.env   → MONGO_URL, DB_NAME, JWT_SECRET, EMERGENT_LLM_KEY
#    frontend\.env  → EXPO_PUBLIC_BACKEND_URL=http://localhost:8000

# 3) Run
.\scripts\dev.ps1
```

Unix/macOS: `./scripts/setup.sh` then `./scripts/dev.sh`.

## Verify

```powershell
.\scripts\test.ps1
.\scripts\build.ps1
.\scripts\verify.ps1
```

## Agent / automation

| Path | Purpose |
|------|---------|
| `AGENTS.md` | Permanent agent rules |
| `.cursor/rules/` | Architecture, FE/BE/DB, security, workflow |
| `.cursor/agents/` | ARCHITECT, FRONTEND, BACKEND, DATABASE, TESTER, REVIEWER, DEVOPS |
| `.cursor/hooks.json` | Safety gate on destructive shell commands |
| `docs/PRODUCT.md` | Product |
| `docs/ARCHITECTURE.md` | Architecture |
| `docs/DEVELOPMENT_STATE.md` | What works / what’s blocked |
| `docs/CHANGELOG_AI.md` | AI change log |

## Ask Cursor in natural language

Examples: “aggiungi una sezione calendario”, “crea il login con Google”, “correggi la dashboard”.  
The agent must implement, run checks, and report with the 10-point summary in `AGENTS.md`.

## Known Emergent gaps

See `docs/DEVELOPMENT_STATE.md`. Google login and LLM currently depend on Emergent services/packages; local `.env.example` documents required keys.
