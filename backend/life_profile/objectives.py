"""
What ORA is trying to find out, and whether it has.

A knowledge objective is one thing worth knowing about a life — where someone
lives, whether they own the place, whether there is still a mortgage on it. It
is not a form field and it is not a question: several objectives are often
resolved by one sentence, and one objective can be resolved by a document
nobody was asked for.

The catalogue is `ai_life_strategist.knowledge_gap.DOMAIN_GAPS`, which already
carries a weight (`information_gain`) and dependencies (`when`). This module
reads it; it does not restate it.

The five states an objective can be in are the whole model:

    known           ORA has it, from the person, a document, or a connected
                    source. A "no" is knowledge: "non ho l'auto" is an answer.
    inferred        ORA believes it from something adjacent, and says so.
    declined        the person would rather not say. That is an answer too, and
                    it is not asked again.
    not_applicable  the objective does not apply to this life — no vehicle, no
                    mortgage — so it is not a hole.
    unknown         nobody has said, and it still could be known.

Skipping is deliberately not a state. "Più tardi" leaves an objective exactly
where it was: unknown, askable, and counted as missing. That is the difference
between postponing and answering, and the completeness figure has to respect
it or the number becomes a measure of how many questions were dismissed.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, Field

from life_profile.areas import LifeArea, area_for_domain

ObjectiveState = Literal["known", "inferred", "declined", "not_applicable", "unknown"]

# The only state that leaves the reckoning entirely.
#
# `not_applicable` is the one thing that is genuinely not missing knowledge:
# there is no mortgage to know about, no vehicle to insure, and counting them
# would hold a percentage down for a life that simply does not contain them.
#
# `declined` is different and the distinction matters. Someone who would rather
# not discuss their savings has told ORA something about themselves, but they
# have not told it the thing — ORA still does not know, and still cannot use
# it. So it stays in the denominator, never enters the numerator, and is never
# raised again. Letting it out would mean the percentage rose because somebody
# refused, which is the one reading of this number that would be a lie.
_OUT_OF_RECKONING: Tuple[ObjectiveState, ...] = ("not_applicable",)


class KnowledgeObjective(BaseModel):
    """One thing worth knowing, and where ORA stands on it."""

    ref: str
    area_id: str
    domain: str
    label: str
    weight: float = 0.5
    # Some things are better read than asked. When true, ORA offers the
    # document instead of interrogating.
    prefer_document: bool = False
    document_type: Optional[str] = None
    # Any one of these being known makes this objective relevant. Empty means
    # it is always relevant.
    depends_on: Tuple[str, ...] = ()
    # Other keys that resolve this same thing. The early part of a life gets
    # captured under the Minimum Life Context's own names — where somebody
    # lives arrives as `mlc.life_places.home` or as `casa.citta` depending on
    # how they said it — and an objective that only recognised one of them
    # would report a profile emptier than it is.
    satisfied_by: Tuple[str, ...] = ()
    sensitivity: str = "normal"

    # Filled by resolution.
    state: ObjectiveState = "unknown"
    provenance: Optional[str] = None
    note: str = ""

    @property
    def resolved(self) -> bool:
        return self.state in ("known", "inferred")

    @property
    def counts_toward_completeness(self) -> bool:
        """
        Whether this objective is part of what would help ORA understand.

        Declined is included on purpose: ORA does not know it, so the figure
        must not pretend otherwise.
        """
        return self.state not in _OUT_OF_RECKONING


def _catalogue() -> Dict[str, List[Dict[str, Any]]]:
    from ai_life_strategist.knowledge_gap import DOMAIN_GAPS

    return DOMAIN_GAPS


# The first thing worth knowing about a part of a life, and where the existing
# engine already records it. These are not new questions — the Minimum Life
# Context has asked them since the first version of the setup — they are a
# statement of which area each nucleus informs, and how much it explains.
_FOUNDATIONS: Dict[str, Tuple[str, str, float]] = {
    # area_id: (mlc nucleus, label, weight)
    "casa": ("life_places", "dove vivi", 1.0),
    "lavoro": ("current_situation", "di cosa ti occupi", 1.0),
    "famiglia": ("responsibilities", "di chi ti prendi cura", 0.9),
}


def _foundation(life_area: LifeArea) -> Optional[KnowledgeObjective]:
    spec = _FOUNDATIONS.get(life_area.id)
    if not spec:
        return None
    nucleus, label, weight = spec
    try:
        from ai_life_strategist.minimum_life_context import (
            NUCLEUS_EVIDENCE_KEYS,
            NUCLEUS_GAP_KEY,
        )
    except Exception:
        return None
    keys = tuple(NUCLEUS_EVIDENCE_KEYS.get(nucleus, ()) or ())
    ref = NUCLEUS_GAP_KEY.get(nucleus) or (keys[0] if keys else "")
    if not ref:
        return None
    return KnowledgeObjective(
        ref=ref,
        area_id=life_area.id,
        domain=life_area.domains[0],
        label=label,
        weight=weight,
        satisfied_by=keys,
        sensitivity=life_area.sensitivity,
    )


# The same knowledge, arriving under another name.
#
# A document's extraction writes what it found in its own vocabulary — a bill
# becomes `doc.bolletta` or `doc.fattura` — while the objective it answers is
# called "utenze / bollette". Found live: a real bill was uploaded, the
# pipeline genuinely read the supplier, the amount and the due date, and the
# profile did not move at all.
#
# These are aliases, not new objectives: each one is another way the *same*
# thing arrives. Anything that would merely be adjacent is left out — an
# invoice total is not a statement about somebody's recurring expenses, and
# pretending otherwise would put a number on the screen that nobody said.
_ALSO_SATISFIED_BY: Dict[str, Tuple[str, ...]] = {
    "casa.utenze": ("doc.bolletta", "doc.fattura"),
    "casa.assicurazione": ("doc.polizza_casa",),
    "auto.assicurazione_scadenza": ("doc.polizza_auto",),
    "assicurazioni.tipo": ("doc.polizza", "doc.polizza_casa", "doc.polizza_auto"),
    "salute.visita": ("doc.referti",),
}


def objectives_for_area(life_area: LifeArea) -> List[KnowledgeObjective]:
    """Every objective this area draws from the existing gap catalogue."""
    catalogue = _catalogue()
    out: List[KnowledgeObjective] = []
    base = _foundation(life_area)
    if base is not None:
        out.append(base)

    # The guided setup's own objectives. They carry their own weights and
    # their own dependencies, and they are the bulk of what the first
    # conversation establishes — counting the gap catalogue alone would report
    # a profile far emptier than it is.
    try:
        from life_profile.guided import for_area as guided_for_area

        for g in guided_for_area(life_area.id):
            out.append(
                KnowledgeObjective(
                    ref=g.id,
                    area_id=life_area.id,
                    domain=str(g.id).split(".", 1)[0],
                    label=g.question,
                    weight=g.weight,
                    prefer_document=g.control == "document_upload",
                    document_type=g.document_type,
                    depends_on=tuple(c.key for c in g.depends_on),
                    satisfied_by=_ALSO_SATISFIED_BY.get(g.id, ()),
                    sensitivity=g.sensitivity,
                )
            )
    except Exception:  # pragma: no cover - the catalogue is not optional
        pass
    for domain in life_area.domains:
        for raw in catalogue.get(domain, []) or []:
            ref = str(raw.get("key") or "").strip()
            if not ref:
                continue
            out.append(
                KnowledgeObjective(
                    ref=ref,
                    area_id=life_area.id,
                    domain=domain,
                    label=str(raw.get("label") or ref),
                    weight=float(raw.get("information_gain") or 0.5),
                    prefer_document=bool(raw.get("prefer_document")),
                    document_type=raw.get("document_type"),
                    depends_on=tuple(str(w) for w in (raw.get("when") or ())),
                    satisfied_by=_ALSO_SATISFIED_BY.get(ref, ()),
                    sensitivity=life_area.sensitivity,
                )
            )

    seen: Dict[str, KnowledgeObjective] = {}
    for item in out:
        # A ref declared in both places is one thing worth knowing, not two.
        seen.setdefault(item.ref, item)
    return list(seen.values())


def objective_area(ref: str) -> Optional[str]:
    """Which area an objective belongs to, by its domain prefix or its catalogue entry."""
    catalogue = _catalogue()
    for domain, items in catalogue.items():
        for raw in items or []:
            if str(raw.get("key") or "") == ref:
                found = area_for_domain(domain)
                return found.id if found else None
    prefix = (ref or "").split(".", 1)[0]
    found = area_for_domain(prefix)
    return found.id if found else None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


# What someone writes when the answer is "there isn't one". The setup stores a
# direct answer as the sentence the person typed, so this has to read sentences
# and not just flags.
_NEGATIVE_OPENERS = (
    "no",
    "non ho",
    "non ne ho",
    "non possiedo",
    "non ce l",
    "nessun",
    "niente",
    "non abbiamo",
    "non uso",
    "none",
)

# "Non lo so" is not a "no". Someone who does not know has told ORA nothing
# about their life, and counting it as an answer would resolve an objective
# nobody resolved.
_IGNORANCE = ("non lo so", "non so", "non ricordo", "non saprei", "boh")


def _is_negative(value: Any) -> bool:
    """A stated "no", as opposed to nothing said — or to not knowing.

    The distinction matters twice over: the objective itself is resolved, and
    everything that depended on it stops applying. Treating a "no" as absence
    is what left Mobilità permanently unfinished for someone who does not own
    a car.
    """
    if value is False:
        return True
    if not isinstance(value, str):
        return False
    text = " ".join(value.strip().lower().split())
    # The profile stores values as text, so a boolean arrives as "False".
    if text in ("false", "no", "0"):
        return True
    if not text:
        return False
    if any(text.startswith(x) for x in _IGNORANCE):
        return False
    stripped = text.rstrip(".!… ")
    if stripped in {"no", "nessuno", "nessuna", "none", "assente"}:
        return True
    # A sentence that opens with a negation is a negative answer: "No, non ho
    # l'auto", "Non possiedo veicoli". Anything longer than a short reply is
    # left alone — a paragraph is a description, not a denial.
    if len(stripped) <= 120 and any(
        stripped.startswith(x) for x in _NEGATIVE_OPENERS
    ):
        return True
    return False


def _is_present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def resolve(
    objectives: Sequence[KnowledgeObjective],
    *,
    facts: Dict[str, Any],
    provenance: Optional[Dict[str, str]] = None,
    declined_refs: Optional[Iterable[str]] = None,
    not_applicable_refs: Optional[Iterable[str]] = None,
    inferred_refs: Optional[Iterable[str]] = None,
) -> List[KnowledgeObjective]:
    """
    Put every objective into exactly one state.

    Order matters and is deliberate: what the person said outranks what the
    system worked out, and a dependency that has been answered "no" removes its
    dependants before anything else gets to call them missing.
    """
    declined = {str(r) for r in (declined_refs or ())}
    not_applicable = {str(r) for r in (not_applicable_refs or ())}
    inferred = {str(r) for r in (inferred_refs or ())}
    prov = provenance or {}

    # Facts that were answered in the negative. Anything gated on them no
    # longer applies to this life.
    denied: Set[str] = {k for k, v in (facts or {}).items() if _is_negative(v)}
    present: Set[str] = {k for k, v in (facts or {}).items() if _is_present(v)}

    out: List[KnowledgeObjective] = []
    for obj in objectives:
        item = obj.model_copy(deep=True)
        ref = item.ref
        # Any of the names this thing can arrive under.
        names = (ref,) + tuple(item.satisfied_by)
        said_no = any(n in denied for n in names)
        said_yes = any(n in present for n in names)

        if ref in not_applicable:
            item.state = "not_applicable"
            item.note = "non si applica"
        elif item.depends_on and all(d in denied for d in item.depends_on):
            # Every gate was answered "no". This is not a hole in the profile.
            item.state = "not_applicable"
            item.note = "non si applica"
        elif said_no:
            # A stated "no" is knowledge about this life.
            item.state = "known"
            item.provenance = next((prov.get(n) for n in names if prov.get(n)), None)
            item.note = "risposta negativa"
        elif said_yes:
            hit = next((n for n in names if n in present), ref)
            item.state = "inferred" if hit in inferred else "known"
            item.provenance = prov.get(hit)
        elif ref in declined:
            item.state = "declined"
            item.note = "preferisce non dirlo"
        else:
            item.state = "unknown"
        out.append(item)
    return out


def applicable(objectives: Sequence[KnowledgeObjective], facts: Dict[str, Any]) -> List[KnowledgeObjective]:
    """
    The objectives that are relevant right now.

    An objective whose dependency has not been settled yet is latent: ORA does
    not know whether there is a mortgage to ask about, so counting it as
    missing would hold a percentage down for a question nobody should be asked.
    It appears the moment its gate is answered, which is why the shape of an
    area changes as a conversation goes on.
    """
    present = {k for k, v in (facts or {}).items() if _is_present(v)}
    out: List[KnowledgeObjective] = []
    for obj in objectives:
        if obj.state == "not_applicable":
            continue
        # Something ORA already knows evidently applies, whatever its gate says.
        # Found live: a bill was uploaded, the pipeline read the supplier and
        # the amount, and the profile did not move — because the objective it
        # answered was still waiting for a question about home ownership that
        # nobody had asked. Knowledge arriving from anywhere has to count.
        if obj.resolved:
            out.append(obj)
            continue
        if obj.depends_on and not any(d in present for d in obj.depends_on):
            continue
        out.append(obj)
    return out
