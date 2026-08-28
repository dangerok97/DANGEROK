"""
Life Guidance — the state ORA needs in order to stop interrogating people.

Four questions, kept apart because they fail differently:

    where am I?          state reconstruction
    what is left?        residual path
    can I proceed?       information sufficiency
    what do I ask?       minimum necessary questioning

The constitutional rule underneath all four is that a question is the *last*
resort. Something ORA already knows must never become a question; something it
does not need yet must never become a question either. Both failures look like
diligence and read like an interrogation.

Domain-neutral by construction. There is no mortgage milestone and no travel
milestone: there is a milestone, whether it is done, and how we know.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Where am I
# ---------------------------------------------------------------------------

# How a milestone's state is held. The distinction is the whole point of §6:
# "ho firmato il compromesso" is a fact, and "the property has been chosen" is
# a reasonable inference from it. ORA may act on inference — that is what stops
# it asking obvious questions — but it may not present one as something the
# person told it, and a correction always wins.
Basis = Literal["fact", "inference", "unknown"]

MilestoneState = Literal[
    "done",           # behind us, whether stated or reasonably inferred
    "active",         # where the work is now
    "upcoming",       # ahead, and expected to apply
    "conditional",    # ahead, but only on one branch of an open decision
    "not_applicable", # ruled out for this person's situation
    "unknown",
]


class Milestone(BaseModel):
    """One step of the path, and how ORA came to believe its state."""

    ref: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    state: MilestoneState = "unknown"
    basis: Basis = "unknown"
    # Where the belief came from: a turn, a memory, a document, a plan item.
    # Bounded and opaque — enough to answer "why does ORA think this is done?"
    evidence_refs: List[str] = Field(default_factory=list, max_length=6)
    # The Life OS item this milestone is projected onto, when there is one.
    # Identity lives in Life OS; guidance points at it rather than copying it.
    plan_item_id: Optional[str] = Field(default=None, max_length=64)
    # Only meaningful for `conditional`: which open decision selects this branch.
    depends_on: Optional[str] = Field(default=None, max_length=120)

    def is_behind_us(self) -> bool:
        return self.state in ("done", "not_applicable")


class OpenDecision(BaseModel):
    """A fork the path cannot be planned past until it is settled."""

    ref: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=400)
    options: List[str] = Field(default_factory=list, max_length=6)


class GoalState(BaseModel):
    """
    The reconstruction. Structured enough to plan from, not a summary.

    `stage` is the reasoning's own words for where this sits — "compromesso
    firmato, manca il finanziamento" — and never an enum, because an enum of
    stages is a domain flow wearing a different hat.
    """

    objective: str = Field(default="", max_length=300)
    stage: str = Field(default="", max_length=300)
    milestones: List[Milestone] = Field(default_factory=list, max_length=20)
    constraints: List[str] = Field(default_factory=list, max_length=8)
    open_decisions: List[OpenDecision] = Field(default_factory=list, max_length=4)
    # Bumped whenever new information changes the reconstruction, so a plan
    # change can be traced to what caused it rather than appearing by magic.
    revision: int = 0

    def residual(self) -> List[Milestone]:
        """What remains from here — the only part a person should be shown."""
        return [m for m in self.milestones if not m.is_behind_us()]

    def active(self) -> Optional[Milestone]:
        for m in self.milestones:
            if m.state == "active":
                return m
        upcoming = [m for m in self.milestones if m.state == "upcoming"]
        return upcoming[0] if upcoming else None


# ---------------------------------------------------------------------------
# Can I proceed
# ---------------------------------------------------------------------------

# Why a piece of information matters *to the next step*. Only `required` may
# ever become a question; the other two wait, however interesting they are.
Necessity = Literal["required", "useful", "optional"]

# Where a variable's value came from when ORA already had it. `unresolved`
# means nobody knows it yet; `declined` means the person was asked and chose
# not to say, which is an answer and must not be asked again.
Origin = Literal[
    "unresolved", "user_turn", "memory", "profile", "life_os",
    "document", "prior_answer", "inference", "declined",
]


class Variable(BaseModel):
    """
    One thing the next step needs, and what became of it.

    `label` is what a person would call it; `purpose` is why the next step
    cannot be taken without it. Both exist so a question can explain itself
    without the reasoning having to re-derive the explanation.
    """

    ref: str = Field(min_length=1, max_length=120)
    label: str = Field(default="", max_length=160)
    purpose: str = Field(default="", max_length=240)
    necessity: Necessity = "useful"
    sensitivity: Literal["normal", "sensitive", "high"] = "normal"
    origin: Origin = "unresolved"
    # A short human trace of what was found — never the raw sensitive value.
    resolved_note: str = Field(default="", max_length=200)

    @property
    def resolved(self) -> bool:
        return self.origin != "unresolved"

    @property
    def blocks(self) -> bool:
        """Blocking means required *and* still unknown. Nothing else blocks."""
        return self.necessity == "required" and self.origin == "unresolved"


class Sufficiency(BaseModel):
    """The answer to "can I take the next step with what I have?"."""

    can_proceed: bool = True
    variables: List[Variable] = Field(default_factory=list, max_length=24)

    def blocking(self) -> List[Variable]:
        return [v for v in self.variables if v.blocks]

    def resolved(self) -> List[Variable]:
        return [v for v in self.variables if v.resolved]

    def deferred(self) -> List[Variable]:
        """Known unknowns ORA is deliberately not asking about."""
        return [v for v in self.variables if v.necessity != "required" and not v.resolved]


# ---------------------------------------------------------------------------
# What next
# ---------------------------------------------------------------------------

NextStepKind = Literal["proceed", "ask", "wait", "complete"]


class NextStep(BaseModel):
    """
    What ORA does next — and asking is only one of the four.

    The ordering the service enforces is: proceed on what is known, resolve
    from what ORA already holds, and only then ask. A design where the next
    step is always a question is a questionnaire.
    """

    kind: NextStepKind = "proceed"
    title: str = Field(default="", max_length=200)
    milestone_ref: Optional[str] = Field(default=None, max_length=120)
    # Present only when `kind == "ask"`.
    question: str = Field(default="", max_length=600)
    why_needed: str = Field(default="", max_length=400)
    requested: List[Variable] = Field(default_factory=list, max_length=10)


class GuidanceOutcome(BaseModel):
    """
    One pass of the cycle, and enough of a trace to explain what it did.

    `avoided` is the number that matters most in review: variables the next
    step genuinely needed and that ORA answered from what it already had
    instead of asking. It is the difference between guidance and an intake form.
    """

    state: GoalState = Field(default_factory=GoalState)
    sufficiency: Sufficiency = Field(default_factory=Sufficiency)
    next_step: NextStep = Field(default_factory=NextStep)
    avoided: int = 0
    asked: int = 0
    reason: str = Field(default="", max_length=200)

    def public_trace(self) -> Dict[str, Any]:
        """Bounded, non-sensitive — for logs and tests, never for a screen."""
        return {
            "revision": self.state.revision,
            "milestones": len(self.state.milestones),
            "residual": len(self.state.residual()),
            "next_step": self.next_step.kind,
            "required": len([v for v in self.sufficiency.variables if v.necessity == "required"]),
            "avoided": self.avoided,
            "asked": self.asked,
            "reason": self.reason,
        }
