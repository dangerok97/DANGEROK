"""
Minimum necessary questioning.

Two rules do all the work here.

**Only what blocks.** A variable reaches a person when the next step cannot be
taken without it and ORA could not find it. Everything else — useful, optional,
merely interesting — waits, however much better the answer would be with it.

**One question, not one per field.** Variables that serve the same next step
are asked together, because seven turns to collect seven numbers is an
interrogation and one short request is a conversation. The bundle stays small:
past a handful, a single question stops being compact and becomes a form.

The phrasing is deliberately plain. ORA says what it needs and, when the list
is long or personal, why — once, in a sentence. It does not apologise, does not
explain the mechanism, and never repeats back what it already knows.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from guidance.models import NextStep, Variable
from guidance.wording import is_meta_choice, looks_english

# Above this a bundle stops reading as one question. Related variables past the
# limit wait for the next step rather than being crammed in.
MAX_BUNDLE = 7

# Below this there is nothing to explain: "mutuo o risparmi?" justifies itself.
EXPLAIN_FROM = 3


def _label(v: Variable) -> str:
    return (v.label or v.ref).strip()


def _list_phrase(labels: Sequence[str]) -> str:
    """"a, b, c e d" — an Italian list, not a bulleted form."""
    items = [l for l in labels if l]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} e {items[-1]}"


def select_bundle(blocking: Sequence[Variable]) -> List[Variable]:
    """
    The smallest set that unblocks the next step.

    Ordered so the least personal things come first: a request that opens with
    an income figure reads as an interrogation even when every item in it is
    genuinely needed.
    """
    weight = {"normal": 0, "sensitive": 1, "high": 2}
    ordered = sorted(blocking, key=lambda v: (weight.get(v.sensitivity, 0), _label(v)))
    return list(ordered[:MAX_BUNDLE])


def compose_question(
    bundle: Sequence[Variable],
    *,
    step_title: str = "",
    fallback: str = "",
) -> str:
    """
    What a person actually reads.

    A single variable is asked as itself. Several are asked as one sentence
    naming the step they serve, so the request has a visible point rather than
    arriving as a list of fields.
    """
    if not bundle:
        return (fallback or "").strip()

    if len(bundle) == 1:
        only = bundle[0]
        # The purpose is the reasoning's own prose and is written as a full
        # sentence as often as as a phrase, so grafting it into "Per …:"
        # produced "Per necessario per creare l'evento: data e ora del rogito?".
        # It has a place of its own — `why_needed` — and this is not it.
        return f"{_label(only)}?"

    labels = _list_phrase([_label(v).lower() for v in bundle])
    step = (step_title or "").strip().rstrip(".")
    if step:
        return f"Per {step[0].lower()}{step[1:]} mi servono: {labels}."
    return f"Mi servono ancora: {labels}."


def compose_why(bundle: Sequence[Variable], *, step_title: str = "") -> str:
    """
    A reason, only when the request earns one.

    An obvious question explained is noise. A long or personal one that is not
    explained reads as data collection, so those get one sentence — the
    reasoning's own purpose when it gave one, and nothing invented when it
    did not.
    """
    if len(bundle) < EXPLAIN_FROM and not any(v.sensitivity != "normal" for v in bundle):
        return ""
    purposes = [v.purpose.strip() for v in bundle if v.purpose.strip()]
    if purposes:
        return purposes[0][:400]
    if step_title:
        return f"Servono per {step_title.rstrip('.').lower()}."[:400]
    return ""


def build_ask(
    blocking: Sequence[Variable],
    *,
    step_title: str = "",
    milestone_ref: Optional[str] = None,
    fallback_question: str = "",
    asked_refs: Optional[Sequence[str]] = None,
) -> NextStep:
    """The one question this cycle is allowed to ask, or nothing to ask."""
    bundle = select_bundle(blocking)
    if not bundle and not fallback_question.strip():
        return NextStep(kind="proceed", title=step_title, milestone_ref=milestone_ref)

    # The system decides *what* may be asked; the model usually writes better
    # Italian than any template. Its words stand when guidance did not change
    # the set — nothing already known, nothing dropped — and when they are
    # actually usable: a sentence that hands the choice of step back to the
    # person, or that arrives in English, is not, however well it reads.
    model_words = fallback_question.strip()
    unchanged = (
        bool(model_words)
        and asked_refs is not None
        and {v.ref for v in bundle} == {str(r) for r in asked_refs}
    )
    usable = bool(model_words) and not is_meta_choice(model_words) and not looks_english(model_words)
    question = (
        model_words
        if (unchanged and usable)
        else compose_question(
            bundle,
            step_title=step_title,
            fallback=model_words if usable else "",
        )
    )

    return NextStep(
        kind="ask",
        title=step_title,
        milestone_ref=milestone_ref,
        question=question,
        why_needed=compose_why(bundle, step_title=step_title),
        requested=list(bundle),
    )


def unresolved_after(bundle: Sequence[Variable], answered_refs: Sequence[str]) -> List[Variable]:
    """
    What a partial answer left behind.

    Someone asked for four things and giving two has answered the question they
    were asked. Asking for all four again is the failure §52 exists to prevent;
    only what is still missing may be asked a second time.
    """
    answered = {str(r).strip() for r in answered_refs if str(r).strip()}
    return [v for v in bundle if v.ref not in answered and v.blocks]
