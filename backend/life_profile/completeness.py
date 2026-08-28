"""
How much of what would help, ORA actually knows.

The number on the screen is the one thing in this sprint a person will read
literally, so it has to mean something literal. It is not "how much of the form
you filled in" — nobody filled in a form — and it is not a score. It is the
share of what ORA could usefully know about a part of someone's life that it
currently does know, weighted by how much each piece actually helps.

    completeness = Σ weight(known or inferred) / Σ weight(applicable)

Everything interesting is in what "applicable" excludes, and it is exactly two
things:

  - what does not apply to this life (no car, no mortgage) — a life without a
    vehicle is not an incomplete life;
  - what is still latent, because the thing it depends on has not been settled.

What it does **not** exclude is anything ORA simply does not know, however the
person came to leave it unknown. "Più tardi" leaves the hole where it was. So
does "preferisco non dirlo": a refusal is a fact about the conversation, not
about the life, and ORA still cannot use what it was not told. Letting a
declined subject out of the denominator would make the percentage rise because
somebody refused — the one reading of this number that would be a lie.

The three are kept apart deliberately:

    skipped         not now              still counted as missing
    declined        I would rather not   still counted, never asked again
    not applicable  there is none        gone from the reckoning

The formula is deliberately plain arithmetic over structured state. No model
runs to produce it, which is why opening Vita costs a read and not fifty LLM
calls.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field

from life_profile.areas import LifeArea, all_areas
from life_profile.objectives import (
    KnowledgeObjective,
    applicable,
    objectives_for_area,
    resolve,
)

# Where an area stops being "just started" and starts being useful. Chosen to
# match how it reads, not to be precise: below a third ORA has fragments,
# past two thirds it can genuinely help, and 100% is not a goal anybody should
# be pushed toward.
_ENOUGH_TO_HELP = 0.65
_STARTED = 0.30


class AreaCompleteness(BaseModel):
    """What ORA knows about one part of a life, and what it would still help to know."""

    area_id: str
    title: str
    description: str
    icon_key: str
    sensitivity: str
    order: int
    # 0–100, rounded for presentation. Derived, never accepted from a client.
    percent: int = 0
    state: str = "not_started"
    state_label: str = "Non iniziata"
    known_count: int = 0
    applicable_count: int = 0
    declined_count: int = 0
    not_applicable_count: int = 0
    # What ORA would most usefully learn next here, heaviest first. Labels
    # only: these are objectives, not questions — the question is written when
    # it is asked, by guidance, in the moment.
    open_objectives: List[Dict[str, Any]] = Field(default_factory=list)

    @property
    def has_room(self) -> bool:
        return self.percent < 100 and self.applicable_count > 0


class ProfileCompleteness(BaseModel):
    """The whole picture: one figure, and the areas it came from."""

    percent: int = 0
    areas: List[AreaCompleteness] = Field(default_factory=list)
    # Where it would help most to continue. Never random, never always "Casa":
    # the area with the most weight still to learn, preferring one already
    # begun so a person is not bounced between subjects.
    suggested_area_id: Optional[str] = None
    computed_at: Optional[str] = None


def _state_of(percent: int, applicable_count: int, known_count: int) -> tuple[str, str]:
    if applicable_count == 0:
        return "not_applicable", "Non applicabile"
    if known_count == 0:
        return "not_started", "Non iniziata"
    if percent >= int(_ENOUGH_TO_HELP * 100):
        return "known_enough", "Conosciuta"
    if percent >= int(_STARTED * 100):
        return "started", "Buon punto di partenza"
    return "sparse", "Da completare"


def area_completeness(
    life_area: LifeArea,
    *,
    facts: Dict[str, Any],
    provenance: Optional[Dict[str, str]] = None,
    declined_refs: Optional[Iterable[str]] = None,
    not_applicable_refs: Optional[Iterable[str]] = None,
    inferred_refs: Optional[Iterable[str]] = None,
) -> AreaCompleteness:
    resolved = resolve(
        objectives_for_area(life_area),
        facts=facts,
        provenance=provenance,
        declined_refs=declined_refs,
        not_applicable_refs=not_applicable_refs,
        inferred_refs=inferred_refs,
    )
    live = applicable(resolved, facts)
    countable = [o for o in live if o.counts_toward_completeness]

    total = sum(o.weight for o in countable)
    got = sum(o.weight for o in countable if o.resolved)
    percent = int(round(100 * got / total)) if total > 0 else 0
    # A single unanswered thing should not read as finished.
    if percent == 100 and any(not o.resolved for o in countable):
        percent = 99

    known_count = sum(1 for o in countable if o.resolved)
    state, label = _state_of(percent, len(countable), known_count)

    # What ORA would still usefully learn. Declined objectives are counted as
    # missing — ORA does not know them — but they are never offered again: the
    # person already answered that question, and the answer was no.
    open_items = sorted(
        (o for o in countable if o.state == "unknown"),
        key=lambda o: (-o.weight, o.ref),
    )
    return AreaCompleteness(
        area_id=life_area.id,
        title=life_area.title,
        description=life_area.description,
        icon_key=life_area.icon_key,
        sensitivity=life_area.sensitivity,
        order=life_area.order,
        percent=percent,
        state=state,
        state_label=label,
        known_count=known_count,
        applicable_count=len(countable),
        declined_count=sum(1 for o in resolved if o.state == "declined"),
        not_applicable_count=sum(1 for o in resolved if o.state == "not_applicable"),
        open_objectives=[
            {
                "ref": o.ref,
                "label": o.label,
                "weight": round(o.weight, 2),
                "prefer_document": o.prefer_document,
                "document_type": o.document_type,
            }
            for o in open_items[:6]
        ],
    )


def profile_completeness(
    *,
    facts: Dict[str, Any],
    provenance: Optional[Dict[str, str]] = None,
    declined_refs: Optional[Iterable[str]] = None,
    not_applicable_refs: Optional[Iterable[str]] = None,
    inferred_refs: Optional[Iterable[str]] = None,
    touched_area_ids: Optional[Iterable[str]] = None,
) -> ProfileCompleteness:
    areas = [
        area_completeness(
            a,
            facts=facts,
            provenance=provenance,
            declined_refs=declined_refs,
            not_applicable_refs=not_applicable_refs,
            inferred_refs=inferred_refs,
        )
        for a in all_areas()
    ]

    # The overall figure is weighted by how much each area matters, so knowing
    # where someone lives moves it more than knowing which magazines they
    # subscribe to. Areas with nothing applicable drop out entirely rather than
    # counting as zero.
    by_id = {a.id: a for a in all_areas()}
    live = [a for a in areas if a.applicable_count > 0]
    denom = sum(by_id[a.area_id].weight for a in live)
    num = sum(by_id[a.area_id].weight * (a.percent / 100.0) for a in live)
    overall = int(round(100 * num / denom)) if denom > 0 else 0

    return ProfileCompleteness(
        percent=overall,
        areas=areas,
        suggested_area_id=_suggest(areas, touched_area_ids or ()),
    )


def _suggest(areas: List[AreaCompleteness], touched: Iterable[str]) -> Optional[str]:
    """
    Where to go next — derived from the profile, never a default and never random.

    An area already begun and not yet useful wins: finishing a thought beats
    starting a new one. Otherwise the one with the most weight still to learn.
    """
    started = {str(t) for t in touched}
    by_id = {a.id: a for a in all_areas()}

    def room(a: AreaCompleteness) -> float:
        return by_id[a.area_id].weight * (100 - a.percent) / 100.0

    candidates = [a for a in areas if a.has_room]
    if not candidates:
        return None
    resumable = [
        a for a in candidates
        if a.area_id in started and a.state in ("sparse", "started")
    ]
    pool = resumable or candidates
    return max(pool, key=lambda a: (room(a), -a.order)).area_id
