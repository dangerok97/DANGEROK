"""AI decision contract — domain-neutral. No domain field dictionaries."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

ResponseMode = Literal["answer", "ask", "tool", "act", "context", "finish"]
ReasoningStatus = Literal[
    "enough_information",
    "needs_user_input",
    "needs_context",
    "needs_tool",
    "ready_to_act",
]
GroundingKind = Literal[
    "USER_STATED",
    "PERSONAL_CONTEXT",
    "TOOL_OBSERVATION",
    "MODEL_KNOWLEDGE",
    "INFERENCE",
]


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
    """Proposal only — never auto-promoted to canonical Memory."""

    fact_summary: str
    confidence: float = 0.5
    evidence_refs: List[str] = Field(default_factory=list)


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
    state_updates: List[StateUpdate] = Field(default_factory=list)
    memory_candidates: List[MemoryCandidate] = Field(default_factory=list)
    confidence: Optional[float] = None
    # Optional epistemic self-report (not shown to user)
    claim_grounding: Optional[GroundingKind] = None


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


class Observation(BaseModel):
    kind: Literal["tool", "context", "error", "system"] = "system"
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
