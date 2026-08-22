"""Impact Assessment V2.9.2 — structured internal reasoning about consequences.

An ImpactAssessment answers "SO WHAT?" for a bounded batch of LifeChangeSignals.
It is NOT a suggestion, NOT a notification, NOT a plan, NOT a Memory, NOT a
Situation, and NOT an action — it is reasoning ORA keeps to itself until
V2.9.3 decides whether anything is worth saying.

Two vocabularies are deliberately REUSED rather than reinvented:

* `epistemic_status` and `authority` come from `MemoryCandidate`/`ContextEdge`
  — ORA already has one epistemic model and must not grow a third.
* impact `kind` uses the general-purpose technical categories
  (dependency / risk / opportunity / constraint / conflict /
  missing_information), never a domain taxonomy. There is no HOUSE, TRAVEL or
  STUDY member here and adding one would be an architectural regression.

Design note — one list, not four: the CPO contract sketch listed `impacts`,
`unresolved_needs`, `opportunities` and `contradictions` as separate fields.
They are modelled here as a single bounded `impacts` list discriminated by
`kind`, because four near-identical parallel lists would each need their own
bounds, validation and prompt section while carrying the same shape. The
distinction the contract actually requires — known vs plausible vs unresolved
vs opportunity vs contradiction — is expressed by `kind` x `epistemic_status`,
which is strictly more expressive than four flat buckets.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from context_graph.models import is_recognized_ref

# General-purpose technical categories only — never a domain taxonomy.
ImpactKind = Literal[
    "dependency",
    "risk",
    "opportunity",
    "constraint",
    "conflict",
    "missing_information",
]

# Reused verbatim from MemoryCandidate — ORA has ONE epistemic model.
EpistemicStatus = Literal["tentative", "asserted", "confirmed", "inferred"]

# Reused verbatim from MemoryCandidate / ContextEdge.
Authority = Literal[
    "user_confirmed", "user_stated", "document", "structured", "inferred", "device"
]

# Coarse, evidence-bounded timing. Never an invented date.
TemporalHorizon = Literal["immediate", "near_term", "later", "unscheduled", "unknown"]

# What KIND of next step would help. This is explicitly NOT an attention or
# notification decision: nothing here says send_now / notify / surface_home /
# interrupt. Those belong to V2.9.3.
NextStepKind = Literal[
    "none",
    "gather_context",
    "ask_user",
    "propose_action",
    "compare_options",
]

AssessmentStatus = Literal["complete", "insufficient_evidence"]

# Downstream lifecycle marker (V2.9.3). Separate from `status`, which describes
# the CONTENT of the reasoning: an assessment can be perfectly complete and
# still be waiting for the attention pass to look at it. Documents written
# before V2.9.3 simply lack the field, and a `$ne: "evaluated"` query treats
# them as pending — so no migration is needed.
AttentionStatus = Literal["pending", "evaluated"]

MAX_IMPACTS = 8
MAX_REFS = 12
MAX_EVIDENCE_REFS = 6


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_assessment_id() -> str:
    return f"lia_{uuid.uuid4().hex[:16]}"


def batch_key_for(user_id: str, signal_ids: List[str]) -> str:
    """Deterministic identity of a batch: the same set of signals always maps
    to the same key regardless of ordering, so a replayed pass cannot produce
    a duplicate assessment. Never a timestamp and never a fresh UUID."""
    ordered = ":".join(sorted({str(s) for s in signal_ids if s}))
    digest = hashlib.sha256(f"{user_id}|{ordered}".encode()).hexdigest()[:32]
    return f"batch_{digest}"


def sanitize_refs(refs: Optional[List[str]], *, limit: int = MAX_REFS) -> List[str]:
    """Keep only structurally valid canonical refs (the existing namespace),
    deduped and bounded. An AI-invented ref shape is dropped rather than
    persisted, so the store cannot accumulate a parallel namespace."""
    out: List[str] = []
    for raw in list(refs or []):
        ref = str(raw or "").strip()
        if not ref or ref in out:
            continue
        if not is_recognized_ref(ref):
            continue
        out.append(ref)
        if len(out) >= limit:
            break
    return out


class Impact(BaseModel):
    """One consequence the AI believes may follow from what changed.

    A possibility must stay a possibility: `kind` says what sort of
    consequence it is, `epistemic_status` + `confidence` say how strongly it
    is held, and `evidence_refs` say what it rests on. A tentative impact with
    no evidence is a legitimate output — silently promoting it to a fact is
    not.
    """

    statement: str = Field(min_length=1, max_length=300)
    kind: ImpactKind
    epistemic_status: EpistemicStatus = "tentative"
    confidence: float = Field(default=0.4, ge=0.0, le=1.0)
    # Canonical refs this impact concerns and rests on.
    affected_refs: List[str] = Field(default_factory=list, max_length=MAX_REFS)
    evidence_refs: List[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_REFS)
    authority: Optional[Authority] = None
    temporal_horizon: TemporalHorizon = "unknown"
    # A capability ORA already has that could serve this impact, when one
    # applies. Validated against the live registry — never free text, never a
    # vendor or provider brand, and never executed in V2.9.2.
    capability_hint: Optional[str] = Field(default=None, max_length=64)

    def public(self) -> Dict[str, Any]:
        return self.model_dump()


class ImpactAssessment(BaseModel):
    """Internal reasoning output for one bounded batch of LifeChangeSignals."""

    id: str = Field(default_factory=new_assessment_id, max_length=40)
    user_id: str = Field(max_length=80)

    # WHICH signals this assessment answers, and WHAT it is about.
    source_signal_ids: List[str] = Field(default_factory=list, max_length=8)
    focal_refs: List[str] = Field(default_factory=list, max_length=MAX_REFS)

    impacts: List[Impact] = Field(default_factory=list, max_length=MAX_IMPACTS)

    # How much this batch appears to matter. NOT a decision to speak: V2.9.3
    # owns attention, and no field here says notify/send/interrupt.
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_more_context: bool = False
    next_step_kind: NextStepKind = "none"

    # A short operational summary, NOT chain-of-thought. No private reasoning
    # trace is ever requested from the model or persisted here.
    reason_summary: Optional[str] = Field(default=None, max_length=400)

    # Evidence the reasoning actually saw, by ref — never the evidence itself.
    evidence_refs: List[str] = Field(default_factory=list, max_length=MAX_REFS)
    evidence_count: int = 0

    # Stable batch identity; unique sparse index enforces idempotency.
    batch_key: str = Field(max_length=64)
    status: AssessmentStatus = "complete"
    attention_status: AttentionStatus = "pending"

    # Bounded provenance for audit — provider/model name only, no payload.
    model_provider: Optional[str] = Field(default=None, max_length=40)
    model_name: Optional[str] = Field(default=None, max_length=80)

    created_at: str = Field(default_factory=now_iso)

    def public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_signal_ids": list(self.source_signal_ids),
            "focal_refs": list(self.focal_refs),
            "impacts": [i.public() for i in self.impacts],
            "relevance": self.relevance,
            "confidence": self.confidence,
            "requires_more_context": self.requires_more_context,
            "next_step_kind": self.next_step_kind,
            "reason_summary": self.reason_summary,
            "evidence_count": self.evidence_count,
            "status": self.status,
            "created_at": self.created_at,
        }


class AssessmentPassReport(BaseModel):
    """Bounded, non-sensitive outcome of one consumer pass — observability
    only, never user text."""

    signals_seen: int = 0
    batches: int = 0
    ai_calls: int = 0
    evidence_items: int = 0
    assessments_created: int = 0
    signals_processed: int = 0
    deferred: int = 0
    failures: List[str] = Field(default_factory=list, max_length=8)
    elapsed_ms: int = 0
