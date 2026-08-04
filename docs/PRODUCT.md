# ORA — Product

## Vision

ORA is the operating system of daily life. It turns personal information into ranked, resolvable actions so the user does not have to organize everything manually.

## Principles

- Never a chatbot-first experience.
- Never a generic task manager / calendar clone.
- Every screen answers one question.
- Design: dark-first, Apple HIG, monochrome, calm.

## Users

People who juggle calendar events, documents, memories, and priorities and want a single “what matters now” surface.

## Main flows

1. **Auth** — Register/login with email+password; Google via Emergent bridge; Apple placeholder.
2. **Home (“Cosa conta adesso”)** — Ranked decisions with resolve actions.
3. **Aggiungi** — Capture a priority or a memory.
4. **Memoria** — Natural-language Q&A over saved memories (LLM-backed).
5. **Documenti** — Upload/browse documents, insights, contextual actions (copy IBAN, add calendar event, …).
6. **Profilo / Settings** — Account, connectors, calendars.
7. **Calendars** — Google Calendar OAuth connector; Apple Calendar (device / mock / EAS notes).

## Feature areas (shipped in Emergent iterations)

| Area | Status (as imported) |
|------|----------------------|
| Decision Engine | Shipped |
| Life Graph + Knowledge | Shipped |
| Auto-Link | Shipped |
| Permissions + Connectors | Shipped |
| Google Calendar ingestion | Shipped (needs OAuth env) |
| Apple Calendar | Partial (mock + native path; EAS checklist) |
| Daily intelligence / explainability / action center | Shipped |
| Behavioral intelligence + shadow mode | Shipped (flagged) |
| Documents + insights + actions | Shipped through Iter 23 |

## Out of scope for Cursor platform setup

Changing product vision, replacing the stack, or removing shipped modules.
