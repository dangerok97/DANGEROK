# Life Object Reasoning

## Principi

1. **Mai inventare fatti** — solo documento / artifact / storia.
2. **Mai matchare solo sul titolo**.
3. **Mai creare silenziosamente “Casa 2”**.
4. **Gemini = consultant** — suggerisce; non decide titolo/tipo/merge finali.
5. **Backend = autorità** — Semantic Validator prima di ogni persist.
6. Output sempre **Pydantic**; contesto Gemini minimale.

## Flusso

```
DocumentReasoning
        ↓
Life Object Reasoner (Gemini consultant / fallback)
        ↓  validate_decision_consultant (type/title/properties)
ObjectReasoningDecision
        ↓
Dedupe + link_state (CONFIRMED|PROBABLE|UNCERTAIN|REAL_CONFLICT)
        ↓
Assimilation (mutuo/bolletta → HOME.state) se quiet link
        ↓
Semantic Validator (type, canonical title, registry map)
        ↓
Knowledge Model ingest (Fact se path verificato, else Hypothesis; memory + decisions)
        ↓
Persist + Enrichment (narrative / gaps / insights / temporal / health 2.0)
```

## Separazione Knowledge (prompt Gemini)

Sempre sezioni distinte: **Facts / Hypotheses / Questions / Recommendations / Decisions**.  
Mai auto-promuovere Hypothesis → Fact. Fact storici immutabili (supersede only).

## Titoli canonici (deterministici)

| Tipo | Ordine |
|------|--------|
| HOME | address → via+city → Casa → Casa #N |
| VEHICLE | brand → brand+model → plate → Auto |
| JOB | company → profession → Lavoro |
| UNIVERSITY | university → course → Università |
| TRAVEL | destination → Viaggio |

**Mai** testo AI come titolo finale. **Mai** HOME con titolo «Lavoro».

## Link states

| Stato | User-facing? | Assimilazione |
|-------|--------------|---------------|
| LINK_CONFIRMED | no | sì |
| LINK_PROBABLE | no (quiet) | sì |
| LINK_UNCERTAIN | no | limitata |
| REAL_CONFLICT | **sì** | no auto |

## Knowledge gaps

Domande su **concetti** (registry). Se catastale presente sotto qualsiasi alias → non chiedere.  
Se mutuo assimilato → mai «Hai un mutuo?».

## Narrative / Insights

- **Narrative:** consulente personale — cos’è, cosa sa ORA, cosa manca, come aiuta, rischi, prossimo documento. No dump campi.
- **Insights:** osservazioni («cambiato fornitore due volte»), non descrizioni («hai una casa»).

## Health 2.0

Dimensioni: `identity_completeness`, `state_completeness`, `reliability`, `source_consistency`, `temporal_confidence`, `pending_conflicts`, `pending_links`, `ai_confidence` + score spiegabile.  
Mai «100% healthy» con mutuo non assimilato / merge aperti / domande duplicate.

## Gemini

- Opzionale (`LIFE_OBJECT_GEMINI=0` in pytest)
- `invented_facts=true` → scarta
- Identity keys deterministiche sempre unite al risultato AI
