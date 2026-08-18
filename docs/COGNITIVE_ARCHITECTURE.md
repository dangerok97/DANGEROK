# ORA Cognitive Architecture

## Context continuity V3

```text
Perceive → Situation → Stage A → Reason → ContextNeed
→ Context Broker V3 → Evidence → Reason → Tool/answer/mutation
→ Observe → Persist justified state
```

L'AI decide quale informazione è rilevante e perché. Governance valida purpose,
scope e budget. Il broker seleziona fonti registrate, recupera evidence
minimizzata, conserva conflitti/authority/provenance e non interpreta l'intento.
Le source non decidono la conversazione. Situation fornisce continuità semantica
anche cross-session; non è un router. Retrieval non equivale a Memory write.
Failure di source e assenza di evidence restano esiti distinti e osservabili.

## Operating principle

**AI decides. System guarantees. Tools execute.**

The production conversational surface (`/ora`) uses one domain-neutral AI Core.
The model decides what is happening, what context is relevant, whether to ask,
and which capability is useful. Deterministic runtime code owns authentication,
identity, persistence, schema validation, provenance, temporal integrity,
idempotency, ownership and side-effect safety.

## Situation Model V1

A Situation is contextual life state: something expected, ongoing, recently
changed, resolved or cancelled. It is user-scoped, may reference the session
that created it, and can outlive that session.

- Situation is not Life Memory.
- Situation is not a domain flow or intent router.
- `semantic_kind` is optional open descriptive metadata, never an enum/router.
- The AI selects `create`, `update`, `cancel`, `resolve` or `none`.
- The runtime creates canonical ids and validates ownership, revision and state transitions.
- Mutations retain bounded provenance/history; superseded values stop being active.
- Plans and GenerativeObjects change only through separate successful Life OS capabilities.

AI Core receives a minimized slice: session-related situations first, followed
by a few recent active/changed user situations. It never receives a full dump.

## Separation of state

| State | Purpose | Durability |
|---|---|---|
| Situation | Temporal/contextual life event | User-scoped until resolved/cancelled retention policy |
| Conversation state | Current reasoning and recent turns | Session-scoped |
| Life OS plan/object | Executable, revisable work | Durable user-owned state |
| Life Profile / Memory | Durable knowledge about the person | Governed epistemic state |

No Situation mutation promotes a fact into Memory. Memory candidates remain
proposals under governed learning.

## Memory Proposal & Governed Learning V2.8.3

The AI decides whether a turn contains potentially durable learning and expresses
an optional `MemoryCandidate`. The runtime never learns every turn: it validates
schema, ownership, provenance, temporal scope, authority, sensitivity, revision
and idempotency, then returns a structured observation. The AI reasons again.

- `Situation` is temporal/contextual state; `Memory` is selective cross-session knowledge.
- `tentative` and `inferred` propositions require clarification; confidence cannot erase uncertainty.
- Direct durable user evidence can be promoted; raw device presence cannot.
- Corrections and supersessions preserve prior records and history.
- Forgetting targets an exact user-owned id and creates a logical tombstone.
- Open `kind`/`identity_key` support identity validation only; they never route cognition.
- Preferences influence reasoning as evidence and never become unconditional behavior rules.
- Stage A exposes only an opaque existence index for active governed Memory. Stage B
  retrieves bounded detail; actionable governed refs are distinguished from read-only
  derived Life Memory evidence.
- Runtime re-entry blocks save/forget claims without a persisted governance outcome and
  blocks a later active-only lookup from contradicting a successful write in the same turn.

```text
AI decides candidate and semantic relationship
→ System guarantees governance, identity and persistence
→ Context Broker retrieves active promoted evidence when useful
```

## Mutation flow

```text
AI structured decision
→ SituationUpdate validation
→ ownership + revision + transition checks
→ idempotent persistence in the reasoning epoch
→ structured observation
→ user-facing claim only after success
```

Client-side capability resume reuses the same reasoning epoch. A new user turn
gets a new epoch, so later corrections can update the same Situation.

## Provider failure boundary (V2.8.3a)

Provider reliability remains below cognition: it does not change prompts,
decisions, Memory, Situation or Context Broker semantics. Typed external
failures can move to the next configured provider; unknown internal ORA errors
cannot. When the configured chain is exhausted, AI Core receives a sanitized
`LLMProviderUnavailable` and follows its existing honest soft-failure path
without exposing vendor, quota or authentication detail to the user.
