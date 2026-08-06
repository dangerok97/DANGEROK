# Benefit Engine

Ultimo aggiornamento: 2026-08-06 (Life Experience)

## Principio

Ogni domanda del Life Strategist deve essere spiegabile con un **beneficio concreto** («ORA può ricordarti le rate del mutuo»), mai «per completare il profilo».

## Catalogo

Codici in `ai_life_strategist/benefit_engine.py`, es.:

- `casa_mutuo_scadenze`, `casa_bollette`, `casa_documenti`  
- `auto_scadenze`, `studio_esami`, `assicurazioni_rinnovi`, …

Ogni benefit dichiara `requires`, `activates_when`, `home_signal` / `proactive_signal` (italiano), e `chain`.

### Home / Proactive (italiano)

Esempi `home_signal`:

- «Adesso posso seguire il tuo mutuo.»
- «Adesso posso tenere d’occhio le bollette di casa.»
- «Adesso posso seguire le scadenze della tua auto.»

Dopo il primo setup, Home e Proactive usano questi segnali — **mai** una sezione Life Setup.

### Catene

- Casa → mutuo → scadenze → calendar → goal → proactive  
- Auto → libretto → assicurazione → revisione → bollo → reminder  
- Università → piano studi → esami → docs → study plan  

## Uso

- Gap → `pick_best_benefit_for_gap`  
- Home → `home_benefit_cards(known_keys)`  
- Proactive → `proactive_benefit_suggestions(known_keys)`  
- Explain API → testo utente da `user_benefit`

Deterministico; Gemini può riformulare ma il codice valida privacy e struttura.
