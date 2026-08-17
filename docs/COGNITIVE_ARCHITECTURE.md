# ORA Cognitive Architecture

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
proposals under the existing authority and clarification rules.

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
