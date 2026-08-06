# Life Object Reasoning

## Principi

1. **Mai inventare fatti** — solo ciò che è nel documento / artifact.
2. **Mai matchare solo sul titolo** — chiave = address, catastale, POD/PDR, targa, VIN, lender+property, coords.
3. **Mai creare silenziosamente “Casa 2”** — in conflitto → `propose_merge` o `uncertain`.
4. Output sempre **Pydantic** (`ObjectReasoningDecision`).

## Flusso

```
DocumentReasoning (Documents V2 / Life Experience)
        ↓
Life Object Reasoner (Gemini via Provider Manager)
        ↓  (fallback deterministico se Gemini assente/invalido)
ObjectReasoningDecision { action, type, identity_keys, improves, worsens, next_question }
        ↓
LifeObjectService upsert (dedupe + history)
```

## Azioni

| action | Significato |
|--------|-------------|
| `create` | Nuovo oggetto con identity keys forti |
| `update` | Stesso oggetto (match key / soft address) |
| `propose_merge` | Conflitto tra candidati — chiedere all’utente |
| `uncertain` | Identity troppo debole — status `uncertain`, non active silenzioso |
| `skip` | Documento non mappa a un Life Object |

## Domande

Il reasoner può proporre `next_question` (es. “Qual è la targa?”) salvata in `pending_questions` — senza UX dedicata in questa fase.

## Gemini

- Via `llm.structured.chat_json` + Provider Manager
- Se `invented_facts=true` → scarta e usa fallback
- Identity keys deterministiche **sempre unite** al risultato AI (non si perdono POD/targa)
- Flag: `LIFE_OBJECT_GEMINI=0` forza fallback
