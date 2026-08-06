# Home V2 — Product

Last updated: 2026-08-06

## Question Home answers

**What is most useful to know or do now?**

Goals are **not** a Home block. They may enrich Adesso / Priorità / Perché / Osserva / Continua as context (see `docs/GOAL_AWARE_HOME.md`). **No Goal tab or Goals list.**

## Blocks (max 5 primary content regions + supporting)

1. **Adesso** — one primary focus from real multi-source ranking; type-specific layout (bill / concert / visit / study…); empty fields hidden. Same Goal → one coherent card (not plan + project + session as rivals).
2. **Perché adesso?** — ranking explanation from real factors/sources/confidence/missing data/`ranking_version` (may include Goal factors when linked); correct / ignore. No chain-of-thought, no invented reasons.
3. **Dynamic actions** — only type-specific actions from the API (event / study / payment / needs_review / reply / generic). No dead buttons.
4. **La tua situazione** — replaces “La tua giornata”; max 4 real indicators; CTA **Vedi situazione completa** → `/situazione` (real view).
5. **Google Calendar** — large connect card removed. Connected: no promo. Disconnected: compact banner (Collega / Non ora). Full config in Settings.
6. **Priorità** — replaces “Dopo”; groups Critico / Oggi / Questa settimana / In attesa / Più avanti; only non-empty; type-specific cards.
7. **ORA TI CONSIGLIA** — max 3 Proactive Engine suggestions (Accetta / Ignora / Ricordamelo dopo / Apri); hidden when empty. See `docs/PROACTIVE_ENGINE_PRODUCT.md`. Email/Finance/Weather/WhatsApp predisposed only.
8. **ORA osserva** — max 1–2 real insights (text, source, action, status, created, validity, ignore, dedupe).
9. **Continua da dove avevi lasciato** — one real resume item (flashcard/quiz) or hidden.

## Removed from Home

- Large Google Calendar hero card
- 100/100 daily score
- Fake energy estimation as a product signal
- Numbering 2–6 on “Dopo”
- Legacy “Dopo” list
- Identical action buttons for every type
- Seed/mock Home cards (valigia/Marco/Milano/Palestra mock paths not used on Home)
- Empty “Perché?” with no data
- Dead CTAs

## Platforms

- Verified target: **Expo web + Playwright**
- Native iOS/Android Home V2: **not claimed**
