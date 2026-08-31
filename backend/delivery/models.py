"""
What ORA is allowed to do about something it believes, and how it says so.

    INTERRUPTION MUST BE EARNED.
    A PUSH MUST HAVE A REAL REASON TO OPEN ORA.
    NO NOTIFICATION IS A VALID DECISION.

Four ways of existing in somebody's day, and they are four decisions rather
than four rungs of one ladder. Something can be worth a line on Home and not
worth a buzz in a pocket; the same concern can deserve a push at eight in the
morning and silence at eleven at night. Deriving `push` from `in_app` would
collapse that into a single axis and lose the only judgement that matters.

Nothing here is a number. A delivery mode is a word, a timing is a word plus
a real moment, and confidence is `weak | reasonable | strong` — because the
question "is this worth interrupting a person for" has never once been
answered better by a threshold than by a reason somebody could argue with.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# How ORA may exist in somebody's day. Four decisions, not four rungs.
DeliveryMode = Literal["silence", "quiet_presence", "in_app", "push"]

# When. `at` and `window` carry real moments; `hold` means not on any schedule
# we can name yet, and is the honest answer more often than it looks.
TimingKind = Literal["now", "at", "window", "hold"]

Confidence = Literal["weak", "reasonable", "strong"]

# What a lock screen may carry. The phone shows notification text to whoever
# is holding it, which is not always the person it is about.
Sensitivity = Literal["ordinary", "personal", "private"]

# A plan's life. `held` is not `cancelled`: the reason still stands, the
# moment does not.
PlanStatus = Literal["pending", "held", "cancelled", "delivered", "expired"]

# Who decided. `model` is a judgement; the others are the code admitting it
# had no judgement available and saying so rather than pretending.
DeliveryProvenance = Literal["model", "code_cancel", "code_expiry", "code_safety"]

# What became of something that was actually sent.
DeliveryOutcome = Literal["delivered", "opened", "dismissed", "expired"]

# What kind of real work ORA did. Domain-neutral on purpose: these are the
# only things it is allowed to claim, and none of them names a feature.
AmbientKind = Literal[
    "review_completed",
    "change_processed",
    "opportunity_created",
    "opportunity_resolved",
    "evidence_refreshed",
    "delivery_held",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return _now().isoformat()


def new_activity_id() -> str:
    return f"amb_{uuid.uuid4().hex[:16]}"


def new_plan_id() -> str:
    return f"dlv_{uuid.uuid4().hex[:16]}"


class AmbientActivity(BaseModel):
    """
    Something ORA actually did, recorded so it can be said out loud.

        ORA SHOULD FEEL ALIVE BECAUSE IT IS WORKING,
        NOT BECAUSE IT PRETENDS TO BE.

    This exists to make one sentence on Home honest. "Ho ricontrollato quello
    che stai seguendo" is either true or it is a small lie told constantly,
    and the difference is whether a review actually ran. So the claim has to
    point at a record — and the record is written by the work, never by the
    surface that wants something to say.

    Deliberately not a log. It is bounded, it holds human words and refs
    rather than payloads, and it expires: a permanent trace of everything ORA
    ever noticed about somebody's life is not proof of work, it is
    surveillance with a friendly caption.
    """

    id: str = Field(default_factory=new_activity_id)
    owner_id: str

    kind: AmbientKind
    occurred_at: str = Field(default_factory=now_iso)

    # What happened, in words a person could read. Not a status line.
    summary: str = Field(default="", max_length=200)

    # What it was about — handles, never contents.
    source_refs: List[str] = Field(default_factory=list, max_length=8)

    # Why this is a real claim: what ran, and what it looked at. Internal.
    # Nobody sees it; it exists so the question "why is ORA saying this?"
    # always has an answer that is not "because the screen needed a line".
    cognitive_provenance: Dict[str, Any] = Field(default_factory=dict)

    # Whether a surface may mention it at all. Most work is invisible: a scan
    # that found nothing has still happened, but saying so every few minutes
    # would be noise wearing the costume of transparency.
    visibility: Literal["internal", "ambient"] = "internal"

    # Set by Mongo's TTL index.
    expires_at: Optional[datetime] = None

    def for_home(self) -> Dict[str, Any]:
        """One human line, and nothing that reveals the machine."""
        return {"id": self.id, "text": self.summary, "at": self.occurred_at}


class PushCopy(BaseModel):
    """
    What a notification says, at two distances.

    A lock screen is read by whoever is holding the phone, and the person it
    concerns may not be alone. So `public` is what is safe to show there and
    `expanded` is what the same notification says once the phone is unlocked
    — the same fact, told at two levels of detail, never two different facts.
    """

    title: str = Field(default="", max_length=80)
    body: str = Field(default="", max_length=200)
    # Safe on a lock screen: true when it says why it is worth opening
    # without saying anything the wrong reader should not have.
    public_title: str = Field(default="", max_length=80)
    public_body: str = Field(default="", max_length=200)

    def public(self) -> Dict[str, str]:
        return {
            "title": self.public_title or self.title,
            "body": self.public_body or self.body,
        }


class DeliveryDecision(BaseModel):
    """
    One judgement about whether, how and when to say something.

    `reason_to_interrupt` and `reason_to_open` are separate on purpose. The
    first is why this is worth costing somebody their attention; the second is
    what they would find if they came. A notification that can answer the
    first but not the second is an alert with nothing behind it, and one that
    answers the second but not the first is a fact that could have waited.
    """

    mode: DeliveryMode
    timing: TimingKind = "now"

    # Real moments when the model named them. Bounds are applied by code.
    not_before: Optional[str] = None
    not_after: Optional[str] = None

    reason_to_interrupt: str = Field(default="", max_length=400)
    reason_to_open: str = Field(default="", max_length=400)
    # Why THIS channel and this moment, rather than the alternatives that were
    # also defensible.
    #
    # The other two reasons are both about the situation: what makes it worth
    # attention, and what somebody would find. Neither can answer why a quiet
    # line was preferred to a buzz — so when a preference, a recent
    # interruption or the hour tipped the choice, there was nowhere to say so
    # and it stayed invisible. That is what this field is for.
    #
    # A short product justification, never a scratchpad. It is kept so a
    # decision can be audited later; it is not chain-of-thought and it is not
    # written for a screen.
    what_decided_the_mode: str = Field(default="", max_length=300)
    # What the copy should get across, in the model's words. Not the copy.
    copy_intent: str = Field(default="", max_length=300)

    confidence: Confidence = "reasonable"
    sensitivity: Sensitivity = "ordinary"
    # The facts under this may move before the moment arrives.
    requires_recheck: bool = True

    words: Optional[PushCopy] = None

    def public(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "timing": self.timing,
            "not_before": self.not_before,
            "not_after": self.not_after,
            "why_interrupt": self.reason_to_interrupt or None,
            "why_open": self.reason_to_open or None,
            "what_decided": self.what_decided_the_mode or None,
            "confidence": self.confidence,
            "sensitivity": self.sensitivity,
        }


class DeliveryPlan(BaseModel):
    """
    An intention to say something, which is not the same as having said it.

    Everything that makes a scheduled notification dangerous lives in the gap
    between deciding and sending: the document arrives, the meeting is
    cancelled, the person deals with it themselves. So the plan is a record of
    an intention that must survive being re-examined, and `last_rechecked_at`
    is the field that says whether anybody did.
    """

    id: str = Field(default_factory=new_plan_id)
    owner_id: str
    opportunity_id: str

    mode: DeliveryMode
    status: PlanStatus = "pending"

    not_before: Optional[str] = None
    not_after: Optional[str] = None

    # The words as they were decided. Kept so a delivered notification can be
    # explained afterwards even if the opportunity has moved on since.
    words: PushCopy = Field(default_factory=PushCopy)
    reason_to_interrupt: str = Field(default="", max_length=400)
    reason_to_open: str = Field(default="", max_length=400)
    # Kept with the plan, so a notification that arrived can be explained
    # afterwards — including when it was a preference that tipped it.
    what_decided_the_mode: str = Field(default="", max_length=300)
    sensitivity: Sensitivity = "ordinary"

    # Where a tap lands. A notification that opens Home when we know exactly
    # what it was about has thrown away the only thing it knew.
    deep_link: str = Field(default="", max_length=300)

    decision_provenance: DeliveryProvenance = "model"
    # Why it ended up where it ended up, in whoever's words decided.
    rationale: str = Field(default="", max_length=300)

    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    last_rechecked_at: Optional[str] = None
    delivered_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    # When somebody actually opened it. Distinct from `outcome` because
    # "opened" is a moment we know and "not opened" is only an absence — and
    # the two must never be confused into a claim that somebody refused
    # something they may simply not have seen.
    opened_at: Optional[str] = None

    outcome: Optional[DeliveryOutcome] = None
    # Set by Mongo's TTL index, and only once a plan is settled.
    expires_at: Optional[datetime] = None

    def touch(self) -> None:
        self.updated_at = now_iso()

    @property
    def is_open(self) -> bool:
        return self.status in ("pending", "held")

    def public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "opportunity_id": self.opportunity_id,
            "mode": self.mode,
            "status": self.status,
            "not_before": self.not_before,
            "not_after": self.not_after,
            "why_open": self.reason_to_open or None,
            "deep_link": self.deep_link or None,
            "sensitivity": self.sensitivity,
            "last_rechecked_at": self.last_rechecked_at,
            "delivered_at": self.delivered_at,
            "opened_at": self.opened_at,
            "outcome": self.outcome,
        }


class DeliveryResult(BaseModel):
    """What an evaluation did, including deciding to do nothing."""

    mode: DeliveryMode = "silence"
    # True when the model could not be reached. Never silence: an outage has
    # no opinion, and recording one as a decision would be a lie told by a
    # network error.
    unavailable: bool = False
    reason: str = Field(default="", max_length=400)
    # Why this channel and this moment beat the alternatives.
    #
    # On the result rather than only on the plan, because a plan exists only
    # for something that intends to arrive. The decision worth keeping is
    # often the other one — "they asked for quiet, so this stays on their
    # screen" — and putting it only on a push would throw away every case
    # where the preference actually did the work.
    what_decided_the_mode: str = Field(default="", max_length=300)
    plan: Optional[DeliveryPlan] = None
    activity: Optional[AmbientActivity] = None
    # Technical refusals, named. Not judgements.
    blocked_by: str = Field(default="", max_length=120)

    def public(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "unavailable": self.unavailable,
            "reason": self.reason or None,
            "what_decided": self.what_decided_the_mode or None,
            "blocked_by": self.blocked_by or None,
            "plan": self.plan.public() if self.plan else None,
        }
