"""
Whether an observation means anything.

    CONNECTED DOES NOT MEAN INTERRUPTING.
    MOST OF WHAT MOVES IN A LIFE DOES NOT NEED ANYBODY.

One judgement, and the shape of the prompt is the whole safeguard. A model
handed a stream of changes and asked "what should we do about this?" will
find something to do about all of it — that is what a helpful model is for —
and the result is a system that turns a synced calendar into a source of
errands.

So the question is inverted. It is asked whether this is worth anybody's
attention, `noise` is named first and described as the ordinary answer, and
the examples of noise are deliberately the ones a system is most tempted by:
the appointment ORA itself just made, the document that arrived, the meeting
that moved by five minutes.

What comes back is meaning, never action. Nothing in the returned shape can
create a goal, schedule anything or say a word to anybody: those decisions
have owners already, and this layer exists to feed them, not to become them.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from research.reasoning import _ask_model

logger = logging.getLogger("ora.connected.reasoning")

_DISCIPLINE = (
    "You are reading changes in somebody's connected life — their calendar, "
    "their documents, the messages they receive — and deciding what, if "
    "anything, each one means.\n\n"
    "A message is a change like any other, and the same rule holds: most "
    "of them mean nothing that needs anybody. But a message from a "
    "practice, an office or a service saying something they arranged has "
    "moved, been confirmed or been cancelled is about an appointment in "
    "their life, and a subject line alone rarely settles which.\n\n"
    "Most changes mean nothing that needs anybody. A meeting moved by ten "
    "minutes, a recurring stand-up, a file somebody uploaded to have it "
    "somewhere: these are a life happening, not a life needing help. Saying "
    "so is the correct answer and the common one.\n\n"
    "You are not summarising and you are not narrating. Nobody wants to be "
    "told what their own calendar says.\n\n"
    "Write about the person's life, never about data, providers, syncs or "
    "records. Never mention that something was 'detected'.\n\n"
    "Answer with JSON only. No markdown fences."
)

# What the judgement may conclude. Deliberately four words, and the first is
# the ordinary one.
OUTCOMES = ("noise", "worth_knowing", "changes_something_known", "may_need_action")


async def interpret_signal(
    signal: Dict[str, Any],
    *,
    life: Dict[str, Any],
    source: Dict[str, Any],
    recent: List[Dict[str, Any]],
    language: str = "it",
    content: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    What this change means in this life, or that it means nothing.

    `who_caused_it` reaching the model matters more than it looks. A change
    ORA made itself is not news about the world — it is ORA's own work coming
    back round, and the only useful thing to conclude about it is that the
    work landed. The instruction says so plainly, and code refuses to act on
    it either way.
    """
    instruction = (
        "Something in this person's connected life has changed. Decide what "
        "it means to them.\n\n"
        "You are shown every difference that was observed, not a "
        "selection. Nothing was ranked, filtered or dropped before it "
        "reached you: if an appointment moved and changed room and "
        "gained somebody, all three are listed, in no particular order. "
        "Which of them matters, if any, is exactly the judgement you "
        "are here for.\n\n"
        "Some fields say only that they changed, with no content. That "
        "is deliberate: a private note and other people's addresses are "
        "not carried. That a field changed is still a fact you may "
        "weigh.\n\n"
        "If one of those genuinely decides the answer — a note that "
        "might say what to bring, or might say nothing that matters — "
        "say so with needs_content, and you will be asked again with "
        "it. Ask only when you cannot decide without it: it is read "
        "from their private record, once, and the reading is written "
        "down.\n\n"
        "Your choices:\n"
        "- `noise` — nothing here needs anybody. The ordinary answer.\n"
        "- `worth_knowing` — a person would want to know, and nothing is "
        "being asked of them.\n"
        "- `changes_something_known` — this makes something ORA already "
        "believes about their life out of date.\n"
        "- `may_need_action` — left alone, this would cost them something.\n\n"
        "If ORA itself caused this change, it is not news: at most it "
        "confirms that something ORA already did actually landed. Never "
        "treat it as a reason to do the thing again.\n\n"
        "Judge it against the life you are shown, not in the abstract. The "
        "same appointment moving is nothing to one person and a problem for "
        "another, and the difference is in what else is true about them.\n\n"
        "One more thing to say about it, separately from what it means: "
        "whether it tells you something about this person's money — a "
        "cost they have or will have, money coming to them, something "
        "they paid. It is a different question from whether it matters, "
        "and the answer is often no even when the message mentions a "
        "price: an advertisement for loans names sums and says nothing "
        "about theirs.\n\n"
        "Return JSON: {\"outcome\": \"noise|worth_knowing|"
        "changes_something_known|may_need_action\", "
        "\"what_it_means\": \"one sentence about their life, empty when "
        "noise\", "
        "\"relates_to\": \"a few words naming what in their life this is "
        "about, or empty\", "
        "\"reasoning\": \"one short sentence, never shown to them\", "
        "\"needs_content\": false, "
        "\"why_content\": \"what you would decide with it, when asking\", "
        "\"touches_money\": false}\n\n"
        "Write anything a person reads in their language."
    )

    payload: Dict[str, Any] = {
        "what_changed": signal,
        "what_we_know_about_them": life,
        "where_it_came_from": source,
        "other_things_that_moved_recently": recent,
    }
    if content:
        # Present for this one call and kept nowhere. Marked so the model
        # knows it is looking at something private that was fetched because
        # it asked, and so that a reader of this function can see there is
        # exactly one place content enters.
        payload["what_you_asked_to_see"] = content

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump(payload),
    )
    if not isinstance(data, dict):
        return None
    outcome = str(data.get("outcome") or "").strip()
    if outcome not in OUTCOMES:
        return None
    data["outcome"] = outcome
    data["needs_content"] = bool(data.get("needs_content")) and content is None
    # Se questa cosa parla dei soldi di questa persona. E' una domanda a parte
    # da «conta qualcosa», e la risposta e' spesso no anche quando il
    # messaggio nomina delle cifre.
    #
    # Sta qui, dentro il giudizio che gia' si fa, e non in un secondo
    # passaggio: un instradamento a parole chiave — «fattura» quindi soldi —
    # manderebbe al ragionamento finanziario ogni newsletter che nomina un
    # prezzo, e lascerebbe fuori «da settembre pago sessanta euro in piu'».
    data["touches_money"] = bool(data.get("touches_money"))
    return data


# What a link judgement may conclude. `uncertain` is not a failure mode: it
# is the correct answer whenever the evidence does not settle it, and a
# vocabulary without it would force a guess that everything downstream would
# then treat as knowledge.
# What a link judgement may conclude. `uncertain` is not a failure mode: it
# is the correct answer whenever the evidence does not settle it, and a
# vocabulary without it would force a guess that everything downstream would
# then treat as knowledge.
LINK_OUTCOMES = (
    "same_situation", "related", "new_situation", "irrelevant", "uncertain",
)


async def decide_link(
    signal: Dict[str, Any],
    *,
    candidates: List[Dict[str, Any]],
    life: Dict[str, Any],
    meaning: Dict[str, Any],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Whether this reading and something already known are the same thing.

        MULTIPLE SOURCES CAN REFER TO THE SAME THING IN A PERSON'S LIFE.

    The candidates are handed over as facts with no scores attached and in no
    meaningful order, and the model is told plainly that resemblance is not
    identity: an email mentioning a dentist and an appointment with a dentist
    may be one afternoon or two unrelated things, and the difference is a
    judgement about a life rather than about two strings.

    What comes back can be `uncertain`, and code does nothing with that
    beyond recording it. There is deliberately no fallback that picks the
    closest candidate — a link nobody was sure of is worse than none, because
    everything downstream then reasons about a situation that does not exist.
    """
    if not candidates:
        return None

    instruction = (
        "Here is something that just happened in this person's life, and "
        "some things ORA already knows about. Decide whether the new thing "
        "is about one of them.\n\n"
        "Sources describe the same life from different angles. An "
        "appointment in a calendar, a message about it, and the document it "
        "asks them to bring are three readings of one afternoon — and "
        "treating them as three separate arrivals is how a system ends up "
        "telling somebody three things instead of one true one.\n\n"
        "But resemblance is not identity. Two appointments with the same "
        "doctor are not one appointment, and a message that happens to share "
        "a word with a title proves nothing. Say `same_situation` when the "
        "evidence actually supports it and `uncertain` whenever it does "
        "not — `uncertain` is a real answer and costs nothing.\n\n"
        "Your choices:\n"
        "- `same_situation` — this is about a thing already listed. Name it "
        "in target_ref.\n"
        "- `related` — connected to one of them, but not the same thing.\n"
        "- `new_situation` — something in their life that is not here yet.\n"
        "- `irrelevant` — nothing in this life turns on it.\n"
        "- `uncertain` — the evidence does not settle it.\n\n"
        "Where two readings say different things about the same situation "
        "you are shown both, with when each was observed and how directly "
        "each knows. Nothing has decided which is right, and you do not have "
        "to either: that they disagree is often the true and useful "
        "answer.\n\n"
        "Return JSON: {\"relationship\": \"same_situation|related|"
        "new_situation|irrelevant|uncertain\", "
        "\"target_ref\": \"the ref of the thing it is about, or empty\", "
        "\"confidence\": 0.0, "
        "\"why\": \"one sentence a person could be shown, in their "
        "language\", "
        "\"relied_on\": [\"the refs whose facts you actually used\"]}"
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump({
            "what_just_happened": signal,
            "what_it_seems_to_mean": meaning,
            "things_already_known": candidates,
            "what_we_know_about_them": life,
        }),
    )
    if not isinstance(data, dict):
        return None
    relationship = str(data.get("relationship") or "").strip()
    if relationship not in LINK_OUTCOMES:
        return None

    # A target only counts when it names one of the candidates offered. A
    # model inventing a ref would otherwise produce a link to nothing, and a
    # link to nothing reads downstream exactly like a link to something.
    offered = {str(c.get("ref") or "") for c in candidates}
    target = str(data.get("target_ref") or "").strip()
    if target not in offered:
        target = ""
    if relationship in ("same_situation", "related") and not target:
        relationship = "uncertain"

    return {
        "relationship": relationship,
        "target_ref": target,
        "confidence": _bounded(data.get("confidence")),
        "why": str(data.get("why") or "")[:300],
        "relied_on": [
            str(r)[:120] for r in (data.get("relied_on") or []) if str(r) in offered
        ][:8],
    }


def _bounded(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _dump(payload: Dict[str, Any]) -> str:
    """
    What the model is shown, bounded.

    Truncation is a privacy boundary as much as a cost one, and it matters
    more here than anywhere: this is the layer where somebody's real calendar
    meets a prompt, and a payload that can grow without limit is one that
    eventually carries a fortnight of their appointments into a log.
    """
    return json.dumps(payload, ensure_ascii=False, default=str)[:6000]
