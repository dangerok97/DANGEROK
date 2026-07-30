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

## Iteration 6 — Auto-Link Engine (SHIPPED)
Deterministic Decision ↔ Node link proposer. Independent module `/app/backend/auto_link/`. Decision Engine and Life Graph untouched. Zero UI/design changes. No GPT, no external calls.

**Components** (`auto_link/`):
- `types.py` — enums, `MATCHER_VERSION = "auto_link/v1.0"`, `Thresholds` (auto_accept 0.95, propose 0.70, diagnostic 0.50, ambiguity_floor 0.60), category↔type compat matrix, verifiable-signal set.
- `repository.py` — read-only facade over `db.decisions`, `db.life_nodes`, `db.node_knowledge`; writes limited to `db.link_proposals` and (indirectly, via LifeGraphService) `decisions.node_ids`.
- `candidate_finder.py` — narrows the node set via category compat + explicit references + identifier hints (plate→car, contract_id→contract, iban→finance, …) + label text scan.
- `matcher.py` — 6 pure, testable strategies: `s_explicit_link`, `s_verifiable_identifiers`, `s_category_type`, `s_knowledge_text_match`, `s_node_label`, `s_keywords`, plus `s_graph_direct` for depth-1 propagation.
- `confidence.py` — saturating-sum combiner (`1 - Π(1-cᵢ)`), ambiguity marker, auto-accept gate.
- `service.py` — orchestration, idempotent analyze/reanalyze, accept/reject, decision signature, versioning.

**Data model** `link_proposals`:
- `id, user_id, decision_id, node_id, node_type, node_label_safe, status, confidence, ambiguous, matching_signals[{tag, description, contribution, verifiable}], reason, matcher_version, decision_signature, node_knowledge_version, provenance{source_type, actor_type, confidence, verified_by_user, extracted_at}, diagnostic_only, created_at, updated_at, accepted_at, accepted_by, accepted_by_user, accepted_by_system, acceptance_reason, rejected_at, rejected_by, rejected_by_user, correction_reason, previous_node_id, expires_at, expired_at, expired_reason, superseded_at, superseded_reason`.
- Statuses: `proposed | accepted | rejected | expired | superseded`.

**Auto-accept rules**: fires ONLY when confidence ≥ 0.95 AND ≥1 signal is `verifiable=true` AND `ambiguous=false`. Verifiable tags: `EXPLICIT_LINK, EXPLICIT_LINKED_TO, VERIFIABLE_PLATE, VERIFIABLE_CONTRACT, VERIFIABLE_DOCUMENT, VERIFIABLE_IBAN`. Keywords alone can never auto-accept.

**Ambiguity**: if ≥2 candidates pass 0.60 confidence, all are marked `ambiguous=true` and NONE is auto-accepted.

**Idempotence**: same `(decision_signature, node_id, matcher_version, node_knowledge_version)` → no duplicate proposal. Data changes → old proposals become `superseded` on next analyze.

**Rejection suppression**: after user rejects, the same proposal is NOT regenerated by `/analyze` unless decision changes; `/reanalyze` (force) can re-propose.

**Accept path**: atomic + idempotent. Only external write is `LifeGraphService.link_decision(user_id, decision_id, [node_id])` — history event `life_graph.linked` recorded on the decision (cross-cutting audit).

**Sensitive redaction**: signals derived from `sensitivity in {sensitive, highly_sensitive}` never expose the raw value inside `description` (uses `<redacted>` or omits value entirely).

**Endpoints** (all under `/api`, all require Bearer token):
- `POST /auto-link/decisions/{id}/analyze` · `POST /auto-link/decisions/{id}/reanalyze`
- `GET  /auto-link/decisions/{id}/proposals?include_all=<bool>`
- `GET  /auto-link/proposals/{id}` · `POST /accept` · `POST /reject`

## Preliminary correction (iteration 6)
`_refresh_time_anchors` and `_ensure_live_imminent` are now gated behind `is_demo=user.email in DEMO_EMAILS`. Real users' Decisions are never modified by login (5-login byte-stability test passes). Dedicated admin endpoint `POST /api/admin/demo/refresh` — 200 for demo users, 403 for everyone else.

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
