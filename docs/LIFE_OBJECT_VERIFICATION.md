# Life Object Verification

## Unit / API (pytest)

```bash
cd backend
python -m pytest life_objects/tests/ -q
```

### Scenari coperti

| Scenario | Atteso |
|----------|--------|
| Rogito → Mutuo → Bolletta | **1** HOME, titolo Casa (mai Lavoro), mutuo+bolletta assimilati |
| Registry / validator / titles / link states / health 2.0 | unit green |
| Real-life growth (d1→d400) | **sempre 1 HOME** che evolve |
| No domanda catastale se presente; no «Hai un mutuo?» se assimilato | gaps OK |
| Solo REAL_CONFLICT in merge_proposals user-facing | quiet LINK_PROBABLE |
| Provenance tipizzata | `document_sources` + `total_sources` |
| Home V3 DTO | campi completi; `enabled=false` |
| Flag OFF / isolamento / Gemini assente | invariati |

## FAIL criteria (ruthless)

Se dopo rogito+mutuo+bolletta il titolo è ancora «Lavoro», o i merge si accumulano senza assimilare → **FAIL**.

## Playwright (shadow API)

```bash
cd frontend
npx playwright test e2e/life-experience-documents.spec.ts -g "SHADOW Life Objects"
```

## Manuale smoke

1. Flags: engine=1, home_ui=0, gemini=0  
2. Consuma rogito → mutuo → bolletta → 1 HOME, titolo Casa*, state con lender + supplier  
3. `GET .../health` → dimensioni Health 2.0 + reasons  
4. Home UX invariata  

## Limiti onesti

- Home V3 **non shippata**
- Gemini live **opzionale**
- Conversazioni/calendar come fonti provenance: struttura pronta, hook conversazione non esteso in questo batch
