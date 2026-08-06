# Question Planning

Ultimo aggiornamento: 2026-08-06

## Obiettivo

Scegliere la **next best question** (o documento) con massimo information gain e beneficio, senza sequenze rigide da wizard.

## Componenti

1. **Knowledge Gap** (`knowledge_gap.py`) — gap dichiarativi per dominio + `when` conditions  
2. **Document strategy** — preferisci rogito/libretto/polizza quando densità > Q&A  
3. **Question planner** — fallback deterministico benefit-driven  
4. **Reasoner** — Gemini structured JSON via Provider Manager  
5. **Dedup** — `avoid_duplicate` su testo già chiesto  
6. **Cache** — riduce chiamate AI (`AI_LIFE_STRATEGIST_CACHE_*`)

## Esempio Casa

User: «Ho comprato casa.» → known `casa.purchased`/`casa.owned` → gap `doc.rogito` (prefer document) → dopo upload → gap `casa.mutuo` («il mutuo è sotto controllo?»).

## Anti-pattern (FAIL)

- Progress bar obbligatoria / step 3 di 12  
- Campo vuoto random  
- «Completa il profilo»  
- Chiedere PIN/password/OTP
