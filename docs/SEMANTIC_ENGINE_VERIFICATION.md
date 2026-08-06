# Semantic Engine — Verification

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

## Automated

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests/test_semantic_engine.py -q
```

Corpus ≥200 Italian phrases in `tests/fixtures/semantic_corpus_it.json`.

## Playwright

```bash
cd frontend
npx playwright test e2e/semantic-extraction-gap.spec.ts
```

Evidence under `frontend/e2e-evidence/semantic-extraction-gap/`.

## Limits

- Gemini is optional; deterministic path is the source of truth when the key is absent.
- Optional Gemini rephrase of questions is OFF by default (`SEMANTIC_GEMINI_REPHRASE=0`).
