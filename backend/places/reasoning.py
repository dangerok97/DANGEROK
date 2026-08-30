"""
Whether a repeated spot is worth a question, and what to ask.

The counter can tell you somebody was in the same place eleven times. It
cannot tell you whether that is worth interrupting them about — eleven visits
to a supermarket and eleven visits to a hospital are the same number and very
different questions — and it certainly cannot tell you what the place is.

So the measurements go to the model, and what comes back is a decision about
asking, phrased as a question a person could answer. What the place *is* comes
from the person. Nothing in this file, and nothing downstream of it, is allowed
to name a place on somebody's behalf.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from research.reasoning import _ask_model

logger = logging.getLogger(__name__)

_DISCIPLINE = (
    "You are deciding whether to interrupt someone. Nobody is paying you to "
    "find something to say. Silence is a valid answer and usually the right "
    "one.\n"
    "You are shown places a device kept returning to. You are NOT shown what "
    "they are, because nobody knows yet, and you must not decide. A count is "
    "not a meaning: the same eleven visits could be a gym, a hospital, a "
    "parent's flat or a road you park on. Never name a place. Never guess a "
    "category. Ask, or stay quiet."
)


async def should_ask_about(
    candidates: List[Dict[str, Any]],
    *,
    known_places: List[Dict[str, Any]],
    language: str = "it",
) -> List[Dict[str, Any]]:
    """
    Decide which repeated spots deserve a question, and how to word it.

    Returns one entry per candidate worth asking about: its id, the question
    in the person's language, and why it seemed worth raising. Everything not
    returned is left alone — which is the common case and needs no explanation.
    """
    if not candidates:
        return []

    payload = {
        "language": language,
        "repeated_locations": candidates,
        "places_they_already_named": known_places,
    }
    instruction = (
        "For each repeated location, decide whether it is worth asking the "
        "person about it at all.\n\n"
        "Reasons to stay quiet: too few sightings to mean anything; it looks "
        "like somewhere they already named; it was seen once and never again; "
        "the pattern is too thin to be worth an interruption. Staying quiet is "
        "not a failure and costs nothing — the location will still be there "
        "next week.\n\n"
        "If it is worth asking, write the question the way a person would ask "
        "it: short, in their language, admitting you do not know. "
        "\"Che posto è?\" is a question. \"È la tua palestra?\" is a guess "
        "wearing a question mark, and if you are wrong the person has to "
        "correct a claim instead of answering.\n\n"
        "Return JSON: {\"ask_about\": [{\"candidate_id\": \"...\", "
        "\"question\": \"...\", \"why\": \"what about the pattern made this "
        "worth raising, in one short sentence\"}]}. "
        "Return an empty list if none of them are worth it."
    )

    data = await _ask_model(_DISCIPLINE + "\n\n" + instruction, _dump(payload))
    if not isinstance(data, dict):
        return []

    known_ids = {c.get("candidate_id") for c in candidates}
    out: List[Dict[str, Any]] = []
    for raw in (data.get("ask_about") or [])[:5]:
        if not isinstance(raw, dict):
            continue
        cid = raw.get("candidate_id")
        question = str(raw.get("question") or "").strip()
        # Fail closed on identity, exactly as everywhere else: a question about
        # a location we cannot resolve is a question about nothing.
        if cid not in known_ids or not question:
            continue
        out.append(
            {
                "candidate_id": cid,
                "question": question[:600],
                "why": str(raw.get("why") or "").strip()[:400],
            }
        )
    return out


async def interpret_answer(
    answer: str, *, question: str, language: str = "it"
) -> Optional[Dict[str, Any]]:
    """
    Turn what the person said into a place, or into a refusal.

    The person answers in their own words — "è la palestra", "casa di mia
    madre", "lascia stare" — and this reads the intent behind it. The label is
    kept as they said it; only the structural role is normalised, and only to
    home, work or neither.
    """
    instruction = (
        "Someone was asked about a place they visit often. Read their answer.\n\n"
        "Decide what they meant:\n"
        "- they named the place → keep their words as the name, exactly as they "
        "wrote them. Do not tidy, translate or expand them.\n"
        "- the name they gave means it is where they live → role \"home\".\n"
        "- it means where they work or study for a living → role \"work\".\n"
        "- anything else → role \"other\". Most places are other, and that is "
        "not a lesser answer.\n"
        "- they declined → decision \"skip\".\n"
        "- they do not want to be asked about this place again → \"mute\".\n\n"
        "Do not invent a name they did not give. If they said something you "
        "cannot read as either a name or a refusal, return \"unclear\".\n\n"
        "Return JSON: {\"decision\": \"name\"|\"skip\"|\"mute\"|\"unclear\", "
        "\"label\": \"their words, when they gave a name\", "
        "\"role\": \"home\"|\"work\"|\"other\"}."
    )
    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump({"language": language, "question": question, "answer": answer}),
    )
    if not isinstance(data, dict):
        return None

    decision = str(data.get("decision") or "").strip()
    if decision not in {"name", "skip", "mute", "unclear"}:
        return None
    role = str(data.get("role") or "other").strip()
    if role not in {"home", "work", "other"}:
        role = "other"
    label = str(data.get("label") or "").strip()[:120]
    if decision == "name" and not label:
        return None
    return {"decision": decision, "label": label, "role": role}


def _dump(payload: Dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)[:6000]


async def read_the_shape_of_the_days(
    days: List[Dict[str, Any]],
    *,
    place_names: Dict[str, str],
    journeys: List[Dict[str, Any]],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Look at a stretch of days and say whether there is a pattern worth naming.

    The code has already counted everything countable: which places, in which
    order, on which days, at what times, for how long. What it cannot do is
    decide that eleven similar mornings amount to a routine — two consecutive
    Mondays are a coincidence, and the line between coincidence and habit is a
    judgement about a life, not a threshold.

    Returning nothing is the normal outcome and costs nothing.
    """
    if not days:
        return None

    instruction = (
        "You are shown somebody's days: which of their own places they were "
        "in, in what order, when, and for how long. The names are theirs.\n\n"
        "Decide whether a repeated shape is worth naming. Reasons not to: too "
        "few days to tell; the days differ more than they agree; it is the "
        "obvious fact that people sleep at home, which tells nobody anything. "
        "Two similar days are a coincidence.\n\n"
        "If there is one, describe it the way the person would recognise it: "
        "one sentence, their language, concrete about when. Do not predict, do "
        "not advise, do not congratulate. You are noticing, not coaching.\n\n"
        "Then say separately whether it is worth interrupting them to ask "
        "about it. Usually it is not: noticing something is not a reason to "
        "speak.\n\n"
        "Return JSON: {\"routine\": null} when there is nothing, or "
        "{\"routine\": {\"place_ids\": [in order], \"weekdays\": [], "
        "\"typical_start\": \"HH:MM\", \"typical_end\": \"HH:MM\", "
        "\"occurrences\": 0, \"interpretation\": \"one sentence\"}, "
        "\"worth_asking\": true, \"question\": \"...\"}."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump(
            {
                "language": language,
                "days": days,
                "place_names": place_names,
                "journeys_between_places": journeys,
            }
        ),
    )
    if not isinstance(data, dict):
        return None
    routine = data.get("routine")
    if not isinstance(routine, dict):
        return None

    # Fail closed on identity, as everywhere else: a routine through a place
    # that does not exist is a routine through nothing.
    ids = [p for p in (routine.get("place_ids") or []) if p in place_names]
    if len(ids) < 2:
        return None
    return {
        "place_ids": ids[:8],
        "weekdays": [str(w)[:12] for w in (routine.get("weekdays") or [])][:7],
        "typical_start": str(routine.get("typical_start") or "")[:20],
        "typical_end": str(routine.get("typical_end") or "")[:20],
        "occurrences": int(routine.get("occurrences") or 0),
        "interpretation": str(routine.get("interpretation") or "").strip()[:400],
        "worth_asking": bool(data.get("worth_asking")),
        "question": str(data.get("question") or "").strip()[:600],
    }
