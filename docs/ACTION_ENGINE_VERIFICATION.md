# Action Engine — Verification

Last updated: 2026-08-05 (collaborative feel smoke)

## Automated unit / API

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_action_engine.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_home_v2.py tests/test_documents_v2.py -q
```

```powershell
cd frontend
npx tsc --noEmit
```

## Playwright collaborative-feel smoke (PASS 2026-08-05)

**Branch tip at verify start:** `cca0acb`  
**Spec:** `frontend/e2e/action-engine.spec.ts`  
**Command:**

```powershell
# Backend must be THIS branch (has /api/action-engine/*). Restart uvicorn if 404.
cd backend
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload

# Expo web (restart after adding /action/* routes)
cd frontend
npx expo start --web --port 8081

cd frontend
$env:E2E_BASE_URL="http://127.0.0.1:8081"
$env:E2E_API_URL="http://127.0.0.1:8000"
$env:EXPO_PUBLIC_BACKEND_URL="http://127.0.0.1:8000"
npx playwright test e2e/action-engine.spec.ts --reporter=list
```

### Result: **PASS** (1/1, ~19–24s)

| Check | Result |
|-------|--------|
| Login + seeded study priority on Home | PASS |
| Primary action **Inizia** (`kind=guide`) present | PASS |
| Tap opens guided UI — **not blank** | PASS |
| First question + chips visible (`action-question`, `action-chips`) | PASS |
| Answer ≥3 chip steps in UI | PASS (3) |
| Flow complete → `next_focus_hint` | PASS (`Sessione 1 tra 1g · esame tra 3g`) |
| Home refresh evolved (sessions / ripasso / hint) | PASS |

### Evidence (local, gitignored `test-results/`)

Path: `frontend/test-results/action-engine-smoke/`

| File | Content |
|------|---------|
| `01-home-priority.png` | Home with «Esame Analisi E2E» + Inizia |
| `02-first-question.png` | One question + chips |
| `03-second-question.png` | Next question after chip |
| `04-after-chips.png` | After 3 UI chip answers |
| `05-home-after-refresh.png` | Home after complete/refresh |
| `smoke-log.json` | Structured evidence (titles, session id, hint) |

Sample from `smoke-log.json`:

- `guideLabel`: Inizia  
- `firstQuestion`: exam date question for «Esame Analisi E2E»  
- `uiStepsAnswered`: 3  
- `homeTitlesAfter`: Sessione 1/2, Studio, Ripasso, project hint  

### Incident during verify

First Playwright run failed with `POST /api/action-engine/open` → **404**. Cause: stale uvicorn still serving pre–Action Engine code (openapi had no `/action-engine` routes; Home actions lacked `Inizia`). Restarted backend from `feature/ora-action-engine` → probe + Playwright **PASS**.

## Manual checklist (still useful)

1. Backend + Expo from this branch.  
2. Home priority → **Inizia** / **Organizza** / **Apri** / card.  
3. One question + chips — not empty.  
4. Complete → Home shows session/hint.  
5. Medical: disclaimer, no advice.

## Platforms / gaps still open

- iOS / Android native builds: **not verified**  
- Google Calendar live sync of AE events: **not verified** (Life Graph events yes)  
- Weather / live traffic: blocked placeholders  
- Playwright finishes long study turns via API after 3 UI chips (UI path for full 5–6 turns exercised partially; collaborative open + multi-step chips + Home evolution verified)
