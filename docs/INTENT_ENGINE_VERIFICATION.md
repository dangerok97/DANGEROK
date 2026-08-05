# Intent Classification Engine — Verification

Last updated: 2026-08-05  
Branch: `feature/intent-classification-engine`

## Automated tests

| Suite | Result | Count |
|-------|--------|-------|
| `tests/test_intent_engine.py` (corpus + clarify + AE regression) | **PASS** | 124 corpus + unit/integration |
| `tests/test_action_engine.py` (updated for Intent routing) | **PASS** | included in 147 total |
| Combined `pytest tests/test_intent_engine.py tests/test_action_engine.py` | **147 passed** | 2026-08-05 |

Corpus: `backend/tests/fixtures/intent_corpus_it.json` (**124** Italian phrases).

Psychology phrase asserted explicitly:
- text → `study` / `exam_preparation` / subject `Psicologia`
- AE open with `item_type=event` still → flow `study`, first turn `exam_date` (no biglietto)
- Study Action Flow (2026-08-05) consumes this Intent unchanged for routing; subject skip + full plan after exam_date — see `STUDY_ACTION_FLOW_VERIFICATION.md`

## Playwright (Expo web)

| Spec | Result |
|------|--------|
| `frontend/e2e/intent-psychology.spec.ts` | **1 passed** (~10s) |

Flow verified:
1. Create decision `"devo studiare l'esame di psicologia"` with wrong `category: event`
2. Open Inizia / Action Engine
3. **NOT** “Hai già il biglietto?”
4. Study first question (exam date / material)

Evidence: `frontend/test-results/intent-psychology/`

## Classified examples (deterministic, no Gemini)

| Phrase | Intent | Subtype |
|--------|--------|---------|
| devo studiare l'esame di psicologia | study | exam_preparation |
| biglietto concerto Coldplay | event | concert |
| vacanza in Sardegna | travel | vacation |
| visita dal dentista | medical | appointment |
| bolletta luce da pagare | payment | bill |
| fattura da saldare | payment | invoice |

## Limits

- Italian-first keyword KB; other languages weaker until patterns added.
- LLM enricher optional (`INTENT_LLM_ENRICH`); not required for pass criteria.
- Native iOS/Android Intent→AE UI not re-verified in this pass (web Playwright only).
- Very short nonsense text → clarify (by design).
