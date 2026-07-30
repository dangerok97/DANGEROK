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

## Iteration 2 — Decision Engine (SHIPPED)
The reasoning core of ORA. Task → **Decision** (richer schema). New modular package `/app/backend/decision_engine/`:
- `DecisionContext` — snapshot of the world at eval time (extensible signal bag).
- `DecisionEvaluator` — base multi-factor score (replaceable, e.g. with an ML model later).
- `DecisionReasoner` — extensible rule engine. Each rule returns a score delta + a human-readable Italian fragment + a tag. Rules shipped: `imminent_event`, `deadline_proximity`, `trip_dependency`, `high_stakes_dampens_leisure`, `bill_at_risk`, `quick_win`, `positive_signal`.
- `DecisionRanking` — composes evaluator + reasoner and produces the ordered list with `reason` + `reason_tags`.
- `DecisionService` — CRUD, one-shot migration from legacy `tasks`, seeding.

Behavior added:
- Dependency reasoning (e.g. a flight tomorrow → "prepara la valigia" auto-boosted).
- Contextual dampening (exam/deadline within 48h dampens fitness/leisure).
- Insight-type decisions never reach the top ("Hai risparmiato 220€" ≠ action).
- Every decision has a `reason` visible in the Home under the card.
- Home now shows max 3 + "Mostra altro". Design unchanged.
- Rich schema on `decisions` collection: title, description, origin, category, urgency, importance, risk, economic_impact, personal_impact, time_required_min, energy, place, people, starts_at, deadline, status, linked_to, metadata, history, created_at.
- Full history log per decision (created, resolved, dismissed, ai_resolution_proposed, migrated_from_task, seeded).
- Legacy `/api/tasks` + `/api/priorities` still work (read/write decisions transparently).

## Iteration 3 — Life Graph Core (SHIPPED)
Persistent representation of the user's life as a graph of Nodes + typed Edges. Independent module `/app/backend/life_graph/`. **Decision Engine untouched.** No UI/design changes.

- **Node types**: `home, car, person, job, university, trip, subscription, contract, document, purchase, health, pet, goal, event, finance, generic`.
- **Relation types**: `owns, lives_at, belongs_to, pays_for, documents, assigned_to, has_member, related_to, parent_of, generic`.
- **Decision ↔ Node**: decisions gain an optional `node_ids: []` field written exclusively by the `LifeGraphService` (idempotent `$addToSet`, history-logged). Decision Engine payloads pass through unchanged.
- **Traversal**: in-memory BFS `neighborhood(node_id, depth)` returning `{root, nodes, edges, distances, decisions}`. Bounded depth ≤ 6.
- **Seed**: idempotent `POST /api/life-graph/seed` creates a demo graph: Io → lives_at → Casa → parent_of → Bolletta Luce; Io → owns → Auto → assigned_to → Assicurazione; Io → has_member → Lavoro; Io → related_to → {Salute, Università}.
- **Endpoints**: `GET /api/life-graph/vocabulary`, `POST /api/life-graph/seed`, full CRUD on `/nodes` and `/edges`, `GET /nodes/{id}/graph?depth=`, `GET /nodes/{id}/decisions`, `POST /life-graph/decisions/{id}/nodes`, `DELETE /life-graph/decisions/{id}/nodes/{node_id}`.
- **Cascade**: archiving a node removes its edges and unlinks it from all decisions.
- **Cross-user isolation**: every query filtered by `user_id`.

## Iteration 4 — Knowledge Layer (SHIPPED, hardened in iteration 5)
Structured, per-node-type properties on top of Life Graph nodes. Independent module `/app/backend/knowledge/`. Own collection `node_knowledge` keyed by `(user_id, node_id)`.

**Iteration 5 hardening added:**
- **Property envelope** on every stored property: `{value, value_type, unit, format, sensitivity, provenance}`.
- **Provenance metadata**: `source_type ∈ {user_input, ai_extraction, document, email, calendar, banking, system, migration}`, `source_id`, `confidence ∈ [0,1]`, `verified_by_user`, `extracted_at`, `last_confirmed_at`. Same-value re-declaration preserves `extracted_at` and bumps `last_confirmed_at`.
- **Sensitivity classification**: `public | personal | sensitive | highly_sensitive` — encoded in schema per property, sensitive values are redacted in audit history and logs.
- **Optimistic concurrency**: `version` per doc; writes accept `expected_version`; mismatch → 409 `{error: version_conflict}`.
- **Rich audit**: every mutation → history entry `{at, event, property, previous, next, actor_type, actor_id, source_type, reason}`. Sensitive properties in `previous/next` become `{redacted: true, value_type: …}`.
- **Soft delete + restore**: `DELETE` sets `status=archived, archived_at/by/reason`; `POST /restore` reactivates; permanent purge intentionally not exposed.
- **Input safety**: normalization module rejects `$`-prefix, `.`-embedded, `__proto__`/`constructor`/`prototype` keys; caps key length (64), value length (10k), property count (200), list length (500), depth (6), serialized payload (~60 KB). Reject NaN/Inf. Applied recursively.
- **Soft coercion**: numeric strings → int/float, truthy/falsy strings → bool, scalars → auto-wrapped lists/objects when schema declares them.
- **Atomic single-property API**: `GET/PUT/DELETE /knowledge/nodes/{id}/properties/{key}`. GET on missing key returns `{envelope: null, value: null}`.
- **Cross-user isolation**: every op filters by `user_id` + verifies ownership by reading `life_nodes` read-only.
- **No premature interpretation**: writes never create decisions, never edit life-graph edges, never call GPT, never auto-link.

**Endpoints**: `/api/knowledge/schemas`, `/schemas/{node_type}`, `/knowledge`, `/knowledge/nodes/{id}` (GET/PUT/PATCH/DELETE), `/nodes/{id}/history`, `/nodes/{id}/restore` (POST), `/nodes/{id}/properties/{key}` (GET/PUT/DELETE).

**Demo user drift fix (iteration 5)**: `prepare_user_decisions` now refreshes relative time anchors (`metadata.eta_min` → `starts_at`, `metadata.due_days` → `deadline`) on every login, and if the user has no OPEN imminent decision, seeds a fresh `Esci tra 25 minuti`. Idempotent; never grows the collection unboundedly.

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
