"""AI decision contract — domain-neutral. No domain field dictionaries."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator
from context_graph.models import ContextEdgeUpdate
from situations.models import SituationUpdate

ResponseMode = Literal[
    "answer", "ask", "tool", "act", "context", "research", "compare", "finish"
]
ReasoningStatus = Literal[
    "enough_information",
    "needs_user_input",
    "needs_context",
    "needs_tool",
    "needs_research",
    "needs_comparison",
    "ready_to_act",
]
GroundingKind = Literal[
    "USER_STATED",
    "PERSONAL_CONTEXT",
    "TOOL_OBSERVATION",
    "MODEL_KNOWLEDGE",
    "INFERENCE",
]

UncertaintyStrategy = Literal["retrieve", "ask", "assume", "defer"]


class MissingInformation(BaseModel):
    """Bounded AI-owned information need; never a domain slot."""

    ref: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=240)
    purpose: Optional[str] = Field(default=None, max_length=240)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    blocking: bool = False
    strategy: UncertaintyStrategy = "defer"
    context_query: Optional[str] = Field(default=None, max_length=400)
    sensitivity: Literal["normal", "sensitive", "high"] = "normal"
    # V3.2 — why this matters *to the next step*, which is the only thing that
    # decides whether a person is asked. `required` means the step cannot be
    # taken without it; `useful` would improve the answer and waits; `optional`
    # is not needed now. Only `required` may ever become a question, however
    # interesting the rest would be.
    # Absent means the model did not say. That is different from saying
    # "useful": an unstated necessity falls back to how the item was marked
    # (a blocking ask was, in the only sense that matters, required), while an
    # explicit "useful" is a decision and is honoured as one.
    necessity: Optional[Literal["required", "useful", "optional"]] = None
    # What a person would call it — "reddito netto mensile", not "income_net".
    # Used to compose a question that reads like a sentence.
    label: Optional[str] = Field(default=None, max_length=160)
    # The step this blocks, so "is it blocking?" has an answer that is about
    # the work rather than about the model's comfort.
    blocks_step: Optional[str] = Field(default=None, max_length=200)


class Ambiguity(BaseModel):
    ref: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=240)
    blocking: bool = False


class DecisionAssumption(BaseModel):
    """A reversible proposition used for this decision, never a fact or Memory."""

    ref: str = Field(min_length=1, max_length=120)
    statement: str = Field(min_length=1, max_length=300)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reversible: bool = True
    consequential: bool = False
    source_refs: List[str] = Field(default_factory=list, max_length=6)


class UncertaintyState(BaseModel):
    """Operational epistemic state; contains no private chain-of-thought."""

    level: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_information: List[MissingInformation] = Field(default_factory=list, max_length=6)
    ambiguities: List[Ambiguity] = Field(default_factory=list, max_length=4)
    assumptions: List[DecisionAssumption] = Field(default_factory=list, max_length=4)
    blocking: bool = False
    operational_reason: Optional[str] = Field(default=None, max_length=240)


class ContextNeed(BaseModel):
    """AI-owned information need; source hints never become mandatory routing."""

    query: str = Field(min_length=1, max_length=400)
    purpose: Optional[str] = Field(default=None, max_length=240)
    desired_evidence: List[str] = Field(default_factory=list, max_length=6)
    temporal_scope: Optional[str] = Field(default=None, max_length=120)
    source_hints: List[str] = Field(default_factory=list, max_length=5)
    max_items: int = Field(default=6, ge=1, le=8)


class ResearchNeed(BaseModel):
    """
    The reasoning reaching the edge of what ORA can know from inside.

    `context` is the same shape of statement about ORA's own stores — what it
    holds about this person and has not looked at yet. This is its sibling for
    the world: something that is not in any of ORA's stores because it is not
    about the person at all, and changes without asking.

    Declaring it is the whole of the "should I go and look?" decision, and it
    belongs here because it belongs to the model. Nothing derives it from a
    plan type, a document type, an area of life or a word in the message.
    """

    question: str = Field(min_length=1, max_length=400)
    purpose: Optional[str] = Field(default=None, max_length=300)
    # What is already established, so nothing goes looking for what ORA has
    # been told. Written by the model from what it can see of this person.
    already_known: List[str] = Field(default_factory=list, max_length=12)


class ComparisonAlternative(BaseModel):
    """One of the things being chosen between, as the reasoning has it."""

    name: str = Field(min_length=1, max_length=200)
    summary: Optional[str] = Field(default=None, max_length=400)
    # What is known about it and where each piece came from. A research source
    # id, or nothing when the person said it themselves.
    attributes: List[Dict[str, Any]] = Field(default_factory=list, max_length=20)
    research_run_id: Optional[str] = None


class ComparisonNeed(BaseModel):
    """
    The reasoning saying this is a choice rather than a question.

    Its siblings: `context_need` for what ORA holds about this person,
    `research_need` for what the world knows. This is for the step after both
    — when the evidence is in and something has to be decided between.

    Nothing infers it. Two results are not a comparison, and a question with
    one answer is not a decision: only the reasoning can tell that somebody is
    choosing.
    """

    decision: str = Field(min_length=1, max_length=400)
    purpose: Optional[str] = Field(default=None, max_length=300)
    alternatives: List[ComparisonAlternative] = Field(default_factory=list, max_length=8)
    # What is established, so nothing is asked twice.
    already_known: List[str] = Field(default_factory=list, max_length=16)
    # Evidence already gathered that this decision rests on.
    research_run_ids: List[str] = Field(default_factory=list, max_length=8)


class ToolCall(BaseModel):
    """Capability request — prefer capability over provider brands."""

    name: Optional[str] = None  # legacy alias
    capability: Optional[str] = None
    operation: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _sync_capability(self) -> "ToolCall":
        cap = (self.capability or self.name or "").strip()
        if cap:
            self.capability = cap
            self.name = cap
        return self

    @property
    def resolved_capability(self) -> str:
        return (self.capability or self.name or "").strip()


class StateUpdate(BaseModel):
    """Semantic state patch — not domain slot dictionaries."""

    path: str  # e.g. active_goal.summary | current_facts.location | note
    value: Any = None
    op: Literal["set", "clear", "append"] = "set"


class MemoryCandidate(BaseModel):
    """AI proposal; deterministic governance owns every durable mutation."""

    operation: Literal["propose", "correct", "supersede", "forget"] = "propose"
    summary: Optional[str] = Field(default=None, max_length=600)
    fact_summary: Optional[str] = Field(default=None, max_length=600)  # legacy alias
    kind: Optional[str] = Field(default=None, max_length=80)
    identity_key: Optional[str] = Field(default=None, max_length=120)
    value: Any = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    authority: Literal[
        "user_confirmed", "user_stated", "document", "structured", "inferred", "device"
    ] = "inferred"
    epistemic_status: Literal["tentative", "asserted", "confirmed", "inferred"] = (
        "inferred"
    )
    provenance: List[str] = Field(default_factory=list, max_length=8)
    evidence_refs: List[str] = Field(default_factory=list, max_length=8)
    permanence: Literal["temporary", "indefinite", "durable", "unknown"] = "unknown"
    starts_at: Optional[str] = Field(default=None, max_length=80)
    ends_at: Optional[str] = Field(default=None, max_length=80)
    recurrence: Optional[str] = Field(default=None, max_length=120)
    sensitivity: Literal["normal", "sensitive", "high"] = "normal"
    existing_memory_ref: Optional[str] = Field(default=None, max_length=120)
    supersedes_refs: List[str] = Field(default_factory=list, max_length=6)
    coexists_with_refs: List[str] = Field(default_factory=list, max_length=6)
    reason_for_future_utility: Optional[str] = Field(default=None, max_length=300)
    requires_confirmation: bool = False
    user_authorized: bool = False

    @model_validator(mode="after")
    def _normalize_summary(self) -> "MemoryCandidate":
        text = (self.summary or self.fact_summary or "").strip()
        if not text:
            raise ValueError("memory summary required")
        self.summary = text
        self.fact_summary = text
        self.provenance = [
            str(x)[:160] for x in dict.fromkeys(self.provenance or self.evidence_refs)
        ][:8]
        self.evidence_refs = [str(x)[:160] for x in self.evidence_refs][:8]
        self.supersedes_refs = [str(x)[:120] for x in self.supersedes_refs][:6]
        self.coexists_with_refs = [str(x)[:120] for x in self.coexists_with_refs][:6]
        try:
            if len(json.dumps(self.value, ensure_ascii=False, default=str)) > 2000:
                raise ValueError("memory value too large")
        except TypeError as exc:
            raise ValueError("memory value is not serializable") from exc
        return self


class ActiveGoal(BaseModel):
    summary: str = ""
    desired_outcome: str = ""
    status: Literal["active", "paused", "done", "abandoned"] = "active"


class CognitiveDecision(BaseModel):
    response_mode: ResponseMode = "answer"
    user_intent_summary: str = ""
    active_goal_summary: Optional[str] = None
    reasoning_status: ReasoningStatus = "enough_information"
    message_to_user: Optional[str] = None
    question: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    context_query: Optional[str] = None
    context_need: Optional[ContextNeed] = None
    research_need: Optional[ResearchNeed] = None
    comparison_need: Optional[ComparisonNeed] = None
    state_updates: List[StateUpdate] = Field(default_factory=list)
    memory_candidates: List[MemoryCandidate] = Field(default_factory=list)
    confidence: Optional[float] = None
    # Optional epistemic self-report (not shown to user)
    claim_grounding: Optional[GroundingKind] = None
    situation_update: Optional[SituationUpdate] = None
    uncertainty: Optional[UncertaintyState] = None
    context_graph_updates: List[ContextEdgeUpdate] = Field(
        default_factory=list, max_length=2
    )
    # V3.2 — where this person actually is, in structure rather than prose:
    # the milestones of the goal, which are already behind them, and on what
    # basis ORA believes so. Validated by `guidance.GoalState`; an unusable
    # reconstruction leaves the previous one standing rather than replacing it.
    goal_state: Optional[Dict[str, Any]] = None


class ContextFact(BaseModel):
    """Personal context item with provenance — never flatten authority."""

    statement: str = ""
    fact: str = ""
    source: str = "unknown"
    authority: str = "unknown"
    status: str = "known"
    timestamp: Optional[str] = None
    ref: str = ""
    grounding: Optional[str] = None
    temporal_scope: Optional[str] = None
    confidence: Optional[float] = None
    sensitivity: str = "personal"
    provenance: List[str] = Field(default_factory=list)


class Observation(BaseModel):
    kind: Literal["tool", "context", "research", "comparison", "error", "system"] = "system"
    name: str = ""
    status: str = "ok"
    payload: Dict[str, Any] = Field(default_factory=dict)
    provenance: List[str] = Field(default_factory=list)


class CognitiveTurnResult(BaseModel):
    ok: bool = True
    mode: ResponseMode = "answer"
    ora_text: str = ""
    question: Optional[str] = None
    session_id: str = ""
    active_goal: Optional[ActiveGoal] = None
    memory_candidates: List[MemoryCandidate] = Field(default_factory=list)
    trace: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    ai_calls: int = 0
    tool_calls: int = 0
    context_calls: int = 0
    external_queries: int = 0
    elapsed_ms: int = 0
    sources: List[Dict[str, str]] = Field(default_factory=list)
    working_hint: Optional[str] = None
    client_actions: List[Dict[str, Any]] = Field(default_factory=list)
    situation: Optional[Dict[str, Any]] = None
    # V3.1 — when this turn stopped because the reasoning cannot proceed
    # without the person, this carries what a persistent blocker needs: the
    # question, why it is needed, and the AI's own opaque handles for the
    # information it was missing. Absent on every other kind of turn, including
    # an ordinary clarification the reasoning did not call blocking.
    blocking_ask: Optional[Dict[str, Any]] = None
