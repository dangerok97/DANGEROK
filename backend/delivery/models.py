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

from pydantic import BaseModel, Field, model_validator

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
# What raised the thing being weighed. V3.8 shipped assuming there was only
# ever one answer, which was true until an agent could need somebody.
#
# The alternative — inventing an Opportunity so the agent had one — would have
# been three lines and a lie: an opportunity is something ORA noticed about a
# life, and "I am stuck and need you" is not that. Two source types cost less
# than one dishonest one.
DeliverySource = Literal["opportunity", "agent_need"]

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


class DeliverySubject(BaseModel):
    """
    The thing being weighed, whatever raised it.

    Deliberately shaped like an Opportunity rather than like a new idea: the
    context builder reads its subject by attribute name, so a subject that
    answers to the same names needs no branch anywhere downstream. That is the
    whole generalisation — one adapter at the edge instead of a source check
    at every call site.

    The last few fields are the ones an opportunity has no use for and an
    agent need cannot do without: whether somebody has to reply, and what ORA
    had already done before it got stuck.
    """

    source_type: DeliverySource = "agent_need"
    id: str
    owner_id: str

    # Read by `delivery.context._about`, under exactly these names.
    semantic_summary: str = Field(default="", max_length=400)
    why_it_matters: str = Field(default="", max_length=400)
    why_now: str = Field(default="", max_length=400)
    created_at: str = Field(default_factory=now_iso)
    valid_until: Optional[str] = None
    relevance: Optional[str] = None
    urgency: Optional[str] = None
    time_sensitivity: Optional[str] = None
    requires_clarification: bool = False
    surfaced_count: int = 0
    seen_at: Optional[str] = None
    deferred_until: Optional[str] = None
    status: str = "active"

    # What only a need has.
    #
    # `goal_id` is the second handle a tap needs: a need belongs to a goal,
    # and landing somebody on the goal instead of on the thing that is
    # blocked throws away the only useful thing the notification knew. Empty
    # for an opportunity, which has nothing above it.
    goal_id: str = Field(default="", max_length=64)
    requires_response: bool = False
    # In human words: what ORA already did, so the judgement can weigh
    # "everything is ready and one thing is missing" differently from
    # "something came up".
    work_already_done: List[str] = Field(default_factory=list, max_length=6)
    what_is_missing: str = Field(default="", max_length=300)
    sensitivity_hint: Sensitivity = "ordinary"
    source_refs: List[str] = Field(default_factory=list, max_length=8)


def source_of(subject: Any) -> str:
    """
    Which kind of thing this is. An Opportunity does not carry the field, and
    should not have to — it was here first.
    """
    return str(getattr(subject, "source_type", "") or "opportunity")


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

    # What this plan is about, and what kind of thing that is.
    source_type: DeliverySource = "opportunity"
    source_id: str = ""
    # The field V3.8 shipped with. Kept, and kept populated for the
    # opportunity path, because rows written before the bridge existed have
    # only this one and there is no reason to migrate them to prove a point.
    # For an agent need it is empty — an id that is not an opportunity's must
    # not be filed under a name that says it is.
    opportunity_id: str = ""

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

    @model_validator(mode="after")
    def _one_identity(self) -> "DeliveryPlan":
        """
        Keep the two names for one thing in step.

        A row written before this bridge has `opportunity_id` and no
        `source_id`; a plan built by the agent has `source_id` and must not
        have an `opportunity_id`. Reconciled here rather than at every call
        site, which is where the "decine di if" would otherwise live.
        """
        if not self.source_id and self.opportunity_id:
            self.source_id = self.opportunity_id
        if self.source_type == "opportunity" and not self.opportunity_id:
            self.opportunity_id = self.source_id
        if self.source_type != "opportunity":
            self.opportunity_id = ""
        return self

    def touch(self) -> None:
        self.updated_at = now_iso()

    @property
    def is_open(self) -> bool:
        return self.status in ("pending", "held")

    def public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "opportunity_id": self.opportunity_id or None,
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
