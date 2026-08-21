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
# V2.8.4 — Uncertainty is decision state, not a second brain

`AI DECIDES. SYSTEM GUARANTEES. TOOLS EXECUTE.` The AI expresses a bounded uncertainty state:
missing information, ambiguities, reversible assumptions and whether unresolved information
is blocking. It chooses `context`, `ask`, `answer`, `tool` or `act`. The runtime never uses
domain keywords to choose among them; it enforces budgets, ownership, privacy, no repeated
semantic question, no unsafe side effect and failure honesty.

Situation may preserve justified contextual assumptions and their supersession history.
Memory governance remains separate: an assumption is never a fact and never bypasses the
MemoryCandidate governance path. Context Broker retrieves evidence but does not decide intent.

# V2.8.5 — Life Context Graph: relationships between canonical refs, not a second brain

`backend/context_graph/` adds one thing the AI Core did not previously have: a durable,
AI-authored, system-governed RELATIONSHIP between two canonical refs it already sees in its
own evidence (`situation:`, `goal:`, `plan:`, `object:`, `document:`, `calendar:`, `profile:`,
`file:`, `presence:`, or a bare governed `mem_` id). It stores no duplicate node data — an
edge (`ContextEdge`) is only `subject_ref --predicate--> object_ref` plus provenance,
authority, confidence, temporal_scope and revision/history, mirroring the conventions already
proven by Situation (revision/history/`applied_epochs` idempotency) and Memory
(`supersedes_refs`/`coexists_with_refs`/governance-key idempotency) rather than inventing a
third pattern.

`predicate` is fully open, AI-authored free text (format-normalized only: lowercase,
underscores, ≤60 chars) — the runtime never chooses among relationship meanings and never
special-cases a predicate value. The only structural guarantees are: refs must match a known
canonical prefix (never a domain taxonomy), no self-loops, ownership, idempotency per
`reasoning_epoch`, and that a conflicting active edge (same subject+predicate, different
object) surfaces as `REQUIRES_SUPERSESSION` for the AI to resolve explicitly — it is never
silently overwritten or silently duplicated.

The Context Broker gained one new bounded source, `life_context_graph`, registered in the
existing Source Registry exactly like every other source (no new orchestrator, no second LLM
call). Retrieval seeds from the AI's own hinted refs plus the user's currently active
Situation/Plan/Goal, expands at most one further hop (depth ≤ 2), and caps at 10 edges — the
same bounded-evidence discipline Context Broker V3 already applies everywhere else.

Existing entity/model boundaries are unchanged: Situation still owns ephemeral contextual
state, Memory still owns durable propositions with its own governance, Life OS still owns
plans/goals/objects. The graph never promotes a temporary Situation fact, an unconfirmed
inference, or a raw presence/GPS signal into a durable edge on its own — every edge carries
the same honest authority/confidence the AI declared, never upgraded silently.

# V2.8.6b — Calendar as a capability, not a second reasoning mode

Calendar joins the AI Core the same way every other capability does: `get_calendar_events` is
one more bounded evidence source the AI reaches for like any other, and
`create_calendar_event`/`update_calendar_event`/`cancel_calendar_event` are three more
`REVERSIBLE_WRITE` tools in the same `ToolRegistry`. No intent classifier, no domain router, no
separate calendar reasoning loop was introduced — the general-purpose cognitive loop
(`response_mode` ∈ {answer, ask, tool, act, context, finish}) is unchanged in shape.

Two structural guarantees are the entire runtime contribution here, both reused rather than
invented: (1) any `REVERSIBLE_WRITE` tool call carrying a blocking `uncertainty` is already
stripped by `governance.py`'s existing `_blocks_side_effect` gate — a calendar write is not a
governance special case; (2) a calendar write claim in the AI's own output text
(`_CALENDAR_CLAIM_RE`) that is not backed by a real confirmed Observation this turn triggers the
same persist-before-claim nudge already proven for Memory and the Context Graph — one honest
re-entry, then a forced honest retry message if the AI claims success a second time without
persisting.

Whether a time-bearing statement becomes a CalendarEvent, stays a Situation fact, becomes a Life
OS plan/goal deadline, or is nothing at all is explicitly left to the AI's own judgment — the
same judgment already governing Situation vs Memory vs Graph. This is a deliberate absence of a
decision tree, not an oversight: a hardcoded `if "domani" in text` or `if "ricordami" in text`
branch would reintroduce exactly the kind of keyword router this architecture has consistently
avoided elsewhere, and is statically forbidden by `test_ai_native_calendar_v286b.py`'s
`test_v`/`test_z`. Calendar's relationship to Situation/Plan/Goal is likewise never inferred by
the runtime — the AI proposes it through the existing `context_graph_updates` channel (V2.8.5),
using an open predicate like `scheduled_as` or `supported_by`, exactly like any other relationship
the AI already knows how to propose.
