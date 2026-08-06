# Life Object Verification

## Unit / API (pytest)

```bash
cd backend
python -m pytest life_objects/tests/test_life_object_engine.py -q
```

### Scenari coperti

| Scenario | Atteso |
|----------|--------|
| Rogito → Mutuo → Bolletta | **1** HOME attivo, 3 documenti linkati |
| Libretto + Polizza auto | **1** VEHICLE (targa) |
| University / Job / Family | tipi corretti |
| Merge + link | unione identity_keys + relationship |
| Travel / Study / Goal hooks | TRAVEL / COURSE + `life_object_id` su goal |
| Flag OFF | zero writes |
| Isolamento utenti | user B non vede oggetti di A |
| Gemini assente | fallback deterministico, `ai_used=False` |
| Title-only bolletta | non crea terza Casa active |
| Casa enrichment | narrative + questions + health explainable + identity/state + temporal/insights |
| Auto / Università / Lavoro enrichment | narrative + identity/state + health reasons |
| Home V3 DTO | `enabled=false` quando flag OFF; card senza branding “Life Object” |

## Playwright (shadow API)

```bash
cd frontend
npx playwright test e2e/life-experience-documents.spec.ts -g "SHADOW Life Objects"
```

Assert: dopo upload rogito+mutuo+bolletta via API → `GET /api/life-objects?type=HOME` count=1, `home_ui_enabled=false`, e dopo `POST .../enrich` esistono `narrative.text`, `pending_questions`, `insights`, `health.completeness/reliability/reasons`. Feed Home V3 `enabled=false`.

Evidence: `frontend/e2e-evidence/life-experience-documents/shadow-life-objects-casa.json`

## Manuale smoke

1. `LIFE_OBJECT_ENGINE_ENABLED=1`, `LIFE_OBJECT_HOME_UI_ENABLED=0`, opzionale `LIFE_OBJECT_GEMINI=0`
2. Avvia backend + registra utente
3. `GET /api/life-objects/status` → `mode: shadow`, `home_ui_enabled: false`
4. Consuma rogito → mutuo → bolletta → lista HOME length 1
5. `GET /api/life-objects/{id}/narrative` → testo italiano naturale
6. `GET /api/life-objects/{id}/health` → completeness/reliability/reasons
7. Home UI invariata (nessuna vista oggetti)

## Limiti onesti

- Home V3 **non shippata** (SHADOW / PREDISPOSTO)
- Playwright UI Life Objects: non applicabile (UX non cambiata)
- Gemini live sul reasoner/enrichment: **opzionale** — CI usa fallback italiano deterministico
- Nessun branding “Life Object” in Home
