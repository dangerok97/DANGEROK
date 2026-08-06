# Life Object Reasoning

## Principi

1. **Mai inventare fatti** — solo ciò che è nel documento / artifact / storia oggetto.
2. **Mai matchare solo sul titolo** — chiave = address, catastale, POD/PDR, targa, VIN, lender+property, coords.
3. **Mai creare silenziosamente “Casa 2”** — in conflitto → `propose_merge` o `uncertain`.
4. Output sempre **Pydantic** (`ObjectReasoningDecision`, risultati enrichment).
5. Contesto Gemini **minimale** (no segreti, no dump completi).

## Flusso identity

```
DocumentReasoning (Documents V2 / Life Experience)
        ↓
Life Object Reasoner (Gemini via Provider Manager)
        ↓  (fallback deterministico se Gemini assente/invalido)
ObjectReasoningDecision { action, type, identity_keys, improves, worsens, next_question }
        ↓
LifeObjectService upsert (dedupe + history + identity/state split)
        ↓
Enrichment (narrative / questions / insights / temporal / health)
```

## Azioni reasoner

| action | Significato |
|--------|-------------|
| `create` | Nuovo oggetto con identity keys forti |
| `update` | Stesso oggetto (match key / soft address) |
| `propose_merge` | Conflitto tra candidati — chiedere all’utente |
| `uncertain` | Identity troppo debole — status `uncertain`, non active silenzioso |
| `skip` | Documento non mappa a un Life Object |

## Enrichment AI

| Sezione | Scopo | Fallback |
|---------|-------|----------|
| Narrative | Situazione naturale in italiano (versionata) | Template per tipo (Casa/Auto/…) |
| Questions | Domande che aumentano capacità di aiutare | Gap identity/state tipizzati |
| Insights | Osservazioni da storia (cambio fornitore, trend, rata) | `detect_state_changes` + trend |
| Temporal | Presente vs storia stesso oggetto | Serie bollette + cambi state |
| Health | completeness, reliability, missing_info, opportunities, risks, reasons | Score derivato spiegabile |

## Domande

Il reasoner può proporre `next_question`; l’enrichment **rinfresca** `pending_questions` a ogni nuova fonte. Nessuna UX dedicata in questa fase.

## Gemini

- Via `llm.structured.chat_json` + Provider Manager
- Se `invented_facts=true` → scarta e usa fallback
- Identity keys deterministiche **sempre unite** al risultato AI
- Flag: `LIFE_OBJECT_GEMINI=0` forza fallback (usato in pytest)
- Honest: Gemini è **opzionale**; CI e smoke usano il fallback italiano
