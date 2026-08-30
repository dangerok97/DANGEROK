"""
What a decision looks like while it is being made.

V3.4 gave ORA evidence. This is the step after: evidence, plus what ORA knows
about a person, becoming an answer to "which of these, for me?".

The division is the same as everywhere else. The model decides what matters
here, which of those things are absolute and which are preferences, what would
have to be worked out, which alternatives are not really comparable, whether
there is a winner at all, and whether it knows enough to say. The code does the
arithmetic, checks the stated constraints against the stated values, keeps the
provenance, and stores it.

There is no score in this file. A number like 87.4 next to a mortgage is a
claim to a precision nobody has, and the way it is produced — weights invented
to make the sum come out — is exactly the simulated judgement this phase is not
allowed to be. What a comparison produces is sentences: better for this, worse
for that, ruled out because, no clear winner unless you care most about.

Nothing here knows what is being compared. The same classes carry a loan, a
tariff and a language course, and the difference is entirely in what the model
wrote into them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# How much something matters, in the words a person would use. Deliberately not
# a number: a weight would be multiplied by something, and the moment the code
# multiplies it the code is deciding what matters.
Importance = Literal["deal_breaker", "major", "moderate", "minor"]

# What the model concluded once it had looked at everything.
Verdict = Literal[
    "clear_choice",      # one of them is the answer
    "conditional",       # it depends on what the person cares about most
    "no_clear_winner",   # they are genuinely close
    "insufficient",      # not enough to say responsibly
]

# How firmly it holds. Never shown as a number.
Confidence = Literal["strong", "tentative", "weak"]

# Relations the code can check without understanding the subject.
Operator = Literal["<=", "<", ">=", ">", "==", "!=", "in", "not_in"]

# Arithmetic the code can do without understanding the subject.
Operation = Literal["sum", "difference", "product", "quotient", "percent_of", "percent_change"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    return f"cmp_{uuid.uuid4().hex[:12]}"


def new_alternative_id() -> str:
    return f"alt_{uuid.uuid4().hex[:10]}"


def new_attribute_id() -> str:
    return f"attr_{uuid.uuid4().hex[:8]}"


class ComparisonNeed(BaseModel):
    """
    The reasoning saying this is a choice, not a question.

    "What does petrol cost" wants an answer. "Which of these suits me" wants a
    decision, and the difference is the model's to see — nothing counts results
    and calls two of them a comparison.
    """

    decision: str = Field(min_length=1, max_length=400)
    # Why it is being made now, in the model's words.
    purpose: str = Field(default="", max_length=300)
    # What the reasoning already holds about this person and this choice, so
    # nothing is asked twice.
    already_known: List[str] = Field(default_factory=list, max_length=16)


class Attribute(BaseModel):
    """
    One stated fact about one alternative, and where it came from.

    `id` is how everything afterwards refers to this. Found live: the model
    wrote an attribute called "costo mensile" and then, describing the
    calculation it wanted, referred to it as "costo mensile (39€)". The two are
    the same thing to a reader and different strings to a lookup, so the
    figure would simply not have been worked out.

    Asking the model to repeat a label exactly is asking it to be a database
    key, which it is not. It names things; identity is assigned here, handed
    back to it, and quoted back by it. A label can then be rewritten, improved
    or translated between one step and the next without breaking anything,
    because nothing downstream ever reads it.

    Attributes that mean the same thing across alternatives share one id —
    that shared identity is what makes two options comparable at all, and it
    is what lets one constraint apply to all of them.
    """

    id: str = Field(default_factory=new_attribute_id)
    name: str = Field(min_length=1, max_length=120)
    # Kept as two shapes: what it says, and — when it is a quantity — what it
    # is worth, so the code can compute and compare with it.
    value: str = Field(default="", max_length=300)
    number: Optional[float] = None
    unit: str = Field(default="", max_length=40)
    # Where this came from: a source id from a research run, a document, or the
    # person. A fact with no origin is not usable in a recommendation.
    source_ids: List[str] = Field(default_factory=list, max_length=6)
    stated_by_user: bool = False


class Alternative(BaseModel):
    """One of the things being chosen between."""

    id: str = Field(default_factory=new_alternative_id)
    name: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=400)
    attributes: List[Attribute] = Field(default_factory=list, max_length=20)
    # Which research run, if any, this came out of.
    research_run_id: Optional[str] = None

    def attribute(self, attribute_id: str) -> Optional[Attribute]:
        """
        By identity, and only by identity.

        No case folding, no partial match, no "the closest one": a reference
        that does not resolve is a reference that was not made, and the caller
        says so instead of guessing which field was meant.
        """
        for item in self.attributes:
            if item.id == attribute_id:
                return item
        return None


class ComparisonCriterion(BaseModel):
    """
    Something that matters here, decided here.

    Every field is written per decision. Two decisions about the same subject on
    different days may weigh differently, and decisions about different parts of
    a life share nothing but this class.
    """

    name: str = Field(min_length=1, max_length=120)
    why_it_matters: str = Field(default="", max_length=400)
    importance: Importance = "moderate"
    # What about this person makes it matter as much as it does. Empty when the
    # criterion is general rather than personal.
    personal_basis: str = Field(default="", max_length=300)
    # Which attribute answers it, by id, when one does.
    attribute_id: str = Field(default="", max_length=64)


class Constraint(BaseModel):
    """
    A condition that is not negotiable, expressed so the code can check it.

    The model decides that something is a constraint rather than a preference
    — that is a judgement about somebody's life. What it cannot be trusted to
    do reliably is arithmetic, so it states the relation and the code evaluates
    it: `attribute <= value`. AI says what is absolute; code says who breaches
    it; AI says what that means for the decision.
    """

    name: str = Field(min_length=1, max_length=120)
    # The field it applies to, by id. A constraint that named its field in
    # prose could be broken by rewording it — "prezzo mensile" against "prezzo
    # al mese" — and a requirement that silently stops being checked is worse
    # than one that was never stated.
    attribute_id: str = Field(min_length=1, max_length=64)
    operator: Operator
    value: str = Field(default="", max_length=200)
    number: Optional[float] = None
    unit: str = Field(default="", max_length=40)
    why: str = Field(default="", max_length=300)
    # What of this person's situation makes it absolute.
    personal_basis: str = Field(default="", max_length=300)


class Computation(BaseModel):
    """
    A number worth working out, named by the model and calculated by the code.

    The model is good at knowing that a monthly figure has to become an annual
    one before two options can be compared, and unreliable at doing the
    multiplication. So it says which operation over which operands, and the
    arithmetic happens in Python.
    """

    name: str = Field(min_length=1, max_length=120)
    operation: Operation
    # Attribute ids, or literal numbers. Never labels.
    operands: List[str] = Field(default_factory=list, max_length=6)
    unit: str = Field(default="", max_length=40)
    why: str = Field(default="", max_length=300)
    # Filled by the code, never by the model.
    result: Optional[float] = None
    failed_reason: str = Field(default="", max_length=200)
    # Which alternative it was worked out for, and what each input actually
    # was: the numbers that went in, and where they came from.
    alternative_id: str = ""
    inputs: List[Dict[str, Any]] = Field(default_factory=list, max_length=6)


class ConstraintCheck(BaseModel):
    """The code's answer about one constraint on one alternative."""

    alternative_id: str
    constraint_name: str
    # What was read, and from where, so a result can be traced back to the
    # fact it rests on without going looking by name.
    attribute_id: str = ""
    source_ids: List[str] = Field(default_factory=list, max_length=6)
    stated_by_user: bool = False
    satisfied: Optional[bool] = None
    observed: str = Field(default="", max_length=200)
    # When it could not be checked at all — the attribute is missing, or is not
    # a number. Unknown is not the same as breached, and saying so is the whole
    # difference between excluding something and not knowing about it.
    reason: str = Field(default="", max_length=200)


class AlternativeAssessment(BaseModel):
    """What the model makes of one alternative, once the facts are in."""

    alternative_id: str
    # In words. Never a score.
    strengths: List[str] = Field(default_factory=list, max_length=6)
    weaknesses: List[str] = Field(default_factory=list, max_length=6)
    excluded: bool = False
    excluded_because: str = Field(default="", max_length=300)
    # What is still unknown about this one specifically.
    missing: List[str] = Field(default_factory=list, max_length=5)


class TradeOff(BaseModel):
    """
    Two things that cannot both be maximised.

    Kept as its own object because flattening it into an order is how a
    comparison stops being useful: "A is cheaper, B costs more and removes a
    risk that matters to you" is the answer, not a step towards one.
    """

    between: List[str] = Field(default_factory=list, max_length=4)
    about: str = Field(min_length=1, max_length=300)
    # Which way it goes for each side.
    detail: str = Field(default="", max_length=600)
    # What about this person decides it, if anything does.
    decided_by: str = Field(default="", max_length=300)


class ConditionalChoice(BaseModel):
    """"If what matters most to you is X, then this one."" """

    condition: str = Field(min_length=1, max_length=300)
    alternative_id: str = Field(min_length=1, max_length=64)
    because: str = Field(default="", max_length=400)


class Recommendation(BaseModel):
    """
    What ORA would say, and why, and how firmly.

    `verdict` may be `insufficient`, and that is a real answer: choosing
    anyway, because a recommendation was asked for, is the failure this field
    exists to make expressible.
    """

    verdict: Verdict = "insufficient"
    confidence: Confidence = "weak"
    # For a clear choice. Empty otherwise.
    chosen_alternative_id: Optional[str] = None
    # What ORA would say out loud, in Italian, to this person.
    message: str = Field(default="", max_length=2000)
    # The handful of things that actually decided it.
    deciding_factors: List[str] = Field(default_factory=list, max_length=6)
    # When it depends on what they care about most.
    conditional: List[ConditionalChoice] = Field(default_factory=list, max_length=4)
    # What is still open, and what would settle it.
    unresolved: List[str] = Field(default_factory=list, max_length=6)
    needed_to_decide: List[str] = Field(default_factory=list, max_length=5)


class ComparisonRun(BaseModel):
    """One decision, with everything that went into it."""

    id: str = Field(default_factory=new_run_id)
    user_id: str
    # The work this belongs to, carried through so a comparison happens inside
    # the reasoning that asked for it and never starts anything of its own.
    session_id: Optional[str] = None
    plan_id: Optional[str] = None
    plan_item_id: Optional[str] = None
    situation_ref: Optional[str] = None

    need: ComparisonNeed
    alternatives: List[Alternative] = Field(default_factory=list)
    criteria: List[ComparisonCriterion] = Field(default_factory=list)
    constraints: List[Constraint] = Field(default_factory=list)
    computations: List[Computation] = Field(default_factory=list)
    checks: List[ConstraintCheck] = Field(default_factory=list)
    assessments: List[AlternativeAssessment] = Field(default_factory=list)
    trade_offs: List[TradeOff] = Field(default_factory=list)
    recommendation: Optional[Recommendation] = None

    # Evidence is referenced, never copied: V3.4 owns it.
    research_run_ids: List[str] = Field(default_factory=list, max_length=8)
    # What of this person was actually used, so a recommendation can say which
    # part of their situation it rests on — and so it can be seen that the rest
    # was not sent anywhere.
    personal_context_used: List[str] = Field(default_factory=list, max_length=12)

    status: Literal["completed", "insufficient", "failed"] = "failed"
    outcome_note: str = ""

    # Version, so a later run can say what changed and why. Nothing in this
    # phase acts on it; the data has to allow it later.
    supersedes_run_id: Optional[str] = None
    revision: int = 1
    changed_because: str = Field(default="", max_length=400)

    started_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    failures: List[str] = Field(default_factory=list)

    def assign_attribute_identity(self) -> None:
        """
        Give every stated fact an id, and give the same field one id.

        Two alternatives describing the same thing under the same label are
        describing the same field, and sharing an id is what makes them
        comparable — and what lets a single requirement be checked against
        both. The match is exact and happens once, here, at the only moment a
        label is ever read: nothing afterwards looks at one.

        A label that differs between alternatives stays a separate field. That
        is honest rather than clever: a requirement will then simply not be
        checkable on the other one, and will say so.
        """
        by_label: Dict[str, str] = {}
        for alternative in self.alternatives:
            for attribute in alternative.attributes:
                shared = by_label.get(attribute.name)
                if shared is None:
                    by_label[attribute.name] = attribute.id
                else:
                    attribute.id = shared

    def attribute_by_id(self, attribute_id: str) -> Optional[Attribute]:
        for alternative in self.alternatives:
            found = alternative.attribute(attribute_id)
            if found is not None:
                return found
        return None

    def alternative(self, alternative_id: str) -> Optional[Alternative]:
        for item in self.alternatives:
            if item.id == alternative_id:
                return item
        return None

    def cited_source_ids(self) -> List[str]:
        """Every source any stated fact rests on."""
        out: List[str] = []
        for alternative in self.alternatives:
            for attribute in alternative.attributes:
                for source_id in attribute.source_ids:
                    if source_id not in out:
                        out.append(source_id)
        return out

    def to_reasoning_payload(self) -> Dict[str, Any]:
        """What goes back to the reasoning that asked for the comparison."""
        recommendation = self.recommendation
        return {
            "comparison_run_id": self.id,
            "decision": self.need.decision,
            "status": self.status,
            "outcome_note": self.outcome_note,
            "verdict": recommendation.verdict if recommendation else "insufficient",
            "confidence": recommendation.confidence if recommendation else "weak",
            "message": recommendation.message if recommendation else "",
            "deciding_factors": recommendation.deciding_factors if recommendation else [],
            "conditional": [
                {
                    "condition": choice.condition,
                    "alternative": (self.alternative(choice.alternative_id) or Alternative(name="?")).name,
                    "because": choice.because,
                }
                for choice in (recommendation.conditional if recommendation else [])
            ],
            "chosen": (
                (self.alternative(recommendation.chosen_alternative_id) or Alternative(name="?")).name
                if recommendation and recommendation.chosen_alternative_id
                else None
            ),
            "alternatives": [
                {
                    "name": alternative.name,
                    "excluded": next(
                        (a.excluded for a in self.assessments if a.alternative_id == alternative.id),
                        False,
                    ),
                }
                for alternative in self.alternatives
            ],
            "trade_offs": [{"about": t.about, "detail": t.detail} for t in self.trade_offs],
            "unresolved": recommendation.unresolved if recommendation else [],
            "needed_to_decide": recommendation.needed_to_decide if recommendation else [],
            "research_run_ids": self.research_run_ids,
            # Said plainly, because the reasoning must not narrate a comparison
            # that did not happen.
            "comparison_is_real": bool(self.alternatives and self.recommendation),
        }
