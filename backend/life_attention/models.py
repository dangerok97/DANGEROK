"""Attention & Intervention decision V2.9.3 — "SHOULD I SPEAK?".

An AttentionDecision records whether a batch of ImpactAssessments deserves the
user's attention, and if so through which surface. It is NOT a notification
already sent, NOT a tool execution, NOT a Calendar write, NOT a Plan, NOT a
Memory and NOT a Situation — it is an internal delivery decision that the
system may still downgrade.

The load-bearing property is that **silence is a first-class outcome**. An
assessment reaching this layer does not imply a suggestion: the most common
correct answer is `silent`, and the contract makes that the cheapest possible
result to express.

Two authorities are recorded separately and never merged:

* `ai_delivery` — what the model judged would help the user.
* `delivery` — what the system actually permits after the deterministic gate.

Keeping both makes every downgrade auditable, and makes it impossible for the
model to grant itself permission to interrupt: only `delivery` is acted on.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from context_graph.models import is_recognized_ref

# Delivery surfaces, ordered from quietest to loudest. `silent` is first
# because it is the default, not the fallback.
DeliveryMode = Literal[
    "silent",
    "defer",
    "home",
    "ask_user",
    "propose_action",
    "notify",
]

# Ranking used when the system downgrades an AI choice; a downgrade may only
# ever move LEFT along this axis, never right.
DELIVERY_ORDER: tuple = ("silent", "defer", "home", "ask_user", "propose_action", "notify")

MAX_REFS = 12
MAX_DOWNGRADE_REASONS = 6


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_decision_id() -> str:
    return f"lad_{uuid.uuid4().hex[:16]}"


# A deferral may be automatically reconsidered at most this many times. This
# is a COST ceiling, not a semantic verdict: exhausting it means "ORA will not
# spend more automatic re-evaluations on this question", never "this question
# stopped mattering". See `auto_re_evaluation_exhausted`.
MAX_AUTOMATIC_DEFER_REEVALUATIONS = 3


def root_attention_key_for(user_id: str, assessment_ids: List[str]) -> str:
    """Stable identity of an attention QUESTION, independent of how many times
    it has been reconsidered.

    Order-independent over the assessment refs, so the same batch always maps
    to the same root regardless of read order. Never a timestamp.
    """
    ordered = ":".join(sorted({str(a) for a in assessment_ids if a}))
    digest = hashlib.sha256(f"{user_id}|{ordered}".encode()).hexdigest()[:32]
    return f"att_{digest}"


def decision_key_for(
    user_id: str, assessment_ids: List[str], *, revision: int = 1
) -> str:
    """Deterministic identity of ONE attention evaluation: the root question
    plus which reconsideration of it this is.

    Revision 1 deliberately yields exactly the pre-V2.9.4 key, so decisions
    written before revisions existed keep their identity and are never
    re-decided. A retry of the same revision produces the same key and is
    refused by the unique index; a legitimate reconsideration increments the
    revision and is therefore a genuinely new decision rather than an
    overwrite.
    """
    root = root_attention_key_for(user_id, assessment_ids)
    rev = max(1, int(revision or 1))
    return root if rev == 1 else f"{root}:r{rev}"


def is_quieter(candidate: str, current: str) -> bool:
    try:
        return DELIVERY_ORDER.index(candidate) < DELIVERY_ORDER.index(current)
    except ValueError:
        return False


def sanitize_refs(refs: Optional[List[str]], *, limit: int = MAX_REFS) -> List[str]:
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


class AttentionDecision(BaseModel):
    """One delivery decision for one bounded batch of ImpactAssessments."""

    id: str = Field(default_factory=new_decision_id, max_length=40)
    user_id: str = Field(max_length=80)

    assessment_refs: List[str] = Field(default_factory=list, max_length=8)
    focal_refs: List[str] = Field(default_factory=list, max_length=MAX_REFS)

    # What the model judged, kept verbatim for audit even when overruled.
    ai_delivery: DeliveryMode = "silent"
    # What the system permits. This is the only field anything acts on.
    delivery: DeliveryMode = "silent"

    # The model's bounded judgement of the intervention's worth. These are
    # inputs to the deterministic gate, never permissions in themselves.
    utility: float = Field(default=0.0, ge=0.0, le=1.0)
    urgency: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    novelty: float = Field(default=0.0, ge=0.0, le=1.0)
    actionability: float = Field(default=0.0, ge=0.0, le=1.0)

    # Deterministically computed by the system from real signals (resolved
    # local time, calendar occupancy by time overlap, recent volume, dismiss
    # history) — never asked of the model.
    interruption_cost: float = Field(default=0.0, ge=0.0, le=1.0)

    # Why the system moved the AI's choice, one short code per reason. Empty
    # when the system agreed with the model.
    downgrade_reasons: List[str] = Field(
        default_factory=list, max_length=MAX_DOWNGRADE_REASONS
    )

    # Short operational conclusion, NOT chain-of-thought.
    reason_summary: Optional[str] = Field(default=None, max_length=400)

    # A user-facing headline the model proposed. Persisted only so the
    # suggestion built from this decision stays traceable; it is bounded and
    # never a conversation transcript.
    proposed_title: Optional[str] = Field(default=None, max_length=120)

    evidence_refs: List[str] = Field(default_factory=list, max_length=MAX_REFS)

    # Set only when delivery == "defer": when it becomes worth re-evaluating.
    defer_until: Optional[str] = Field(default=None, max_length=40)
    # Lifecycle marker for that deferral (V2.9.4). Separate from `delivery`,
    # which records the decision itself: a deferral stays a deferral, but it
    # stops being in the future. Documents written before V2.9.4 lack the
    # field, and a `$ne: "due"` query treats them as still pending, so no
    # backfill is needed.
    defer_status: Literal["pending", "due"] = "pending"

    # Populated only if the decision actually produced a user-facing item.
    suggestion_id: Optional[str] = Field(default=None, max_length=64)
    suggestion_created: bool = False
    gate_reasons: List[str] = Field(default_factory=list, max_length=MAX_DOWNGRADE_REASONS)

    decision_key: str = Field(max_length=80)

    # --- reconsideration chain (V2.9.4 hardening) ----------------------
    # Stable identity of the underlying question, shared by every revision.
    root_attention_key: str = Field(default="", max_length=64)
    # 1 for the original decision, then 2, 3, ... for each reconsideration.
    attention_revision: int = 1
    # History is append-only: a superseded decision keeps its content and only
    # learns which decision replaced it.
    supersedes_decision_id: Optional[str] = Field(default=None, max_length=64)
    superseded_by: Optional[str] = Field(default=None, max_length=64)
    # How many AUTOMATIC re-evaluations this chain has already spent. Counts
    # reconsiderations after the first decision, so revision N has used N-1.
    automatic_re_evaluations_used: int = 0
    # Set when the automatic budget runs out. A cost marker, never a verdict:
    # the decision itself stays whatever the AI last decided.
    auto_re_evaluation_exhausted: bool = False
    model_provider: Optional[str] = Field(default=None, max_length=40)
    model_name: Optional[str] = Field(default=None, max_length=80)
    created_at: str = Field(default_factory=now_iso)

    def public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "assessment_refs": list(self.assessment_refs),
            "focal_refs": list(self.focal_refs),
            "ai_delivery": self.ai_delivery,
            "delivery": self.delivery,
            "utility": self.utility,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "novelty": self.novelty,
            "actionability": self.actionability,
            "interruption_cost": self.interruption_cost,
            "downgrade_reasons": list(self.downgrade_reasons),
            "reason_summary": self.reason_summary,
            "defer_until": self.defer_until,
            "attention_revision": self.attention_revision,
            "auto_re_evaluation_exhausted": self.auto_re_evaluation_exhausted,
            "suggestion_created": self.suggestion_created,
            "suggestion_id": self.suggestion_id,
            "created_at": self.created_at,
        }


class AttentionPassReport(BaseModel):
    """Bounded, non-sensitive outcome of one attention pass."""

    assessments_seen: int = 0
    batches: int = 0
    ai_calls: int = 0
    silent: int = 0
    deferred: int = 0
    home: int = 0
    ask_user: int = 0
    propose_action: int = 0
    notify_requested: int = 0
    system_downgrades: int = 0
    gate_rejects: int = 0
    suggestions_created: int = 0
    dedupe_hits: int = 0
    assessments_evaluated: int = 0
    # Deferral reconsideration (V2.9.4 hardening).
    defer_reevaluations_requested: int = 0
    defer_reevaluations_completed: int = 0
    defer_reevaluations_failed: int = 0
    defer_budget_exhausted: int = 0
    defer_to_silent: int = 0
    defer_to_defer: int = 0
    defer_to_home: int = 0
    defer_to_ask: int = 0
    defer_to_propose: int = 0
    defer_to_notify: int = 0
    failures: List[str] = Field(default_factory=list, max_length=8)
    elapsed_ms: int = 0
