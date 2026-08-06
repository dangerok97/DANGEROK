# Semantic Extraction Layer + Gap Analyzer — Product

## What it is

ORA turns free Italian text into **structured meaning** (entities with confidence) and asks **only the next useful question**. It is not a chatbot and does not replace Intent Classification.

## User-visible behavior

- Say «Fra due settimane parto.» → ORA knows the departure (+14 days) and asks **Dove andrai?** — never «Quando parti e quando torni?»
- After «Vibo Marina» → asks **return only**
- «Dal 9 al 24 agosto vado a Vibo Marina in auto.» → first asks about **lodging**, not dates/place/transport
- Exam / medical / payment phrases fill known fields and skip redundant questions
- Action screen shows a compact **understood summary** (Partenza / Destinazione / Ritorno) without technical IDs

## Pipeline (product view)

User input → Semantic Extraction → Intent Classification → Entity Normalization → Context Merge → Gap Analyzer → Goal → Action Engine → Flow

Conversation Engine orchestrates. Action Engine **renders** the Gap Analyzer question; it does not freely re-parse text to choose questions.

## Confidence

| Band | Range | Behavior |
|------|-------|----------|
| High | ≥ 0.85 | Use; never re-ask |
| Mid | 0.60–0.84 | Confirm if needed; still not "missing" |
| Low | < 0.60 | Ask |

## Privacy

Minimal context to Gemini (optional). No secrets, tokens, full documents, bank or health dumps. No chain-of-thought storage — validated JSON only.

## Flag

`SEMANTIC_ENGINE_ENABLED=1` (default ON). Deterministic extraction always works without Gemini.
