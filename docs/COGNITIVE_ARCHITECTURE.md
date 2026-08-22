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

# V2.9.1 — Life Change Signal: "what changed", not "what it means"

Everything ORA has built so far answers questions *within* a turn: the user says something, the
AI reasons, tools execute, state is persisted, the turn ends. V2.9.1 adds the first piece of
infrastructure that outlives a turn — a durable, neutral record that the user's life state moved.

The cognitive contribution is a **separation of three questions that are easy to collapse and
expensive to un-collapse**:

| Sprint | Question | Owner |
|--------|----------|-------|
| V2.9.1 | WHAT CHANGED? | deterministic runtime |
| V2.9.2 | SO WHAT? | AI reasoning over bounded context |
| V2.9.3 | SHOULD I SPEAK? | attention/intervention policy |

A LifeChangeSignal answers only the first, and answers it *without judgement*. It has no
`importance`, no `urgency`, no `intent`, no `recommended_action`, no `notification_text` and no
domain label — deliberately, because every one of those fields would be a place for a future
engineer to hardcode a heuristic that belongs to the AI. The signal says a Situation was created,
a Memory superseded, a relationship linked, a calendar event rescheduled — and stops.

This is why the runtime layer stays fully deterministic here and adds **zero LLM calls**. Asking
Gemini "is this change important?" at mutation time would mean paying a reasoning call for every
write in the system, and would bake an interpretation into the event store before any context is
available. V2.9.2 will instead read a bounded batch of pending signals, resolve authorized
context through the existing Context Broker, and reason once — at the moment reasoning is
actually useful.

The boundaries with existing memory-like subsystems stay strict and are asserted by test:
**Signal ≠ Memory** (a signal is never promoted to a durable proposition), **Signal ≠ Situation**
(a signal is not contextual state the AI reads each turn), **Signal ≠ Graph edge** (emitting
never creates a relationship), **Signal ≠ Suggestion** (nothing proactive is generated). The
Context Broker deliberately does not gain a signal source: this store feeds future asynchronous
reasoning, not the normal per-turn answer.

Generality is structural rather than semantic here. Because the signal is deterministic, the
runtime cannot "understand" that a user is organizing a neighbourhood party, caring for an
inherited bonsai, or mounting a photography exhibition — and it does not need to. Those three
arbitrary scenarios appear in the test suite precisely to demonstrate that they traverse the
identical code path as any other life change, with no domain branch anywhere. The meaning of the
change remains where it belongs: with the AI, later, when it has the context to judge it.

# V2.9.2 — Impact Reasoning: the first time ORA thinks between turns

Everything before V2.9.2 reasoned *inside* a turn: the user speaks, ORA thinks, ORA answers.
V2.9.2 is the first layer that reasons about the user's life when the user is not present, and
the first that asks a question nobody typed: **given that this changed, what might it mean?**

That makes the epistemic discipline more important, not less. Inside a turn, a wrong inference
gets corrected immediately by the person reading it. Here it would be persisted, unchallenged,
and later consumed by V2.9.3 as though it were understanding. So the prompt's hardest constraint
is not "find consequences" but **"never invent"**: state no fact the evidence does not support,
invent no date, amount, name, document, commitment or person, and express a possibility as a
possibility. `epistemic_status` (reused verbatim from Memory) is what carries that distinction —
`confirmed` and `asserted` require evidence refs, while `inferred` and `tentative` are honest
labels for reasoning that has run ahead of its grounding. An assessment that concludes "I do not
know enough yet" is a *correct* output; a confident narrative built on nothing is a failure, and
the provider-real gate tests exactly that.

**Need discovery is the point.** People rarely enumerate what a goal requires. The reasoning is
asked to notice dependencies nobody mentioned — preparation, information, resources, people,
permissions, timing, prerequisites — and to surface them as `dependency` or
`missing_information`, held as *possible* until evidence confirms them. This is how ORA widens
what it considers without deciding for the user, and it is the mechanism that must eventually
carry a sentence like "would it help if I looked at financing too?" — without any code anywhere
knowing what financing is.

**Generality is enforced by refusing category reasoning.** The prompt explicitly forbids
pattern-matching a change to a familiar life category and reciting what that category "usually"
involves: two people doing nominally the same thing can need entirely different things, so the
model must reason from *this* user's evidence. There is no domain taxonomy in the contract — the
`kind` vocabulary is six general-purpose technical categories, and a static test asserts no
domain term survives in executable code. A neighbourhood party, an inherited bonsai, a
photography exhibition and a significant purchase all traverse the same path.

**Capability awareness without capability execution.** The model sees the names of what ORA can
do, so it can distinguish a need ORA could already serve from one it cannot yet. A
`capability_hint` is validated against the live registry — an invented capability is dropped
rather than recorded as if it existed — and nothing is ever called. Noticing that a need exists
and being able to act on it are different states, and V2.9.2 only records the first.

**And it stops before speaking.** `relevance` means "how much this seems to matter in this user's
life", never "how much I want to interrupt them". The contract has no field for notification,
timing or urgency of interruption, because the moment reasoning is allowed to decide its own
audibility, a Life OS becomes a notification machine. Whether any of this is worth saying is
V2.9.3's question, and keeping it a separate question is what keeps the answer honest.

# V2.9.3 — Attention: the right to stay quiet

The three questions are now complete, and the last one is the one that decides what kind of
product ORA is:

| Sprint | Question | Owner |
|--------|----------|-------|
| V2.9.1 | WHAT CHANGED? | deterministic runtime |
| V2.9.2 | SO WHAT? | AI reasoning over bounded context |
| V2.9.3 | SHOULD I SPEAK? | AI judgement **and** deterministic system permission |

An assistant that says everything it notices is worse than one that notices less. V2.9.2 can
easily produce ten consequences from a single afternoon; mentioning ten would be indistinguishable
from spam, and each one spends a little of the user's trust whether or not it was accurate.
So the first-class outcome of this layer is **silence** — the prompt opens by saying so, and the
model is told not to look for a reason to speak but for a reason the user would be glad it did.

**Relevance is not permission.** This is the distinction the whole sprint exists to enforce.
Something can be true, well-reasoned, genuinely important — and still not something to say at
11pm, or for the fourth time, or to someone who has dismissed the last three like it. The model
judges worth; a deterministic gate judges admissibility; and the gate can only ever make the
result quieter. Recording both `ai_delivery` and `delivery` makes every downgrade auditable, and
makes it impossible to later mistake "the model wanted to speak" for "ORA was allowed to".

**Safety is deliberately not in the prompt.** The model is not asked whether the user is asleep,
busy, or over-messaged — it is not even shown those facts. The moment "is the user asleep?"
becomes a prompt question it becomes negotiable, and a sufficiently confident model will
negotiate. Quiet hours resolve through the user's real timezone; occupancy comes from actual
calendar overlap; volume and dismissal come from what already happened. None of it is inferred
from what a calendar entry is *called*: knowing someone is busy is honest, guessing they are
driving from the word "guida" is not, and being wrong about the second is worse than not knowing.

**Learning is bounded on purpose.** Repeated dismissal raises the bar and lowers the surface —
it never becomes "never mention this again". A user who ignores something today may need it next
month, and an assistant that permanently silences a topic after three dismissals has quietly
replaced the user's judgement with its own.

**Asking is expensive too.** A proactive question is an interruption that also demands work from
the user, so `ask_user` is reserved for a specific missing piece that would genuinely unblock
something — never curiosity, never something ORA could look up, never a question whose answer
changes nothing. The provider-real gate tests exactly this: an abstract "something is missing"
correctly stays silent, and only a concrete near-term blocker the user alone can clear earns a
question.

**Nothing here speaks by itself.** A permitted decision becomes a candidate for the Proactive
Engine that already existed, and must still pass its scoring, its dedupe, its rate limits and its
"would a real assistant speak up?" test. Two independent judgements — the model's about worth and
the system's about admissibility — must agree before a single user-facing item appears. That
conjunction, not either half alone, is what keeps a Life OS from becoming a notification machine.
