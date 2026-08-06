# Semantic Engine — Verification

Last run: 2026-08-06 (branch `feature/semantic-extraction-gap-analyzer`)

## Tip history

| Commit | Message |
|--------|---------|
| `d4f6d64` | `feat: add semantic extraction and gap analyzer` (initial package) |
| *(follow-up tip)* | `feat: add semantic extraction and dynamic gap analysis` (exact required message + Playwright evidence) |

Base ancestor: `90b3fb1` (Home goal presentation dedupe).

## Bug fix proof

Input: `Fra due settimane parto.`

| Check | Expected | Status |
|-------|----------|--------|
| Domain | travel | ✓ |
| Known | departure_date (+14d Europe/Rome) | ✓ |
| Missing | destination, return_date | ✓ |
| First question | Dove andrai? | ✓ |
| Forbidden | «Quando parti e quando torni?» | ✓ never |
| After «Vibo Marina» | return only | ✓ |

Also verified:

- `Dal 9 al 24 agosto vado a Vibo Marina in auto.` → lodging first
- `Il 18 settembre ho l'esame di psicologia.` → materials (not subject/date)
- `Domani ho il dentista alle 16.` → calendar ask
- `Devo pagare la bolletta Enel entro venerdì, sono 87 euro.` → payment fields known

## Automated (pytest)

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests/test_semantic_engine.py -q
```

Result: **17 passed**. Corpus ≥200 Italian phrases in `tests/fixtures/semantic_corpus_it.json`.

## Playwright (real API + Expo)

Stack:

- API: `http://127.0.0.1:8001` with `SEMANTIC_ENGINE_ENABLED=1`, `CONVERSATION_ENGINE_ENABLED=1`, `GOAL_ENGINE_ENABLED=1`, `PROACTIVE_ENGINE_ENABLED=1`
- Expo web: `http://127.0.0.1:8081` with `EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:8001`

```bash
cd frontend
$env:EXPO_PUBLIC_BACKEND_URL="http://127.0.0.1:8001"
$env:E2E_API_URL="http://127.0.0.1:8001"
$env:E2E_BASE_URL="http://127.0.0.1:8081"
npx playwright test e2e/semantic-extraction-gap.spec.ts --reporter=list
```

Result: **2 passed** (46.3s)

| Spec | Result |
|------|--------|
| Fra due settimane parto → Dove andrai? (never combo dates) | PASS |
| Vibo full extraction → lodging first | PASS |

API smoke before UI: `FIRST_Q=Dove andrai?`, `FLOW=travel`, `TURN_ID=destination`, `BUG_ABSENT_OK`.

Evidence: `frontend/e2e-evidence/semantic-extraction-gap/` (JSON + screenshots). Forbidden phrase absent from first questions and post-Vibo return step.

## Limits

- Gemini is optional; deterministic path is the source of truth when the key is absent.
- Optional Gemini rephrase of questions is OFF by default (`SEMANTIC_GEMINI_REPHRASE=0`).
- Host port 8000 may still run older code without `/api/semantic` — E2E uses tip API on **8001**.
