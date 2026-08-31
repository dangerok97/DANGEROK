"""
Something worth bringing to somebody's attention — and everything it is not.

    PROACTIVITY IS AN AI JUDGMENT, NOT A RULE TRIGGER.
    OPPORTUNITY != WORK. != NOTIFICATION. != ACTION.
    SILENCE IS A VALID DECISION.

An event tomorrow is not an opportunity. A deadline is not an opportunity.
Being at home is not an opportunity. An open decision is not an opportunity.
Each of those is a fact, and the question of whether any of them adds up to
something worth interrupting a person about is a judgement about that person's
life — which is why nothing in this file can answer it.

What the code owns is the shape: an opportunity has to point at facts that
exist, carry a reason a person could read, hold a stable identity so tomorrow's
version of the same concern does not arrive as a second one, and move through
a small set of states that only ever change for a stated reason.

Deliberately no scores. `relevance: high` is a judgement the model can defend
and a person can argue with; `relevance: 0.84` is the same judgement with the
argument hidden behind a decimal point. Where ordering is needed, code turns
the words into an order — that part has a right answer.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# How much this matters to this person, in words that carry their reasoning.
Relevance = Literal["low", "medium", "high"]

# When it stops being useful to say. `none` is the common case: most true
# things are not urgent, and treating them as though they were is how a
# proactive system becomes a nagging one.
Urgency = Literal["none", "soon", "urgent"]

# Whether the facts underneath it are still moving.
TimeSensitivity = Literal["stable", "changing", "perishable"]

Confidence = Literal["weak", "reasonable", "strong"]

# `candidate` is what the model proposed. `active` is what a person may see.
# Nothing becomes active by ageing: a decision moves it.
OpportunityStatus = Literal[
    "candidate",
    "active",
    "dismissed",
    "expired",
    "suppressed",
    "resolved",
]

# What a review concluded. The model chooses; code applies.
ReviewOutcome = Literal["keep", "update", "resolve", "expire", "suppress"]
# What can end up written in the history. A person saying "not this" is not
# a review outcome — the model must never be able to conclude it — but it is
# a decision, and a history that files a refusal under "keep" cannot be read.
DecisionOutcome = Literal[
    "keep", "update", "resolve", "expire", "suppress", "dismiss"
]

# Whether a person is currently being shown this, which is a different question
# from whether it is true. An opportunity can be entirely valid and still be
# the wrong thing to put in front of somebody right now.
SurfaceState = Literal["hidden", "surfaced", "held", "deferred"]

# What the model concluded about showing it. `retire` is not a judgement about
# the concern — it stays exactly as true as it was — only that it has no
# business occupying space on a screen any more.
SurfaceOutcome = Literal["surface", "hold", "retire"]

# Who chose when something may come back. `model` is a judgement about this
# particular thing; `technical_retry_hold` is the opposite of one — the model
# could not be reached, and the card is merely kept off the screen long enough
# not to reappear in the same breath. Keeping the two apart is the whole point:
# a hold that nobody decided must never be read later as a decision.
RevisitSource = Literal["model", "technical_retry_hold"]

# Who decided, so a status can always be traced to a decision rather than to
# a mechanism nobody remembers writing.
DecisionSource = Literal["model", "user", "code_expiry"]

# The order words become when something has to be sorted. Ordering is
# arithmetic; the words above are the judgement.
_RELEVANCE_ORDER = {"high": 0, "medium": 1, "low": 2}
_URGENCY_ORDER = {"urgent": 0, "soon": 1, "none": 2}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_opportunity_id() -> str:
    return f"opp_{secrets.token_hex(8)}"


def new_decision_id() -> str:
    return f"opd_{secrets.token_hex(8)}"


class EvidenceRef(BaseModel):
    """
    One fact an opportunity rests on, named where it lives.

    Not a copy of the fact: a reference to it, so an opportunity can be traced
    back and re-checked when the world moves. An opportunity with no evidence
    is an opinion about somebody's life, and this system does not hold those.
    """

    kind: str = Field(min_length=1, max_length=40)
    ref: str = Field(min_length=1, max_length=120)
    # What it said, in the words a person would recognise. Short: this is a
    # label for a fact, not the fact itself.
    summary: str = Field(default="", max_length=240)


class OpportunityCandidate(BaseModel):
    """
    What the model proposed during one scan.

    Not persisted as something to show anybody. It is the raw output of a
    judgement, and it still has to survive the checks in `service.py` —
    identity, evidence, not-already-dismissed — before it becomes anything.
    """

    identity_key: str = Field(min_length=3, max_length=120)
    semantic_summary: str = Field(min_length=1, max_length=280)
    why_it_matters: str = Field(min_length=1, max_length=600)
    why_now: str = Field(default="", max_length=400)

    relevance: Relevance = "medium"
    urgency: Urgency = "none"
    time_sensitivity: TimeSensitivity = "stable"
    confidence: Confidence = "reasonable"

    evidence: List[EvidenceRef] = Field(default_factory=list, max_length=8)

    # What the model could not establish, and what it would ask.
    requires_clarification: bool = False
    clarifying_question: str = Field(default="", max_length=300)
    needs_research: bool = False
    research_question: str = Field(default="", max_length=300)

    # Where in the person's life this sits, when it sits somewhere named.
    related_goal_id: Optional[str] = Field(default=None, max_length=64)
    related_place_id: Optional[str] = Field(default=None, max_length=64)
    related_work_id: Optional[str] = Field(default=None, max_length=64)

    valid_until: Optional[str] = Field(default=None, max_length=40)


class Opportunity(BaseModel):
    """
    Something ORA thinks is worth this person's attention, and why.

    `identity_key` is the part that makes this a life rather than a feed. The
    same concern noticed again tomorrow — worded differently, because language
    is not a key — has to find yesterday's record instead of stacking a second
    one beside it. The model writes the key; code checks it and refuses what it
    cannot resolve.
    """

    id: str = Field(default_factory=new_opportunity_id)
    owner_id: str
    identity_key: str = Field(min_length=3, max_length=120)

    status: OpportunityStatus = "candidate"

    semantic_summary: str = Field(min_length=1, max_length=280)
    why_it_matters: str = Field(min_length=1, max_length=600)
    why_now: str = Field(default="", max_length=400)

    relevance: Relevance = "medium"
    urgency: Urgency = "none"
    time_sensitivity: TimeSensitivity = "stable"
    confidence: Confidence = "reasonable"

    evidence: List[EvidenceRef] = Field(default_factory=list, max_length=8)
    # Which scan produced it, for tracing a judgement back to its inputs.
    source_context: str = Field(default="", max_length=120)

    requires_clarification: bool = False
    clarifying_question: str = Field(default="", max_length=300)
    needs_research: bool = False
    research_question: str = Field(default="", max_length=300)

    related_goal_id: Optional[str] = Field(default=None, max_length=64)
    related_place_id: Optional[str] = Field(default=None, max_length=64)
    related_work_id: Optional[str] = Field(default=None, max_length=64)

    valid_from: str = Field(default_factory=now_iso)
    valid_until: Optional[str] = Field(default=None, max_length=40)

    decision_provenance: DecisionSource = "model"
    last_reviewed_at: Optional[str] = None

    # Being worth saying and being worth saying *now* are two judgements, and
    # keeping them apart is what stops a valid concern from becoming wallpaper.
    # The model decides; these record what was decided and when it took effect.
    surface_state: SurfaceState = "hidden"
    surface_rationale: str = Field(default="", max_length=300)
    last_surfaced_at: Optional[str] = None
    seen_at: Optional[str] = None
    deferred_until: Optional[str] = None
    # Why it is off the screen until then, and in whose words. Without this a
    # six-hour hold nobody chose is indistinguishable from six hours somebody
    # reasoned about.
    revisit_source: Optional[RevisitSource] = None
    revisit_rationale: str = Field(default="", max_length=300)
    # How many times a person has already had this in front of them. Shown to
    # the model, never to a screen: the fifth appearance of the same card is
    # a different proposition from the first.
    surfaced_count: int = 0
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def touch(self) -> None:
        self.updated_at = now_iso()

    @property
    def order_key(self) -> tuple:
        """
        A deterministic order from words, for surfaces that need one.

        Arithmetic over a judgement, not a judgement of its own: the model said
        `high` and `urgent`, and this only decides which of two `high`s comes
        first. Ties break on age, so the same list is the same list twice.
        """
        return (
            _URGENCY_ORDER.get(self.urgency, 9),
            _RELEVANCE_ORDER.get(self.relevance, 9),
            self.created_at,
        )

    def public(self) -> Dict[str, Any]:
        """
        What a surface may see.

        The identity key is absent: it is how the system recognises a concern
        across days, and a screen has no use for it.
        """
        return {
            "id": self.id,
            "status": self.status,
            "what": self.semantic_summary,
            "why_it_matters": self.why_it_matters,
            "why_now": self.why_now or None,
            "relevance": self.relevance,
            "urgency": self.urgency,
            "time_sensitivity": self.time_sensitivity,
            "confidence": self.confidence,
            "based_on": [
                {"kind": e.kind, "summary": e.summary or None} for e in self.evidence
            ],
            "needs_clarification": self.requires_clarification,
            "question": self.clarifying_question or None,
            "needs_research": self.needs_research,
            "valid_until": self.valid_until,
            "created_at": self.created_at,
            "last_reviewed_at": self.last_reviewed_at,
        }

    def for_home(self) -> Dict[str, Any]:
        """
        What a person reads, and nothing else.

        `public()` is a debug view and says `relevance: high`, `confidence:
        strong`, `time_sensitivity: perishable`. Those are how the system
        thinks, and none of them is something a person would ever say about
        their own week — a card that shows them is showing its own wiring.
        What survives here is a sentence and a reason.
        """
        return {
            "id": self.id,
            "title": self.semantic_summary,
            "why_now": self.why_now or self.why_it_matters,
            "question": self.clarifying_question or None,
            "seen": bool(self.seen_at),
        }

    def for_ai(self) -> Dict[str, Any]:
        """What a later scan is told it has already raised."""
        return {
            "identity_key": self.identity_key,
            "status": self.status,
            "what": self.semantic_summary,
            "relevance": self.relevance,
            "urgency": self.urgency,
            "raised_at": self.created_at,
        }


class OpportunityDecision(BaseModel):
    """
    One decision about one opportunity, kept.

    Status is never edited in place without leaving this behind: an
    opportunity that quietly became `expired` with nobody able to say why is
    indistinguishable from a bug.
    """

    id: str = Field(default_factory=new_decision_id)
    opportunity_id: str
    owner_id: str
    outcome: DecisionOutcome
    source: DecisionSource = "model"
    # Why, in the words of whoever decided.
    rationale: str = Field(default="", max_length=400)
    decided_at: str = Field(default_factory=now_iso)


class ScanResult(BaseModel):
    """
    What one scan concluded, including the common conclusion: nothing.

    `silence` is not an empty result to be tidied away. Most scans should end
    here, and a system that treats that as a failure will start manufacturing
    reasons to speak.
    """

    silence: bool = True
    reason_for_silence: str = Field(default="", max_length=400)
    created: List[Opportunity] = Field(default_factory=list)
    updated: List[Opportunity] = Field(default_factory=list)
    skipped: List[Dict[str, str]] = Field(default_factory=list)
    # Set when no judgement could be made at all — a provider outage is not
    # silence, and must never be recorded as one.
    unavailable: bool = False

    def public(self) -> Dict[str, Any]:
        return {
            "silence": self.silence,
            "reason": self.reason_for_silence or None,
            "unavailable": self.unavailable,
            "created": [o.public() for o in self.created],
            "updated": [o.public() for o in self.updated],
            "skipped": self.skipped,
        }
