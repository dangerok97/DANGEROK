# ORA — Development State

Last updated: 2026-08-07 (Life Object Engine v2 — Semantic Integrity & AI Validation)

## Branch

- Active: `feature/life-object-engine` (tip ~`0ab2f2b` + semantic integrity commit)
- No push / no merge

## Life Object Engine v2 (this batch)

**Framing:** Gemini = consultant; backend = autorità. Validator sempre prima del persist. Home UX **invariata**.

| Item | Stato |
|------|--------|
| Semantic Validator | **implemented** — `semantic_validator.py` |
| Canonical title generator | **implemented** — mai AI come titolo finale; blocca HOME+Lavoro |
| Property Registry | **implemented** — alias → canonical |
| Knowledge Gap Engine | **implemented** — concetti, non field names grezzi |
| Assimilation Engine | **implemented** — mutuo/bolletta aggiornano HOME.state |
| Link states (4) | **implemented** — solo REAL_CONFLICT user-facing |
| Health 2.0 | **implemented** — dimensioni spiegabili + cap <1.0 |
| Source provenance | **implemented** — typed sources + total_sources |
| Narrative/Insights prompts | **updated** — consulente / osservazioni |
| Home V3 DTO | **PREDISPOSTO** (flag OFF) — campi v3 |
| Tests unit + growth + regression | **green** (`life_objects/tests/` 23 passed) |
| Home UX / schermata Life Objects | **NON toccata** |

## Prior (ancora valido)

| Item | Stato |
|------|--------|
| Shadow core + enrichment | **implemented** |
| `LIFE_OBJECT_ENGINE_ENABLED=1` / `HOME_UI=0` | **yes** |
| Satelliti eliminati? | **NO** |

## Open / next

1. Home V3 UI — solo con flag=1 — **non fare ora**
2. Hook conversazione → `conversation_sources` (struttura pronta)
3. Merge UI solo per REAL_CONFLICT
4. Non aggiungere Email / Open Banking / WhatsApp / Weather qui

## Credentials / safety

- Never commit `.env` / tokens
- CI green senza secret; Gemini gated / fallback
- AI cannot invent facts; no silent Casa 2; no HOME title «Lavoro»
