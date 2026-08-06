# Life Graph — Life Setup integration

Ultimo aggiornamento: 2026-08-06

## Ruolo esistente

Il Life Graph (`life_nodes` / `life_edges`) resta la rappresentazione strutturata della vita. Non ranking, non decisioni.

## Integrazione Life Setup

Quando la conversazione tocca un dominio (es. casa dopo «Ho comprato casa.» + rogito):

1. Crea/aggiorna un nodo tipizzato (`home`, `car`, `university`, …) con `origin=life_setup`  
2. Attributi includono `life_setup_domain` + fatti rilevanti  
3. Collega Goal ombra e documenti quando disponibili  

Tipi nodo già in `life_graph/types.py` (HOME, CAR, …). Domini Life Setup mappati in `life_setup/sync.py`.

## Confini

- Strategist non scrive direttamente sul grafo: passa da `life_setup.sync`  
- Nessuna eliminazione nodi da parte dell’AI  
- Email/Banking/Weather non creano nodi fantasma
