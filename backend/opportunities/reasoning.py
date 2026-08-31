"""
Whether anything here is worth saying, and what.

    PROACTIVITY IS AN AI JUDGMENT, NOT A RULE TRIGGER.
    SILENCE IS A VALID DECISION.

The code hands over facts and asks a question it cannot answer: given this
life, right now, is there something worth this person's attention? An event
tomorrow is not an answer. A deadline is not an answer. Being at home is not an
answer. Whether any of them adds up to something depends on the person, on
what they already know, on what it would cost them to miss it — and none of
that is expressible as a threshold.

Two failure modes are guarded against in the prompt rather than in code,
because they are failures of judgement and code cannot see them. The first is
manufacturing: a system rewarded for finding things will find things, so the
instructions say plainly that silence is the expected outcome and costs
nothing. The second is inventing: a deadline that does not exist is worse than
no opportunity at all, so every claim has to point at a fact that was actually
supplied.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from research.reasoning import _ask_model

logger = logging.getLogger(__name__)

_DISCIPLINE = (
    "You decide whether to interrupt someone about their own life.\n\n"
    "Nobody is paying you to find something to say. Most of the time there is "
    "nothing worth raising, and saying so is the correct, expected answer — "
    "not a failure, not an empty result, not something to avoid. A system that "
    "speaks whenever it can becomes something people stop reading.\n\n"
    "You are shown facts. Facts are not conclusions:\n"
    "- an event tomorrow is not an opportunity;\n"
    "- a deadline is not an opportunity;\n"
    "- being somewhere is not an opportunity, and where somebody is means "
    "nothing on its own;\n"
    "- an unmade decision is not an opportunity — people are allowed to leave "
    "things open;\n"
    "- a comparison with no choice made is not an opportunity.\n\n"
    "You may only state things the facts support. Never invent a deadline, an "
    "obligation, an appointment, a cost, a risk or an intention. If the "
    "decisive fact is missing, say what is missing: ask for it, or say it must "
    "be looked up. An invented deadline is worse than saying nothing at all.\n\n"
    "You have no commercial interest of any kind. There are no partners, no "
    "sponsors, no products to prefer. The only question is whether this is "
    "useful to this person."
)


async def scan(
    snapshot: Dict[str, Any],
    *,
    already_raised: List[Dict[str, Any]],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Look at a life and decide whether anything deserves attention.

    Returns None when the model could not be reached — which is not silence
    and must never be recorded as one. Returns a payload with an empty list
    when the model looked and found nothing, which is the ordinary outcome.
    """
    instruction = (
        "Read the facts below and decide whether anything is worth bringing to "
        "this person's attention now or soon.\n\n"
        "Ask yourself, for each thing you are tempted to raise:\n"
        "- what concretely would they do with this?\n"
        "- what happens if nobody says anything — is it recoverable?\n"
        "- do they almost certainly know already?\n"
        "- is it specific enough to act on, or just true?\n"
        "- does it compete with something more important they are already "
        "dealing with?\n"
        "- is the decisive fact actually here, or am I assuming it?\n\n"
        "If you cannot answer the first two, it is not an opportunity.\n\n"
        "Silence and uncertainty are not the same thing. When something "
        "with a real consequence is close and the facts do not tell you "
        "whether it is already handled, saying nothing is the wrong "
        "answer: raise it, mark `requires_clarification` true and give "
        "the one question that would settle it. Say plainly what you do "
        "not know. Never assume it has been neglected, and never write "
        "an assumption as though it were a fact.\n\n"
        "When something IS worth raising, give it an `identity_key`: a short, "
        "stable, lowercase slug for the CONCERN, not for today's wording of "
        "it. The same worry noticed again next week must produce the same key, "
        "so that it updates rather than arriving twice. Base it on what the "
        "concern is about, never on today's date or phrasing.\n\n"
        "When you say how far away something is, use the `in_days` the "
        "facts give you and no other count. It was worked out from the "
        "real dates; a number you arrive at yourself is the one part of "
        "the sentence a person checks against their own calendar.\n\n"
        "Cite the facts you used by their `ref`, exactly as given. A claim "
        "with no ref behind it will be dropped.\n\n"
        "Return JSON:\n"
        '{"opportunities": [], "reason_for_silence": "one short sentence"} '
        "when there is nothing — and expect this to be the usual answer.\n\n"
        "Otherwise:\n"
        '{"opportunities": [{"identity_key": "...", "what": "one sentence a '
        'person would recognise", "why_it_matters": "the concrete '
        'consequence", "why_now": "why this moment and not later", '
        '"relevance": "low|medium|high", "urgency": "none|soon|urgent", '
        '"time_sensitivity": "stable|changing|perishable", "confidence": '
        '"weak|reasonable|strong", "evidence_refs": ["..."], '
        '"requires_clarification": false, "clarifying_question": "", '
        '"needs_research": false, "research_question": "", "valid_until": '
        'null}]}\n\n'
        "Write `what`, `why_it_matters` and `why_now` in the person's "
        "language. No implementation words, no ids, no jargon."
    )

    payload = {
        "language": language,
        "life_right_now": snapshot,
        "already_raised_before": already_raised,
        "note": (
            "already_raised_before is what you have said before, including "
            "things this person dismissed. Do not raise a dismissed concern "
            "again unless something material has changed, and say what "
            "changed if you do."
        ),
    }

    data = await _ask_model(_DISCIPLINE + "\n\n" + instruction, _dump(payload))
    if not isinstance(data, dict):
        return None
    return data


async def review(
    opportunity: Dict[str, Any],
    *,
    snapshot: Dict[str, Any],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Is this still true, and does it still matter?

    An opportunity is a claim about a moment, and moments pass. The document
    was found, the event was cancelled, the decision was made, the date went
    by. The model reads the same life again and says what became of it.
    """
    instruction = (
        "You raised this before. Look at the facts as they are now and decide "
        "what became of it.\n\n"
        "- `resolve` — the concern is dealt with: the thing was done, found, "
        "decided or arranged.\n"
        "- `expire` — the moment passed and it no longer applies.\n"
        "- `update` — still worth raising, but what you would say has changed. "
        "Give the new wording and judgement.\n"
        "- `keep` — nothing has changed; leave it exactly as it is.\n"
        "- `suppress` — it should not be raised again at all.\n\n"
        "Prefer `resolve` and `expire` over keeping something alive out of "
        "caution. An opportunity that lingers after its reason has gone is "
        "clutter, and clutter is what makes people stop reading.\n\n"
        "Return JSON: {\"outcome\": \"keep|update|resolve|expire|suppress\", "
        "\"rationale\": \"one short sentence\", \"updated\": {\"what\": "
        "\"...\", \"why_it_matters\": \"...\", \"why_now\": \"...\", "
        "\"relevance\": \"...\", \"urgency\": \"...\"}} — `updated` only when "
        "the outcome is `update`."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump(
            {
                "language": language,
                "what_you_raised": opportunity,
                "life_right_now": snapshot,
            }
        ),
    )
    if not isinstance(data, dict):
        return None
    outcome = str(data.get("outcome") or "").strip()
    if outcome not in {"keep", "update", "resolve", "expire", "suppress"}:
        return None
    return data


def _dump(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)[:9000]


async def decide_surfacing(
    candidates: List[Dict[str, Any]],
    *,
    context: Dict[str, Any],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Which of these, if any, belong in front of somebody right now.

        SURFACE != NOTIFY.
        OPPORTUNITY ACTIVE != CARD ALWAYS VISIBLE.

    A second judgement, deliberately not folded into the first. Whether
    something is true and whether this is the moment to say it are
    different questions with different answers, and a system that answers
    only the first ends up showing everything it believes — which is how a
    quiet product becomes a feed.

    Nothing here is graded. The model is not told that `high` shows and
    `medium` hides, because that would be the rule this whole design exists
    to avoid: a `high` concern somebody refused twice last week is worse to
    show than a `medium` one they have never seen.
    """
    instruction = (
        "Decide which of these, if any, should be visible on this "
        "person's home right now. Showing nothing is a normal outcome.\n\n"
        "For each one:\n"
        "- `surface` — worth a quiet line on their home now.\n"
        "- `hold` — still true, but not now: they are in the middle of "
        "something else, they have just seen it, or the moment is "
        "wrong.\n"
        "- `retire` — it should stop occupying space, whatever its "
        "status.\n\n"
        "Weigh what they are doing, what they have already been shown and "
        "how often, what they refused before, and whether this would read "
        "as noise arriving next to everything else on that screen. "
        "Something shown several times and never acted on is not more "
        "deserving for having been ignored — it is less.\n\n"
        "Space is scarce and quiet is the default: prefer holding to "
        "showing when it is close. Two things competing usually means one "
        "of them waits.\n\n"
        "Return JSON: {\"decisions\": [{\"id\": \"...\", "
        "\"decision\": \"surface|hold|retire\", "
        "\"rationale\": \"one short sentence\"}]} — every id "
        "you were given, exactly once."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump(
            {
                "language": language,
                "candidates": candidates,
                "what_is_going_on": context,
            }
        ),
    )
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("decisions"), list):
        return None
    return data


async def decide_revisit(
    opportunity: Dict[str, Any],
    *,
    context: Dict[str, Any],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    "Più tardi" — but how much later?

    Six hours was the wrong answer to a question code should not have been
    answering. Somebody saying "not now" about an appointment tomorrow
    morning means this evening; about a dentist they have been putting off
    for six months it means next week, and about something waiting on a
    fact that has not arrived yet it means when that fact arrives. Same
    word, three different amounts of time, and the difference is entirely
    in what the thing is — which is a judgement.

    This decides when it becomes eligible to be considered again. Nothing
    is scheduled and nobody is told anything at that hour: it is the
    earliest moment the surfacing decision may look at it, and that
    decision is still free to hold it again.
    """
    instruction = (
        "Somebody has just said «più tardi» about this. They did not "
        "refuse it and they have not dealt with it — they do not want it "
        "on their screen right now.\n\n"
        "Say when it would make sense to consider showing it again. Think "
        "about what it is waiting on: a moment that is approaching, a fact "
        "that has not arrived, a deadline, or nothing in particular. "
        "Something with a fixed moment coming should come back in time to "
        "be useful and not a minute earlier; something with no clock on it "
        "at all can wait days.\n\n"
        "Do not bring it back so soon that saying «più tardi» achieved "
        "nothing, and not so late that it returns after it stopped "
        "mattering.\n\n"
        "You are choosing when it may be RECONSIDERED, not when to tell "
        "them anything. Nobody will be interrupted at that hour. The same "
        "judgement that decided to show it will decide again, and may well "
        "hold it a second time.\n\n"
        "Return JSON: {\"revisit_in_hours\": 12, "
        "\"rationale\": \"one short sentence\", "
        "\"confidence\": \"weak|reasonable|strong\"} — "
        "`revisit_in_hours` a whole number of hours from now."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump(
            {
                "language": language,
                "what_they_deferred": opportunity,
                "what_is_going_on": context,
            }
        ),
    )
    if not isinstance(data, dict):
        return None
    try:
        hours = int(float(data.get("revisit_in_hours")))
    except (TypeError, ValueError):
        return None
    if hours <= 0:
        return None
    data["revisit_in_hours"] = hours
    return data
