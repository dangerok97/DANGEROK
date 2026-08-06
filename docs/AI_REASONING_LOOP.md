# AI Reasoning Loop

Ogni turno della Life Experience esegue questo loop (mai due domande insieme).

## Passi

1. **Read Knowledge Graph** — nodi Life Graph dell’utente (best-effort)
2. **Read Life Profile** — fatti noti per dominio
3. **Read Conversation** — domande già poste, fase sessione, bridge CE
4. **Read Documents** — tipi documento collegati / stub
5. **Read Goals** — obiettivi shadow
6. **Read Calendar** — eventi recenti (se presenti)
7. **Compute** — cosa so / cosa manca / cosa è utile / beneficio più alto
8. **Build plan** — `StrategistPlan` (Pydantic)
9. **ONE question only** — `next_best_question`
10. **Wait for answer** — il servizio non fa follow-up multipli nello stesso turno

## Re-plan

A ogni risposta, upload, skip o rifiuto il contesto cambia → il loop riparte da zero.
Chiavi `asked` / `refused` / `postponed` non vengono riproposte.

## Implementazione

- Modulo: `backend/ai_life_strategist/reasoning_loop.py`
- Facade: `AILifeStrategistService.build_context` → `next_question` → `plan_turn`
- Orchestrazione sessione: `life_setup.service.LifeSetupService._plan_turn`

## Output

Sempre strutturato (`StrategistPlan`). La spiegazione utente (`user_explanation` / `explain_for_user`) è italiano semplice — **mai** CoT interno.
