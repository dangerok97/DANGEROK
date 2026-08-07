# ORA — Development State

Last updated: 2026-08-07 (Digital Twin Knowledge Model)

## Branch

- Active: `feature/life-object-engine` (tip ~`a5b490c` + knowledge model commit)
- No push / no merge

## Digital Twin Knowledge Model (this batch)

**Framing:** cinque sezioni indipendenti su ogni Life Object. Gemini=consultant; backend=autorità. **Fact mai cancellato.** Home UX **invariata**.

| Item | Stato |
|------|--------|
| Package `life_objects/knowledge_model/` | **implemented** |
| Facts (supersede/archive, no delete) | **implemented** |
| Hypotheses (confirm→Fact, reject) | **implemented** |
| Decisions + never_ask_again | **implemented** |
| Goals link-only | **yes** (no Goal Engine dup) |
| Memory narrativa + Timeline semantica | **implemented** |
| Assimilation / upsert → Fact o Hypothesis | **wired** |
| Migration identity/state → knowledge | **non-destructive** |
| API read + write minimi test | **implemented** |
| Home V3 `knowledge_summary` | **PREDISPOSTO** (flag OFF) |
| Tests knowledge + regression | **31 passed** (`life_objects/tests/`) |
| Playwright knowledge API | `e2e/life-object-knowledge-model.spec.ts` |
| Home UX / schermata Life Objects | **NON toccata** |

## Prior — Life Object Engine v2 (ancora valido)

| Item | Stato |
|------|--------|
| Semantic Validator / titles / registry / gaps / assimilation | **implemented** |
| Link states / Health 2.0 / provenance | **implemented** |
| `LIFE_OBJECT_ENGINE_ENABLED=1` / `HOME_UI=0` | **yes** |

## Open / next

1. Home V3 UI — solo con flag=1 — **non fare ora**
2. UX confirm/reject ipotesi (oggi API interna)
3. Hook conversazione → facts/hypotheses
4. Non aggiungere Email / Open Banking / WhatsApp / Weather qui

## Credentials / safety

- Never commit `.env` / tokens
- CI green senza secret; Gemini gated / fallback
- AI cannot invent facts; no silent Casa 2; Facts immutable history
