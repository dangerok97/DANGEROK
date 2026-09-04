"""
What ORA is trying to achieve, how it intends to get there, and what it is
allowed to actually do.

    THE USER DOES NOT MANAGE THE AGENT. THE AGENT MANAGES THE WORK.
    THE USER SHOULD EXPERIENCE OUTCOMES, NOT WORKFLOWS.
    AUTONOMY MEANS FEWER QUESTIONS, NOT FEWER SAFEGUARDS.

Four things live here and the distinctions between them are the design.

A **goal** is an outcome, not a task. "Make sure the document is in hand
before Thursday" is a goal; "open the council website" is a step. A system
whose goals are tasks has already decided how, and the deciding is the part
worth having.

A **plan** is a hypothesis about how to get there, and it is expected to
change. Steps carry what they intend, not which button to press: the model
says it needs to read a calendar, and code works out whether there is a
calendar it may read.

**Authority** is split in two, because two very different things get called
"asking". Needing human *knowledge* means only the person knows the answer.
Needing human *authority* means ORA knows exactly what to do and may not do
it. Confusing them produces an assistant that asks permission to think.

And **verification** exists because a tool returning success is not the same
as the outcome being true. An email accepted by a server has not been read;
a booking submitted has not been confirmed.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

# Where a goal came from. Both go through the same engine — there is no
# separate "autonomous" path, and a test enforces that.
GoalOrigin = Literal["user_requested", "agent_initiated"]

# `waiting` is not stalled: it is a goal that depends on something outside
# ORA's control and has arranged to be looked at again.
GoalStatus = Literal[
    "proposed", "active", "waiting", "completed", "cancelled", "failed", "abandoned"
]

# What the model concluded about whether there is anything worth pursuing.
# `no_goal` is the ordinary answer and must stay comfortable to give.
GoalOutcome = Literal["no_goal", "create_goal", "clarify", "wait"]

PlanStatus = Literal["draft", "active", "waiting", "completed", "cancelled", "failed"]

# What a step is for. Domain-neutral by construction: nothing here names a
# calendar, an inbox or a booking, because a step type that did would be a
# plan template wearing a disguise.
StepType = Literal[
    "inspect", "research", "compare", "prepare", "ask_user", "execute", "verify", "wait"
]

StepStatus = Literal[
    "pending", "running", "succeeded", "failed", "skipped", "blocked", "waiting"
]

# How hard it would be to undo. Words, not a score — the difference between
# "reversible with effort" and "irreversible" is a judgement about a
# situation, not a number to compare against a threshold.
Reversibility = Literal["easily", "with_effort", "hardly", "irreversible"]

# What the model concluded about how much authority a step needs. Code may
# always narrow this; it may never widen it.
AuthorityOutcome = Literal[
    "proceed_autonomously",
    "prepare_then_confirm",
    "ask_before_execution",
    "needs_user_information",
    "cannot_proceed",
]

# Why a person is being asked. The whole point of keeping these apart.
AskKind = Literal["knowledge", "authority"]

ExecutionStatus = Literal[
    "succeeded", "failed", "partial", "unavailable", "waiting"
]

# Whether the outcome is actually true — not whether a call returned 200.
VerificationOutcome = Literal[
    "achieved",
    "partially_achieved",
    "not_achieved",
    "uncertain",
    "needs_followup",
    "waiting_for_external_result",
]

# How much ORA may do on its own. Conservative by default, and the default is
# not a decision anybody made.
AutonomyMode = Literal["observe", "prepare", "act_within_grants"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return _now().isoformat()


# What a parameter must not be named. Not a security boundary on its own —
# the boundary is that nothing here ever needs a credential — but the cheap
# check that catches the day somebody passes one by accident.
_SECRETISH = re.compile(
    r"token|secret|password|passwd|credential|authorization|bearer|api[_-]?key|"
    r"refresh|access[_-]?key|cookie|session[_-]?id",
    re.IGNORECASE,
)


def _stable(payload: Dict[str, Any]) -> str:
    """
    Parameters as one comparable string.

    Sorted, so that two dictionaries holding the same thing in a different
    order are the same thing — a hash that changed with insertion order would
    invalidate consent for no reason anybody could explain.
    """
    try:
        return json.dumps(payload or {}, sort_keys=True, ensure_ascii=False,
                          default=str)[:2000]
    except Exception:
        return ""


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


# ---------------------------------------------------------------------------
# V3.9 Sprint 2 — where a result came from, and whether it is a fact.
#
#     A TOOL RESULT IS NOT A LIFE FACT.
#     EVIDENCE PRECEDES BELIEF.
#
# Sprint 1 could get away without this: nothing ran for real, so nothing could
# be mistaken for real. The moment a capability actually does something, the
# distinction between "the world said so" and "we stood in for the world"
# becomes the whole safety story — a verifier that cannot tell them apart will
# close a goal because a stub returned success.
# ---------------------------------------------------------------------------

# Where a result came from. Not a quality score: `simulated` is not worse
# evidence, it is not evidence — and the code that checks this treats it as a
# different kind of thing rather than a lower number.
SourceClass = Literal[
    "internal_observation",       # what ORA already holds about this person
    "connected_provider",         # a service the person actually connected
    "external_research",          # looked up in the world, with sources
    "deterministic_computation",  # arithmetic ORA did itself
    "simulated",                  # a stand-in. Never proof of anything.
    "user_statement",             # the person said so
]

# What is actually behind a capability. The planner is told this, because a
# model that believes everything works will plan through a wall.
CapabilityStatus = Literal[
    "available_real",
    "available_simulated",
    "unavailable",
    "requires_connection",
    "requires_authority",
]

# How old the thing being relied on is. A fact, not a verdict — stale evidence
# is sometimes exactly the right evidence, and that judgement is not code's.
Freshness = Literal["fresh", "recent", "stale", "unknown"]

# What has happened to a declared effect. `executed` and `verified` are
# deliberately two states: a provider accepting something is not the world
# having changed.
IntentStatus = Literal[
    "planned", "prepared", "authorized", "executing", "executed", "verified", "cancelled"
]


class ResultProvenance(BaseModel):
    """
    Where a result came from, attached to the result itself.

    Kept on the result rather than inferred later, because the place that
    knows whether a provider was really called is the code that called it —
    and anything reconstructing it afterwards is guessing.
    """

    source_class: SourceClass = "simulated"
    # Which capability produced it. Never a client name, never an endpoint.
    capability: str = Field(default="", max_length=60)
    # A coarse name for what stood behind it, when there is one worth saying.
    provider: str = Field(default="", max_length=60)
    observed_at: str = Field(default_factory=now_iso)
    source_refs: List[str] = Field(default_factory=list, max_length=8)
    freshness: Freshness = "unknown"
    # In words, when the model needs to know how much to lean on it.
    certainty_note: str = Field(default="", max_length=200)

    @property
    def is_real(self) -> bool:
        """Whether this says anything about the actual world."""
        return self.source_class != "simulated"

    def for_ai(self) -> Dict[str, Any]:
        return {
            "where_this_came_from": self.source_class,
            "really_happened": self.is_real,
            "how_old": self.freshness,
            "note": self.certainty_note or None,
        }


class AgentEvidence(BaseModel):
    """
    One thing that was found out, and what it is worth.

    `supports` names which success criterion this bears on, so verification
    has something to check against rather than a pile of observations. And
    `provenance.is_real` is what keeps a stub out of that check.
    """

    id: str = Field(default_factory=lambda: _id("evd"))
    owner_id: str
    goal_id: str
    step_id: str = ""

    kind: str = Field(default="observation", max_length=40)
    # What was found, in one sentence. Not a dump of what a provider returned.
    claim: str = Field(min_length=1, max_length=600)
    # Which of the goal's criteria this speaks to, if any.
    supports: str = Field(default="", max_length=300)

    provenance: ResultProvenance = Field(default_factory=ResultProvenance)
    observed_at: str = Field(default_factory=now_iso)
    expires_at: Optional[str] = None

    @property
    def is_real(self) -> bool:
        return self.provenance.is_real

    def for_ai(self) -> Dict[str, Any]:
        return {
            "what_was_found": self.claim,
            "bears_on": self.supports or None,
            **self.provenance.for_ai(),
        }


class AgentBudget(BaseModel):
    """
    What one pass of the loop is allowed to spend.

        AN AGENT LOOP WITHOUT A CEILING IS A BILL WITHOUT A CEILING.

    Technical bounds only. Nothing here is a judgement about whether the work
    is worth doing — that is the model's, and it gets to make it inside these
    numbers rather than instead of them.
    """

    cognitive_calls: int = 0
    capability_calls: int = 0
    research_calls: int = 0
    steps_executed: int = 0
    started_at: str = Field(default_factory=now_iso)

    max_cognitive_calls: int = 8
    max_capability_calls: int = 8
    max_research_calls: int = 2
    max_steps: int = 5
    max_seconds: int = 180

    def exhausted(self) -> str:
        """Which ceiling was hit, or empty. Named, so the journal can say."""
        if self.cognitive_calls >= self.max_cognitive_calls:
            return "cognitive_calls"
        if self.capability_calls >= self.max_capability_calls:
            return "capability_calls"
        if self.steps_executed >= self.max_steps:
            return "steps"
        try:
            began = datetime.fromisoformat(self.started_at)
            if (_now() - began).total_seconds() >= self.max_seconds:
                return "time"
        except Exception:
            pass
        return ""

    def research_exhausted(self) -> bool:
        return self.research_calls >= self.max_research_calls



# ---------------------------------------------------------------------------
# V3.9 Sprint 3 — doing it, and being able to prove afterwards what was done.
#
#     ORA DOES NOT JUST KNOW WHAT TO DO. ORA CAN DO IT.
#     A GRANT IS NOT A BLANK CHEQUE.
#     EXECUTED IS NOT VERIFIED. PROVIDER ACCEPTED IS NOT OUTCOME ACHIEVED.
#
# Everything below exists because permission and action come apart in time.
# Authority is judged when a plan is made, approved when somebody is asked,
# and used when the effect finally happens — and between those moments a
# person can revoke, the parameters can change, a process can die halfway.
# Each of the models here closes one of those gaps.
# ---------------------------------------------------------------------------

# What kind of thing an effect is. Domain-neutral: nothing here says calendar,
# inbox or booking, because a vocabulary that named them would be a list of
# situations somebody thought of in advance.
EffectType = Literal[
    "create",    # something new exists that did not
    "modify",    # something that existed is different
    "cancel",    # something that was going to happen will not
    "send",      # something reached somebody else
    "transfer",  # something of value moved
    "publish",   # something became visible to people at large
    "remove",    # something no longer exists
]

# What a provider said. `accepted` is the dangerous one: it means the request
# was taken, not that the world changed — and a system that treats the two as
# the same tells people their booking is confirmed because a form posted.
ProviderStatus = Literal["accepted", "succeeded", "partial", "failed", "unknown"]

# Why an authority decision came out the way it did. A code, not a sentence:
# it is read by tests and by an audit, never by a person.
AuthorityReason = Literal[
    "no_grant",
    "grant_matched",
    "grant_out_of_scope",
    "grant_revoked",
    "grant_expired",
    "explicitly_denied",
    "one_time_consent",
    # Un sì che è già stato usato. Diverso da «non c'è» perché la risposta
    # alla persona è diversa: uno è «non me l'hai mai detto», l'altro è
    # «me l'hai detto per quella volta lì».
    "consent_spent",
    # L'ordine stesso della persona. Non un permesso permanente e non una
    # deduzione: le parole con cui hanno chiesto proprio questo, adesso.
    "explicit_user_command",
    "consent_stale",
    "never_autonomous",
    "not_permitted",
    "not_wired",
    "policy_narrowed",
    "capability_unknown",
]


class ActionEffect(BaseModel):
    """
    What would actually change, said in terms a person could check.

    Kept apart from the step that wants it because a step is a plan and this
    is a claim about the world. The fields are named dimensions rather than a
    score: "reaches somebody else" and "cannot be undone" are different
    reasons to be careful, and a number that averaged them would hide which.
    """

    effect_type: EffectType = "create"
    # What is being acted on, as a handle or a short human phrase — never a
    # payload, and never anything a token could hide in.
    target: str = Field(default="", max_length=200)
    effect_summary: str = Field(default="", max_length=300)

    # Whether somebody other than the owner is touched by this. The single
    # most important field here: an event in your own calendar and the same
    # event with a guest on it are different acts.
    external_party: bool = False
    financial_effect: bool = False
    legal_effect: bool = False
    privacy_effect: bool = False
    public_visibility: bool = False
    destructive: bool = False

    reversibility: Reversibility = "easily"
    expected_outcome: str = Field(default="", max_length=300)

    def fingerprint(self) -> str:
        """
        What this effect *is*, reduced to something comparable.

        Approval is bound to this and not to the intent's id, so that changing
        the target or widening the effect after a yes produces a different
        thing that nobody has agreed to. Deliberately excludes anything that
        moves on its own — no clock, no ids that get regenerated.
        """
        raw = "|".join([
            self.effect_type, self.target.strip().lower(),
            "1" if self.external_party else "0",
            "1" if self.financial_effect else "0",
            "1" if self.legal_effect else "0",
            "1" if self.public_visibility else "0",
            "1" if self.destructive else "0",
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def for_ai(self) -> Dict[str, Any]:
        return {
            "what_kind_of_change": self.effect_type,
            "what_it_touches": self.target or None,
            "in_words": self.effect_summary or None,
            "reaches_somebody_else": self.external_party,
            "involves_money": self.financial_effect,
            "commits_them_legally": self.legal_effect,
            "reveals_something": self.privacy_effect,
            "visible_to_others": self.public_visibility,
            "destroys_something": self.destructive,
            "how_hard_to_undo": self.reversibility,
        }

    def for_human(self) -> str:
        """The one sentence somebody is being asked to agree to."""
        return self.effect_summary or self.expected_outcome


class EffectiveAuthority(BaseModel):
    """
    What the model recommended, and what code actually decided.

        AI ASSESSES THE SEMANTIC RISK. CODE ENFORCES THE AUTHORITY CEILING.

    Both halves are kept because they disagree, and the disagreement is the
    part an audit needs. `matched_grant_id` is the answer to "on what basis" —
    empty when there was none, which is the ordinary case.
    """

    recommended_by_ai: AuthorityOutcome = "ask_before_execution"
    matched_grant_id: str = Field(default="", max_length=64)
    consent_id: str = Field(default="", max_length=64)
    code_ceiling: AuthorityOutcome = "ask_before_execution"
    effective_decision: AuthorityOutcome = "ask_before_execution"
    reason_code: AuthorityReason = "no_grant"
    # Never shown to anybody: it names grants and codes.
    note: str = Field(default="", max_length=300)

    @property
    def may_execute(self) -> bool:
        return self.effective_decision == "proceed_autonomously"

    def public(self) -> Dict[str, Any]:
        return {
            "model_said": self.recommended_by_ai,
            "effective": self.effective_decision,
            "on_what_basis": (
                "un permesso che avevi già dato" if self.matched_grant_id
                else "quello che mi hai appena chiesto"
                if self.reason_code == "explicit_user_command"
                else "il tuo via libera per questa volta" if self.consent_id
                else None
            ),
        }


class AuthorityConsent(BaseModel):
    """
    A yes, bound to exactly what it was a yes to.

        APPROVE IS NOT A GENERIC YES.

    Bound by `effect_hash` rather than by the intent's id, because an intent
    can be rewritten while keeping its name. If the effect changes after
    somebody agreed, this stops matching and they are asked again — which is
    the entire reason it exists.
    """

    id: str = Field(default_factory=lambda: _id("cns"))
    owner_id: str
    action_intent_id: str
    goal_id: str = Field(default="", max_length=64)

    effect_hash: str = Field(max_length=64)
    decision: Literal["approved", "denied"] = "approved"

    # Where the yes came from. Only a person produces either; there is no path
    # from a model to this field, and a test walks for one.
    #
    #   `user`                  they were shown what was prepared and pressed yes.
    #   `explicit_user_command` they asked for this act in their own words, and
    #                           the words are in `commanded_words` because code
    #                           checked them against what was actually said.
    #
    # The distinction is not decoration. An approval answers a question ORA
    # asked; a command is a decision the person had already made before ORA
    # said anything, and asking them to confirm it is asking them to agree
    # with themselves.
    source: Literal["user", "explicit_user_command"] = "user"
    # Their own words, when that is what carried the authority. Bounded, and
    # only ever the fragment that was checked — an audit needs to see what the
    # authority was read out of, not the whole conversation.
    commanded_words: str = Field(default="", max_length=200)
    # What they were shown when they said it, so an audit can reconstruct the
    # question rather than only the answer.
    approved_what: str = Field(default="", max_length=300)

    approved_at: str = Field(default_factory=now_iso)
    expires_at: Optional[str] = None
    used_at: Optional[str] = None


class ExecutionReceipt(BaseModel):
    """
    What a provider said when it was asked to do something.

    A receipt, not a result: it records that a request was made and how it was
    answered. Whether the world changed is a separate question, asked by
    reading the world back.
    """

    id: str = Field(default_factory=lambda: _id("rcp"))
    owner_id: str
    goal_id: str = Field(default="", max_length=64)
    action_intent_id: str
    idempotency_key: str = Field(default="", max_length=64)

    capability: str = Field(default="", max_length=60)
    provider: str = Field(default="", max_length=60)
    # The provider's own handle for what it made. Safe to keep and safe to
    # show a support engineer; never a token, never a URL with a secret in it.
    external_ref: str = Field(default="", max_length=200)

    provider_status: ProviderStatus = "unknown"
    # A type name, never a raw error.
    error_type: str = Field(default="", max_length=80)
    retryable: bool = False

    requested_at: str = Field(default_factory=now_iso)
    answered_at: Optional[str] = None
    result_refs: List[str] = Field(default_factory=list, max_length=8)
    authority_basis: str = Field(default="", max_length=64)

    def for_ai(self) -> Dict[str, Any]:
        return {
            "what_the_service_said": self.provider_status,
            "it_gave_us_a_handle": bool(self.external_ref),
            "when": self.requested_at,
            "problem": self.error_type or None,
            # Said plainly, because this is the exact place the mistake gets
            # made: a service accepting a request is not the world changing.
            "note": (
                "Accettato non vuol dire avvenuto: va guardato com'è andata."
                if self.provider_status == "accepted" else None
            ),
        }


class AutonomousGoal(BaseModel):
    """
    An outcome ORA is trying to bring about.

        A GOAL IS AN OUTCOME, NOT A TASK.

    `success_criteria` is what makes this checkable rather than aspirational,
    and `stop_conditions` is what stops a goal from outliving its reason — a
    goal that cannot say when it would give up is one that never will.

    `requires_user_input` and `requires_user_authority` are separate fields
    for the same reason they are separate concepts: a goal blocked on
    something only the person knows is in a different situation from one
    blocked on something ORA is not allowed to do.
    """

    id: str = Field(default_factory=lambda: _id("gol"))
    owner_id: str

    status: GoalStatus = "proposed"
    origin: GoalOrigin = "agent_initiated"

    # An outcome, in words a person would recognise as being about their life.
    objective: str = Field(min_length=1, max_length=280)
    desired_outcome: str = Field(min_length=1, max_length=400)
    why_now: str = Field(default="", max_length=400)

    # How anybody could tell it worked.
    success_criteria: List[str] = Field(default_factory=list, max_length=6)
    # And when to give up rather than keep going.
    stop_conditions: List[str] = Field(default_factory=list, max_length=6)

    # What this grew out of. Handles, never content.
    source_kind: str = Field(default="", max_length=40)
    source_refs: List[str] = Field(default_factory=list, max_length=8)
    opportunity_id: str = Field(default="", max_length=64)

    requires_user_input: bool = False
    requires_user_authority: bool = False

    valid_until: Optional[str] = None
    decision_provenance: Literal["model", "user", "code"] = "model"
    # Why it ended up where it ended up, in whoever's words decided.
    rationale: str = Field(default="", max_length=300)

    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    completed_at: Optional[str] = None

    def touch(self) -> None:
        self.updated_at = now_iso()

    @property
    def is_open(self) -> bool:
        return self.status in ("proposed", "active", "waiting")

    def for_human(self) -> Dict[str, Any]:
        """
        What a person may see: an outcome and a state of affairs.

            NEVER EXPOSE IMPLEMENTATION STATE WHEN A HUMAN STATE EXISTS.

        No step counts, no plan status, no authority level. Somebody wants to
        know whether the thing is handled, not how many stages it has.
        """
        return {
            "id": self.id,
            "what": self.objective,
            "outcome": self.desired_outcome,
            "why_now": self.why_now or None,
        }

    def for_ai(self) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "desired_outcome": self.desired_outcome,
            "why_now": self.why_now or None,
            "success_criteria": self.success_criteria,
            "stop_conditions": self.stop_conditions,
            "status": self.status,
        }


class ActionStep(BaseModel):
    """
    One move in a plan, said in terms of what it is for.

    `capability_needed` is the important field: the model says it needs to
    read a calendar, not which client to call. Code resolves that to
    something that exists and that this person has allowed — and when nothing
    matches, the model is told so it can find another way rather than
    pretending.
    """

    id: str = Field(default_factory=lambda: _id("stp"))
    ordinal: int = 0

    intent: str = Field(min_length=1, max_length=280)
    step_type: StepType
    status: StepStatus = "pending"

    # What the model says it needs to be able to do. Never a function name.
    capability_needed: str = Field(default="", max_length=60)

    input_refs: List[str] = Field(default_factory=list, max_length=8)
    expected_result: str = Field(default="", max_length=300)
    actual_result_ref: str = Field(default="", max_length=64)

    # Only meaningful for steps that touch the world.
    external_effect: bool = False
    reversibility: Reversibility = "easily"
    authority_requirement: str = Field(default="", max_length=60)

    # V3.9 Sprint 3 — what kind of change this would be, and whether it lands
    # on anybody else. Declared by the plan, because the plan is where the
    # model says what it means to do; code never infers either of them, and a
    # step that did not say it reaches somebody cannot acquire an attendee
    # further down.
    effect_type: EffectType = "create"
    effect_target: str = Field(default="", max_length=200)
    reaches_somebody_else: bool = False
    # The values the effect would be carried out with. Bounded, and never a
    # place for anything a token could hide in.
    parameters: Dict[str, Any] = Field(default_factory=dict)

    # Set when a step is blocked on a person, with which of the two it needs.
    asks: str = Field(default="", max_length=300)
    ask_kind: Optional[AskKind] = None

    attempts: int = 0
    note: str = Field(default="", max_length=200)

    def for_ai(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ordinal": self.ordinal,
            "intent": self.intent,
            "type": self.step_type,
            "status": self.status,
            "capability_needed": self.capability_needed or None,
            "expected_result": self.expected_result or None,
            "external_effect": self.external_effect,
            "what_kind_of_change": self.effect_type,
            "reaches_somebody_else": self.reaches_somebody_else,
            "reversibility": self.reversibility,
            "note": self.note or None,
        }


class ActionPlan(BaseModel):
    """
    How ORA currently intends to reach a goal. Expected to change.

    `assumptions` matters more than it looks: a plan built on something that
    turns out to be false should be replanned rather than pushed through, and
    a plan that never wrote down what it assumed cannot notice.
    """

    id: str = Field(default_factory=lambda: _id("pln"))
    goal_id: str
    owner_id: str

    status: PlanStatus = "draft"
    plan_summary: str = Field(default="", max_length=400)
    steps: List[ActionStep] = Field(default_factory=list, max_length=12)
    current_step: int = 0

    assumptions: List[str] = Field(default_factory=list, max_length=6)
    known_constraints: List[str] = Field(default_factory=list, max_length=6)
    blocking_questions: List[str] = Field(default_factory=list, max_length=4)
    expected_outcome: str = Field(default="", max_length=400)

    # How many times this plan has been reconsidered. A bound, not a metric:
    # a plan that keeps being rewritten is a plan that is not working.
    revisions: int = 0

    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def step(self, step_id: str) -> Optional[ActionStep]:
        return next((s for s in self.steps if s.id == step_id), None)

    def next_actionable(self) -> Optional[ActionStep]:
        """
        The first step still waiting to be tried.

        Only `pending`. A step that failed has already been through the
        reconsideration that decided what to do about it — picking it up
        again would be the loop arguing with a judgement that was already
        made, and retrying something the model has routed around.
        """
        for step in sorted(self.steps, key=lambda s: s.ordinal):
            if step.status == "pending":
                return step
        return None

    def for_ai(self) -> Dict[str, Any]:
        return {
            "plan_summary": self.plan_summary,
            "steps": [s.for_ai() for s in self.steps],
            "assumptions": self.assumptions,
            "known_constraints": self.known_constraints,
            "expected_outcome": self.expected_outcome,
            "revisions": self.revisions,
        }


class ActionIntent(BaseModel):
    """
    A declaration of what is about to happen in the world, written before it does.

    Every executable step produces one, and it carries an `idempotency_key`
    derived from what the effect *is* rather than when it was attempted — so a
    retry of the same intent is recognisably the same intent, and cannot
    produce the effect twice.

    Parameters are references, never values: nothing here holds a token, an
    address book, or the contents of anything.
    """

    id: str = Field(default_factory=lambda: _id("int"))
    owner_id: str
    goal_id: str
    step_id: str

    capability: str = Field(max_length=60)
    # What would change in the world, in one sentence.
    effect_summary: str = Field(default="", max_length=300)
    target_ref: str = Field(default="", max_length=120)
    parameter_refs: List[str] = Field(default_factory=list, max_length=8)

    authority_required: str = Field(default="", max_length=60)
    expected_effect: str = Field(default="", max_length=300)
    reversibility: Reversibility = "easily"
    external_effect: bool = True

    # Where this effect has got to. `executed` means something was done;
    # `verified` means the world was afterwards found to have changed. They
    # are two states because they are two facts, and a system that collapses
    # them tells people their booking is confirmed when a form was submitted.
    status: IntentStatus = "planned"
    executed_at: Optional[str] = None
    verified_at: Optional[str] = None

    # V3.9 Sprint 3 — what would actually change, in checkable terms. Absent
    # on an intent nobody has assessed yet, which is why it has a default and
    # why nothing executes on the default.
    effect: ActionEffect = Field(default_factory=ActionEffect)
    # The parameters the effect would be carried out with. Values, not refs,
    # because a calendar entry has to have a time in it — bounded, and never
    # holding anything a token could hide in.
    parameters: Dict[str, Any] = Field(default_factory=dict)

    created_at: str = Field(default_factory=now_iso)

    @model_validator(mode="after")
    def _parameters_carry_no_credentials(self) -> "ActionIntent":
        """
        Values, yes. Credentials, never.

        A calendar entry needs a time in it, so the older rule — an intent
        carries only references — stopped being possible the moment anything
        real was wired. What replaces it is narrower and stronger: the field
        exists, and a key that looks like a credential cannot survive being
        put in it. Dropped rather than rejected, because an intent that fails
        to build is an outage and a stripped one is a working action minus
        something that had no business being there.

        Bounded as well as filtered. An unbounded dictionary reaches a prompt
        eventually, and a prompt is a place things get logged.
        """
        clean: Dict[str, Any] = {}
        for key, value in list((self.parameters or {}).items())[:12]:
            name = str(key)[:60]
            if _SECRETISH.search(name):
                continue
            if isinstance(value, (dict, list, tuple, set)):
                continue
            clean[name] = value if isinstance(value, (int, float, bool)) else str(value)[:300]
        self.parameters = clean
        return self

    @property
    def idempotency_key(self) -> str:
        """
        The same effect attempted twice is one effect.

        Built from owner, goal, step and capability — deliberately not from
        the clock, so a retry after a timeout matches the attempt that may
        already have gone through.
        """
        raw = "|".join(
            [self.owner_id, self.goal_id, self.step_id, self.capability, self.target_ref]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    @property
    def effect_hash(self) -> str:
        """
        What is about to happen, as something an approval can be bound to.

        Distinct from `idempotency_key`, and the difference is the whole
        point: the key says "this is the same attempt", this says "this is the
        same act". An intent rewritten with a new target keeps its key and
        loses its hash, so the yes it was given no longer applies.
        """
        raw = "|".join([
            self.capability,
            self.effect.fingerprint(),
            self.target_ref.strip().lower(),
            _stable(self.parameters),
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def for_human(self) -> Dict[str, Any]:
        """What somebody is being asked to agree to. One sentence, no handles."""
        return {
            "about_to": self.effect.for_human() or self.effect_summary,
            "can_be_undone": self.effect.reversibility in ("easily", "with_effort"),
        }


class AuthorityAssessment(BaseModel):
    """
    What the model thinks this action means, and what code decided about it.

        AI MAY RECOMMEND AUTONOMY. CODE MAY DENY IT.
        AI MAY NOT OVERRIDE POLICY.

    Both halves are kept because they can disagree, and when they do the
    disagreement is the interesting part: a model that judged something
    routine and a policy that refused it is exactly what an audit needs to
    see.
    """

    step_id: str = ""
    capability: str = Field(default="", max_length=60)

    # The model's reading of what this action is.
    model_outcome: AuthorityOutcome = "ask_before_execution"
    reasoning: str = Field(default="", max_length=400)
    reversibility: Reversibility = "easily"
    # Named dimensions, not a score. Each is a fact about the kind of effect.
    financial_effect: bool = False
    external_communication: bool = False
    third_party_impact: bool = False
    privacy_disclosure: bool = False
    legal_effect: bool = False
    security_effect: bool = False

    # What actually applies, after code has had its say.
    effective_outcome: AuthorityOutcome = "ask_before_execution"
    narrowed_by_code: bool = False
    code_reason: str = Field(default="", max_length=200)

    def public(self) -> Dict[str, Any]:
        return {
            "capability": self.capability or None,
            "model_said": self.model_outcome,
            "effective": self.effective_outcome,
            "narrowed_by_code": self.narrowed_by_code,
            "why": self.code_reason or self.reasoning or None,
        }


class ExecutionResult(BaseModel):
    """
    What happened when a step ran. Never a raw exception.

    `observation` is what the reasoning gets to see: a description, in words,
    of what the world said back. A stack trace in a prompt is a way of asking
    a model to debug your code.
    """

    step_id: str = ""
    status: ExecutionStatus = "unavailable"
    observation: str = Field(default="", max_length=600)
    result_refs: List[str] = Field(default_factory=list, max_length=8)
    # A type name, safe to show and safe to log.
    error_type: str = Field(default="", max_length=80)
    retryable: bool = False
    idempotency_key: str = Field(default="", max_length=64)
    at: str = Field(default_factory=now_iso)

    # V3.9 Sprint 2 — where this came from, and what it produced.
    #
    # `provenance` is not optional in spirit even though it has a default:
    # the default says `simulated`, which is the safe thing to be wrong
    # about. A result that forgot to say where it came from is treated as
    # having come from nowhere, and nothing real is concluded from it.
    provenance: ResultProvenance = Field(default_factory=ResultProvenance)
    evidence_refs: List[str] = Field(default_factory=list, max_length=12)
    # A handle to the full result, held elsewhere. The model is given the
    # handle and a sentence, never the whole thing.
    data_ref: str = Field(default="", max_length=120)

    @property
    def is_real(self) -> bool:
        return self.provenance.is_real


class GoalVerification(BaseModel):
    """
    Whether the outcome is actually true.

        A TOOL RETURNING SUCCESS IS NOT THE GOAL BEING ACHIEVED.

    This exists because the alternative — treating a successful call as a
    finished goal — is how a system ends up telling somebody their booking is
    confirmed when all that happened is a form was submitted.
    """

    goal_id: str = ""
    outcome: VerificationOutcome = "uncertain"
    reasoning: str = Field(default="", max_length=400)
    what_is_missing: str = Field(default="", max_length=300)
    # When the answer depends on something that has not happened yet.
    revisit_in_hours: Optional[int] = None
    at: str = Field(default_factory=now_iso)


class AutonomyGrant(BaseModel):
    """
    Permission to act without asking each time, for one kind of thing.

        AI DOES NOT INVENT GRANTS. ONLY A PERSON OR CODE CREATES AUTHORITY.

    Distinct from the permission registry, which answers "may ORA touch this
    data at all". This answers the narrower question: "may ORA do it without
    checking with me first". Scoped, revocable, and finite by default —
    an authority granted once in a good mood should not last for ever.
    """

    id: str = Field(default_factory=lambda: _id("grt"))
    owner_id: str
    capability: str = Field(max_length=60)

    # Only a person or code may create one. Never the model.
    granted_by: Literal["user", "code"] = "user"
    # In the person's words, so it can be shown back to them.
    scope_note: str = Field(default="", max_length=200)

    # V3.9 Sprint 3 — what the permission actually covers.
    #
    #     A GRANT IS NOT A BLANK CHEQUE.
    #
    # "Puoi aggiungere eventi al mio calendario" is not "puoi invitare
    # persone" and not "puoi cancellare quello che c'è". Without a scope, a
    # capability name is the coarsest possible permission and the first
    # surprise is somebody's colleague receiving an invitation.
    #
    # Read only by code. The model may say what an action *is*; whether a
    # particular permission covers it is arithmetic, and arithmetic is not
    # something to ask an opinion about.
    effect_scope: List[EffectType] = Field(default_factory=list, max_length=7)
    # Flags that must be FALSE on the effect for this grant to apply. Named
    # rather than scored, and absent means "not allowed" — the direction that
    # fails closed.
    allows_external_party: bool = False
    allows_financial: bool = False
    allows_public: bool = False
    allows_destructive: bool = False
    # Free constraints the matcher understands, e.g. a target prefix.
    constraints: Dict[str, Any] = Field(default_factory=dict)
    # The sentence the person actually agreed to, shown back on request.
    human_summary: str = Field(default="", max_length=200)
    source: Literal["explicit_grant", "code_policy"] = "explicit_grant"

    active: bool = True
    created_at: str = Field(default_factory=now_iso)
    expires_at: Optional[datetime] = None
    revoked_at: Optional[str] = None

    def public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "capability": self.capability,
            "scope": self.human_summary or self.scope_note or None,
            "active": self.active,
            "granted_by": self.granted_by,
        }


class AutonomyPolicy(BaseModel):
    """
    How much ORA may do on its own, before any particular grant.

    Conservative by default, and `chosen_by_user` says whether that default
    is a decision or just what nobody has changed.
    """

    owner_id: str
    mode: AutonomyMode = "prepare"
    chosen_by_user: bool = False
    updated_at: str = Field(default_factory=now_iso)

    def for_ai(self) -> Dict[str, Any]:
        meaning = {
            "observe": "Vuole che ORA capisca e riferisca, senza preparare nulla.",
            "prepare": "Vuole che ORA prepari tutto da sé, e chieda prima di agire.",
            "act_within_grants": (
                "Vuole che ORA faccia da sé quello che ha già autorizzato."
            ),
        }
        return {
            "how_much_they_want_ora_to_do": meaning.get(self.mode, meaning["prepare"]),
            "they_chose_this": self.chosen_by_user,
        }


class AgentRun(BaseModel):
    """
    One pass of the loop, and the bounds it ran under.

        NO INFINITE AGENT LOOP.

    A cognitive loop with no ceiling is a bill with no ceiling. This records
    what a run did so a circuit breaker has something to break on.
    """

    id: str = Field(default_factory=lambda: _id("run"))
    owner_id: str
    goal_id: str = ""

    iterations: int = 0
    model_calls: int = 0
    steps_executed: int = 0
    replans: int = 0
    stopped_because: str = Field(default="", max_length=120)
    at: str = Field(default_factory=now_iso)

# ---------------------------------------------------------------------------
# V3.9 Sprint 2 close-out — how useful it is to make this visible.
#
#     SILENCE IS A VALID DECISION, NOT A DEFAULT PERSONALITY.
#     DO NOT CONFUSE AVOIDING INTERRUPTION WITH HIDING USEFUL WORK.
#
# V3.8 answered "should ORA interrupt". This answers a different question that
# was quietly collapsed into it: "is it worth this person knowing". They come
# apart in the case that matters most — ORA did something genuinely useful and
# there is no reason on earth to buzz a phone about it. Under one question
# that work disappears; under two it shows up quietly on a screen the person
# looks at when they choose to.
#
# This is not a delivery mode and never becomes one. It says how much the work
# is worth showing; V3.8 still owns when, and through what.
# ---------------------------------------------------------------------------

OutcomeVisibility = Literal[
    # Nothing worth saying. The ordinary answer, and it must stay comfortable.
    "silent",
    # Real work worth seeing, not worth a moment of anybody's attention.
    "quiet_update",
    # They should know the result; nothing is being asked of them.
    "inform_user",
    # Something is needed that only they know or only they may allow.
    "ask_user",
    # Without them this cannot go on, or the result matters enough to say so.
    "requires_attention",
]


class VisibilityDecision(BaseModel):
    """
    Whether the work ORA just did is worth showing, and in what words.

    `headline` is the whole user-facing payload — one sentence a person would
    say. There is deliberately nowhere here to put a step count, a capability
    name or a confidence: a surface cannot show what it was never given.

    `refs` is what makes an update provable. Every visible line points back at
    the goal and at the journal or evidence it came from, and code refuses to
    show one that points at nothing.
    """

    goal_id: str = ""
    outcome: OutcomeVisibility = "silent"
    # Why, in the deciding voice. Never shown to anybody.
    reasoning: str = Field(default="", max_length=400)

    # The one sentence. Empty when silent, and required when not.
    headline: str = Field(default="", max_length=200)

    # Handles back to what actually happened. Never content.
    refs: List[str] = Field(default_factory=list, max_length=8)
    # What this update is *about*, so the same thing said twice is recognised
    # as the same thing rather than as news.
    fingerprint: str = Field(default="", max_length=64)

    decided_by: Literal["model", "code"] = "model"
    # Set when code overruled — always towards saying less.
    quietened_by_code: str = Field(default="", max_length=120)
    at: str = Field(default_factory=now_iso)

    @property
    def is_visible(self) -> bool:
        return self.outcome != "silent"

    @property
    def wants_a_person(self) -> bool:
        """Whether this is asking for something, as opposed to reporting."""
        return self.outcome in ("ask_user", "requires_attention")

    def for_human(self) -> Dict[str, Any]:
        """The sentence, and nothing that would betray how it was reached."""
        return {"says": self.headline, "needs_you": self.wants_a_person}

# ---------------------------------------------------------------------------
# V3.9 Sprint 2 close-out — a need for the person, which is not a notification.
#
#     ORA MAY NEED THE USER WITHOUT WAITING FOR THE USER TO RETURN.
#     A NEED FOR THE USER IS NOT AUTOMATICALLY A PUSH.
#
# Until now an agent that got stuck could only be *seen*, by somebody who
# happened to open the app. That is fine for "I found something useful" and
# wrong for "everything is ready and I need one word from you" — a person who
# does not come back never learns that ORA is waiting on them, and the agent
# that manages the work ends up managed by the user's habits.
#
# The obvious shortcut was to invent an Opportunity so the existing delivery
# path would carry it. It is three lines and it is a lie: an opportunity is
# something ORA noticed about a life, and being stuck is not that. So a need
# is its own thing, and delivery learned to weigh two kinds of subject.
#
# What it deliberately is NOT: a channel, a notification, or a promise that
# anybody will be interrupted. It says somebody may be needed. V3.8 still
# decides whether, when and how — and may decide never.
# ---------------------------------------------------------------------------

# Why the person is being brought in. Domain-neutral by construction: nothing
# here names a document, a booking or an inbox, because the day it does this
# becomes a list of situations somebody thought of in advance.
NeedKind = Literal[
    "progress_update",    # ORA is getting on with it, and that is worth seeing
    "useful_result",      # something was found or done that helps
    "needs_information",  # only they know it
    "needs_authority",    # only they may allow it
    "important_outcome",  # it is finished, or it stopped, and that matters
]

# `satisfied` is the only one that means the person dealt with it. The others
# mean nobody has to any more — which is a different thing, and the difference
# is what stops a cancelled goal from looking like an answered question.
NeedStatus = Literal["open", "satisfied", "cancelled", "expired"]

# What a reply would have to be. Absent when nothing is being asked.
ResponseKind = Literal["information", "authority"]


class CommunicationNeed(BaseModel):
    """
    Something ORA may need to reach a person about, and what it is waiting on.

    The lifecycle is the point. A need is `open` from the moment the agent is
    blocked until somebody answers, the agent stops needing it, or it goes
    stale — and specifically *not* when a notification is sent, delivered, or
    opened. Those are things that happened to a message; this is a thing that
    is true about the work.
    """

    id: str = Field(default_factory=lambda: _id("ned"))
    owner_id: str
    goal_id: str

    kind: NeedKind
    # The sentence a person would read. Never a status, never a step.
    summary: str = Field(min_length=1, max_length=200)
    # Why they are being brought in, for the judgement that decides whether to
    # interrupt. Specific, or it is not worth anybody's attention.
    reason: str = Field(default="", max_length=400)

    # Handles back to the work: goal, journal, evidence. Never content.
    source_refs: List[str] = Field(default_factory=list, max_length=8)
    # The visibility judgement this grew out of, kept so the two can be read
    # together afterwards.
    visibility: OutcomeVisibility = "inform_user"

    status: NeedStatus = "open"
    requires_response: bool = False
    response_kind: Optional[ResponseKind] = None

    # What ORA had already done before it got stuck. The difference between
    # «serve il tuo via libera» and «ho preparato tutto e serve il tuo via
    # libera», which is the difference between a demand and a report.
    work_already_done: List[str] = Field(default_factory=list, max_length=6)
    what_is_missing: str = Field(default="", max_length=300)

    valid_until: Optional[str] = None
    # Same subject, recognised again. Built from the goal and what is blocked,
    # never from the wording — a model asked twice phrases it twice.
    fingerprint: str = Field(default="", max_length=64)

    provenance: Literal["model", "user", "code"] = "model"
    resolution: str = Field(default="", max_length=200)

    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    resolved_at: Optional[str] = None

    def touch(self) -> None:
        self.updated_at = now_iso()

    @property
    def is_open(self) -> bool:
        return self.status == "open"

    def for_human(self) -> Dict[str, Any]:
        """
        What a person may see. One sentence and whether they are needed.

        No kind, no status, no refs, no goal id: a surface cannot show what it
        was never given, and every one of those is implementation state
        wearing a friendly name.
        """
        return {"says": self.summary, "needs_you": self.requires_response}

    def as_subject(self) -> Dict[str, Any]:
        """
        The need as delivery sees it: facts about a thing that might be worth
        saying, with nothing about how the work was done.

        Shaped to the names the delivery context already reads, so no branch
        is needed on the other side.
        """
        return {
            "source_type": "agent_need",
            "id": self.id,
            "owner_id": self.owner_id,
            "goal_id": self.goal_id,
            "semantic_summary": self.summary,
            "why_it_matters": self.reason,
            "why_now": self.what_is_missing,
            "created_at": self.created_at,
            "valid_until": self.valid_until,
            "requires_clarification": self.requires_response,
            "requires_response": self.requires_response,
            "work_already_done": list(self.work_already_done),
            "what_is_missing": self.what_is_missing,
            "source_refs": list(self.source_refs),
            "status": "active" if self.is_open else self.status,
        }
