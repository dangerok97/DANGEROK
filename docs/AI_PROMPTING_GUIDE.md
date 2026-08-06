# AI Prompting Guide — Life Experience / Strategist

## Regola d’oro

Gemini riceve un **JSON di contesto strutturato**, non solo il messaggio utente.

Campi obbligatori nel payload:

- `known` / `missing` / `confidence`
- `domains`
- `goals` / `calendar_summary` / `documents_summary` / `conversation_summary`
- `asked_questions` / `asked_keys` / `refused_keys` / `postponed_keys`
- `benefits_available` / `benefits_active`
- `useful_next` / `highest_benefit_code`

## Domanda unica verso Gemini

```
Qual è la prossima domanda che produrrà il maggior beneficio concreto per l'utente?
```

Mai: «continua liberamente», «fai da chatbot», «completa il profilo».

## System prompt (sintesi)

- Non sei un chatbot generico
- Una sola domanda per turno
- Preferisci documenti densamente informativi
- Mai password / PIN / OTP / IBAN
- Stringhe utente in italiano
- Solo JSON secondo schema StrategistPlan

## Provider

`ProviderManager().chat(..., json_mode=True, user_preference="gemini")`

Flag: `AI_LIFE_STRATEGIST_GEMINI=1` (default). Se assente/fallisce → fallback deterministico italiano.

## Codice

`backend/ai_life_strategist/reasoner.py`  
`backend/ai_life_strategist/reasoning_loop.py` → `to_gemini_context_json`
