# AI Life Strategist

Ultimo aggiornamento: 2026-08-06

## Ruolo

L’AI **dirige** la conversazione Life Setup: *cosa* chiedere, *quando*, *perché*; preferisce upload documenti quando più informativi.  
Il **codice** gestisce persistenza, validazione, security, DB, sync.

## Output (sempre Pydantic strutturato)

| Campo | Ruolo |
|-------|--------|
| `next_best_question` | Prossima domanda |
| `question_reason` | Perché ora |
| `expected_benefit` | Beneficio concreto per l’utente |
| `information_gain` | 0–1 |
| `recommended_document` | Doc preferito (opz.) |
| `alternative_question` | Alternativa |
| `confidence` | 0–1 |
| `domain` | Dominio vita |
| `priority` | 1–100 |

Mai dump di decisioni in free text.

## Pipeline

1. Contesto proporzionato (facts, gap, asked, docs)  
2. Cache reasoning / planning  
3. Gemini via **Provider Manager** (`json_mode`) se configurato  
4. Altrimenti **deterministic benefit-driven planner** (mai random field-filling)  
5. Policy privacy + anti-duplicate  
6. Turn conversazionale (FE)

## Policy

**Può:** reason, suggest, propose, link, extract, explain, choose next Q, recommend document, propose shadow goal / calendar draft.  
**Non può:** delete data, overwrite confirmed, azioni irreversibili calendario senza consenso, chiedere segreti.

## API interna

`POST /api/strategist/next-question` (auth)  
Flag: `AI_LIFE_STRATEGIST_ENABLED`, `AI_LIFE_STRATEGIST_GEMINI`

## Package

`backend/ai_life_strategist/` — models, service, reasoner, benefit_engine, question_planner, knowledge_gap, document_strategy, conversation_planner, confidence_manager, policy, cache, router, tests.
