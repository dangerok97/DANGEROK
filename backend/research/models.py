"""
What a piece of research is, once it has happened.

Every structure here is something the model produced and the code only checked
the shape of. There is no field whose value is decided by a rule: no domain, no
query template, no scoring of sources, no threshold that declares evidence
sufficient. The code owns identity, timestamps, ownership and limits; the
meaning is the model's throughout.

The shape follows the way a question actually gets answered:

    ResearchNeed        what the reasoning found it could not answer from
                        inside, declared by the reasoning itself
    ResearchPlan        what would have to be true to answer it, and what to
                        go and look for
    EvidenceSource      something that was actually read, with what is known
                        about when it was written and when it was fetched
    EvidenceClaim       a statement, tied to the sources that support it
    ResearchAssessment  the model's own reading of what it now has: enough,
                        not enough, or contradictory — and what to do next
    ResearchSynthesis   the answer handed back to the reasoning that asked
    ResearchRun         all of it, persisted, so it can be cited and reused

`ResearchRun` is deliberately not Life Memory. "The rate on this product is X
today" is something the world said this morning, not something true about a
person, and the two must never end up in the same store.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# Where a run can end. `partial` and `insufficient` are outcomes, not errors:
# they are what honesty looks like when the world did not answer.
RunStatus = Literal["completed", "partial", "insufficient", "failed"]

# What the model concluded about the evidence in front of it.
Sufficiency = Literal["sufficient", "insufficient", "conflicted"]

# Who a statement is about, which decides what it takes to be allowed to make
# it. Found in QA: ORA read the market correctly and then wrote "essendo
# dipendente a tempo indeterminato hai un profilo lavorativo solido e standard
# per l'accesso al credito" — a verdict on a person, from evidence about a
# market, holding one fact about them and knowing nothing of their income or
# what else they owe.
#
#   external_fact       what the sources say. Rests on the sources.
#   general_inference   what is generally true of situations like this. Says
#                       so, and stays general.
#   person_specific     a conclusion about *this* person. Rests on the sources
#                       *and* on enough about them, and the model says which
#                       facts about them it used.
ClaimScope = Literal["external_fact", "general_inference", "person_specific"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    return f"rr_{uuid.uuid4().hex[:12]}"


def new_source_id() -> str:
    return f"rs_{uuid.uuid4().hex[:10]}"


def new_claim_id() -> str:
    return f"rc_{uuid.uuid4().hex[:10]}"


class ResearchNeed(BaseModel):
    """
    The reasoning saying it has reached the edge of what it knows.

    This is the whole of the "should I go and look?" decision, and it is the
    model's: nothing infers it from a plan type, a document type, a domain or a
    keyword. `question` is what it wants answered, in its own words.
    """

    question: str = Field(min_length=1, max_length=400)
    # Why answering it moves the current step forward. Kept because a research
    # run that cannot say what it was for is a run nobody can judge.
    purpose: str = Field(default="", max_length=300)
    # What the reasoning already believes, so the planner does not go looking
    # for what ORA has been told.
    already_known: List[str] = Field(default_factory=list, max_length=12)


class ResearchQuestion(BaseModel):
    """One thing to find out, and what would count as finding it out."""

    ref: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=300)
    # The model's own words for what an answer looks like. Never a schema.
    evidence_needed: str = Field(default="", max_length=300)
    # Searches the model wants run for this question. It decides how many,
    # how they are worded, and whether they are narrowed to a place.
    queries: List[str] = Field(default_factory=list, max_length=6)
    # What kind of source would settle *this* question, in the model's words.
    #
    # Per question and not per plan, because fitness belongs to the claim. One
    # question can need what a rule says — which only whoever makes the rule
    # can tell you — while the next needs what things actually cost, which only
    # people selling them publish. Found in QA: a run about a driving licence
    # answered the legally fixed parts from editorial write-ups, which is where
    # market prices live and not where requirements do.
    source_fitness: str = Field(default="", max_length=300)


class ResearchPlan(BaseModel):
    """
    How the model intends to answer the need.

    Every field is generated per run. Two runs about the same subject on
    different days may plan differently, and runs about different parts of a
    life share nothing but this class.
    """

    goal: str = Field(min_length=1, max_length=400)
    reason: str = Field(default="", max_length=300)
    known_context: List[str] = Field(default_factory=list, max_length=12)
    unknowns: List[str] = Field(default_factory=list, max_length=10)
    questions: List[ResearchQuestion] = Field(default_factory=list, max_length=6)
    # What kind of source would answer this well — described, not listed. The
    # model may say "the supervisory authority's own published figures"; it
    # never names a site the code then privileges.
    preferred_source_characteristics: List[str] = Field(
        default_factory=list, max_length=6
    )
    # How recent the evidence has to be *for this goal*, in the model's words,
    # plus how long its own answer should be trusted. A rate and a street
    # address do not age at the same speed, and nothing here assumes they do.
    freshness_requirement: str = Field(default="", max_length=200)
    valid_for_hours: Optional[float] = Field(default=None, ge=0.0, le=8760.0)
    # Where the answer has to apply, when that matters at all.
    geographic_scope: Optional[str] = Field(default=None, max_length=160)
    # What the model would accept as a reason to stop looking.
    stop_condition: str = Field(default="", max_length=300)
    # What of the person's situation may go into a public query, chosen by the
    # model. The sanitizer is a backstop under this, not a substitute for it.
    disclosable_context: List[str] = Field(default_factory=list, max_length=8)
    # What must not leave, and why it is not needed out there.
    withheld_context: List[str] = Field(default_factory=list, max_length=8)


class EvidenceSource(BaseModel):
    """Something that was actually retrieved."""

    source_id: str = Field(default_factory=new_source_id)
    url: str = ""
    title: str = ""
    publisher: str = ""
    snippet: str = ""
    # Observable, so the code fills them: when it was fetched, which query
    # found it, what the deterministic authority band says.
    retrieved_at: str = Field(default_factory=_now)
    found_by_query: str = ""
    authority_hint: str = "UNKNOWN"
    # The model's own reading of the source, written after seeing it.
    published_at: Optional[str] = Field(default=None, max_length=60)
    source_kind: Optional[str] = Field(default=None, max_length=80)
    answers_the_question: Optional[bool] = None
    relevance_note: str = Field(default="", max_length=300)


class EvidenceClaim(BaseModel):
    """
    A statement the research established, and what holds it up.

    A claim with no `supported_by` is not a claim; it is the model talking. The
    service drops those rather than letting them reach a person as findings.
    """

    claim_id: str = Field(default_factory=new_claim_id)
    statement: str = Field(min_length=1, max_length=600)
    supported_by: List[str] = Field(default_factory=list, max_length=8)
    observed_at: str = Field(default_factory=_now)
    # Who it is about, and — when it is about this person — what of theirs it
    # rests on. Which facts are needed is the model's judgement for that
    # particular conclusion, never a list kept here.
    scope: ClaimScope = "external_fact"
    person_evidence_used: List[str] = Field(default_factory=list, max_length=8)
    # The model's own confidence in words, and whether it disagrees with
    # something else found in the same run.
    certainty: str = Field(default="", max_length=120)
    conflicts_with: List[str] = Field(default_factory=list, max_length=6)


class ResearchConflict(BaseModel):
    """Two sources that cannot both be right, described by the model."""

    about: str = Field(min_length=1, max_length=300)
    positions: List[str] = Field(default_factory=list, max_length=4)
    source_ids: List[str] = Field(default_factory=list, max_length=8)
    # Which reading the model finds more applicable, and why — or that it
    # cannot tell, which is an acceptable answer.
    resolution: str = Field(default="", max_length=400)
    resolved: bool = False


class ResearchAssessment(BaseModel):
    """The model reading its own evidence: is this enough?"""

    sufficiency: Sufficiency = "insufficient"
    reason: str = Field(default="", max_length=400)
    missing_evidence: List[str] = Field(default_factory=list, max_length=6)
    conflicts: List[ResearchConflict] = Field(default_factory=list, max_length=4)
    # If it is not enough, what it wants run next. Written by the model, in
    # the same breath as saying why what it has does not do.
    next_queries: List[str] = Field(default_factory=list, max_length=5)


class ResearchSynthesis(BaseModel):
    """What goes back to the reasoning that asked for this."""

    answer: str = Field(default="", max_length=2000)
    claims: List[EvidenceClaim] = Field(default_factory=list, max_length=12)
    unresolved: List[str] = Field(default_factory=list, max_length=6)
    # What the model would say out loud about how solid this is. Not a number,
    # and not shown as one.
    caveats: List[str] = Field(default_factory=list, max_length=6)


class ResearchRun(BaseModel):
    """One question, asked of the world, with everything it produced."""

    id: str = Field(default_factory=new_run_id)
    user_id: str
    # Where in the person's life this happened, so the answer returns to the
    # same reasoning rather than starting something new.
    session_id: Optional[str] = None
    plan_id: Optional[str] = None
    plan_item_id: Optional[str] = None
    situation_ref: Optional[str] = None
    reasoning_epoch: Optional[int] = None

    need: ResearchNeed
    plan: Optional[ResearchPlan] = None
    sources: List[EvidenceSource] = Field(default_factory=list)
    assessments: List[ResearchAssessment] = Field(default_factory=list)
    synthesis: Optional[ResearchSynthesis] = None

    status: RunStatus = "failed"
    # Why it ended where it did, in a sentence a person could read.
    outcome_note: str = ""

    # Bookkeeping the code owns.
    queries_run: List[str] = Field(default_factory=list)
    iterations: int = 0
    started_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    valid_until: Optional[str] = None
    failures: List[str] = Field(default_factory=list)

    def citable_sources(self) -> List[Dict[str, str]]:
        """
        The sources a person may be shown: the ones a claim actually rests on.

        Anything retrieved and then not used is not a citation. Showing it
        would be claiming to have relied on something ORA ignored.
        """
        used: set[str] = set()
        for claim in (self.synthesis.claims if self.synthesis else []):
            used.update(claim.supported_by)
        out: List[Dict[str, str]] = []
        for source in self.sources:
            if source.source_id not in used:
                continue
            if not (source.title or source.url):
                continue
            out.append({"title": (source.title or source.url)[:80], "url": source.url[:300]})
        return out

    def to_reasoning_payload(self) -> Dict[str, Any]:
        """What the reasoning that asked gets back."""
        return {
            "research_run_id": self.id,
            "question": self.need.question,
            "status": self.status,
            "outcome_note": self.outcome_note,
            "answer": self.synthesis.answer if self.synthesis else "",
            "claims": [
                {
                    "statement": c.statement,
                    "supported_by": c.supported_by,
                    "certainty": c.certainty,
                }
                for c in (self.synthesis.claims if self.synthesis else [])
            ],
            "unresolved": self.synthesis.unresolved if self.synthesis else [],
            "caveats": self.synthesis.caveats if self.synthesis else [],
            "conflicts": [
                {"about": c.about, "positions": c.positions, "resolution": c.resolution}
                for a in self.assessments for c in a.conflicts
            ][:4],
            "sources": [
                {
                    "source_id": s.source_id,
                    "title": s.title[:120],
                    "url": s.url[:300],
                    "publisher": s.publisher[:80],
                    "published_at": s.published_at,
                    "retrieved_at": s.retrieved_at,
                }
                for s in self.sources[:8]
            ],
            "retrieved_at": self.started_at,
            "valid_until": self.valid_until,
            # Said plainly, because the reasoning must not narrate a search
            # that did not happen.
            "evidence_is_real": bool(self.sources),
        }
