# Benefit Engine

Ultimo aggiornamento: 2026-08-06

## Principio

Ogni domanda del Life Strategist deve essere spiegabile con un **beneficio concreto** («ORA può ricordarti le rate del mutuo»), mai «per completare il profilo».

## Catalogo

Codici in `ai_life_strategist/benefit_engine.py`, es.:

- `casa_mutuo_scadenze`, `casa_bollette`, `casa_documenti`  
- `auto_scadenze`, `studio_esami`, `assicurazioni_rinnovi`, …

Ogni benefit dichiara `requires`, `activates_when`, segnali Home/Proactive opzionali.

## Uso

- Gap → `pick_best_benefit_for_gap`  
- Profile domain → `benefits_available` / `benefits_active`  
- Explain API → testo utente da `user_benefit`

Deterministico; Gemini può riformulare ma il codice valida privacy e struttura.
