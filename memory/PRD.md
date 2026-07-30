# ORA — Product Requirements Document

## Vision
ORA is the operating system of daily life. It removes cognitive load by turning every stream of personal information into ranked, resolvable actions. The user never has to organize anything — ORA shows only what matters right now.

## Core Principles
- Never a chatbot. The user talks little, the AI works a lot.
- Never a task manager, calendar, or Notion clone.
- Every screen answers one question. Every animation has a purpose.
- Design: dark-first, Apple HIG, monochrome, glass sparingly, calm and timeless.

## Tech Stack
- Frontend: Expo (React Native) + TypeScript, expo-router file routing
- Backend: FastAPI + MongoDB (Motor async)
- AI: OpenAI GPT-5.2 via `emergentintegrations` (Emergent Universal Key)
- Auth: Emergent-managed Google OAuth **and** email/password (JWT + bcrypt)

## MVP v1 (this iteration)
1. **Login** — Apple placeholder, Google (Emergent OAuth), Email.
2. **Home / "Cosa conta adesso"** — max 5 auto-sorted priority cards, each with a big **RISOLVI** button.
3. **RISOLVI** — GPT-5.2 proposes a concrete, immediately actionable solution in Italian.
4. **Memoria** — Arc-Search style, natural language Q&A over the user's saved memories.
5. **Aggiungi** — quick capture: new priority task or new memory.
6. **Profilo** — user info, section placeholders for future life-OS modules, logout.
7. **Priority scoring** — weighted model over urgency, importance, risk, time, energy, economic/personal impact.
8. **Seed data** — first login seeds 5 realistic Italian priority cards.

## API surface
- `POST /api/auth/register` `POST /api/auth/login` `POST /api/auth/google-session` `GET /api/auth/me` `POST /api/auth/logout`
- `GET /api/priorities` — top 5 open, sorted by score
- `GET|POST /api/tasks` — full CRUD
- `POST /api/tasks/{id}/{resolve|complete|dismiss}`
- `GET|POST /api/memory` `POST /api/memory/ask`

## Roadmap
- v2: Documents (upload + AI parsing), Expenses dashboard, Goals with daily nudges.
- v3: Integrations bridge (Calendars, Gmail, WhatsApp, Wallet, Banks – modular adapters).
- v4: Smart notifications (context-aware, non-invasive), Health/Sleep, Home automation.

## Innovative future features
- **Silent Mode**: ORA decides for you and executes the reversible action, telling you after.
- **Trust Score**: rate ORA's suggestions to teach it your judgment.
- **Life Timeline**: ambient monthly recap generated from tasks + memory.
- **Delegated actions**: send "resolve this" to a partner or assistant via one tap.
