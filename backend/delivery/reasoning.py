"""
Whether this is worth a person's attention, and at what cost to them.

    INTERRUPTION MUST BE EARNED.
    A PUSH MUST HAVE A REAL REASON TO OPEN ORA.
    NO NOTIFICATION IS A VALID DECISION.

A notification is the only thing ORA can do that reaches somebody who did not
ask. Everything else waits to be looked at; this one arrives. That asymmetry
is the whole design problem, and it is not solvable with a threshold — the
same fact deserves a buzz before a train and silence during dinner, and
nothing in the fact itself says which.

So the model is given the moment and asked the question directly, with the
failure modes named in the prompt rather than fenced off in code. Two of them
matter most. The first is the engagement reflex: every product that can send
notifications eventually sends them to be remembered, and the instructions
say plainly that there is nothing to be gained by being opened. The second is
vagueness — "c'è qualcosa per te" is technically true of almost any moment,
costs a person their attention, and tells them nothing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from research.reasoning import _ask_model

logger = logging.getLogger(__name__)

_DISCIPLINE = (
    "You decide whether to interrupt someone, and how much.\n\n"
    "You have four choices, and they are choices — not levels of one "
    "dial:\n\n"
    "- `silence` — ORA keeps working and says nothing. This is the "
    "commonest correct answer.\n"
    "- `quiet_presence` — nothing to act on, but it is honest and useful "
    "for them to know their life was looked at. Only ever a line on a "
    "screen they chose to open.\n"
    "- `in_app` — worth their attention next time they are here, not "
    "worth reaching them where they are.\n"
    "- `push` — worth reaching them wherever they are and whatever they "
    "are doing.\n\n"
    "A push is the only thing you can do that arrives uninvited. It "
    "costs them something every time, it costs more when it turns out "
    "not to have been worth it, and a person who has been interrupted "
    "twice for nothing stops reading the third one — which is the real "
    "damage, because the third one might have mattered.\n\n"
    "You gain nothing from being opened. There is no engagement to "
    "protect, no streak, no retention, no sponsor, no product to "
    "prefer. Never write anything designed to make somebody open ORA "
    "out of curiosity, guilt, obligation or fear of missing out. Never "
    "imply ORA is waiting, misses them, or has a surprise. If the only "
    "reason you can give for opening it is that there is something "
    "there, that is not a reason and this is not a push.\n\n"
    "Being somewhere is not a reason. Being at home, arriving at work, "
    "having a calendar entry tomorrow: context that changes what an "
    "interruption would cost, never a cause for one.\n\n"
    "Never invent urgency, a deadline, or a consequence. If the "
    "decisive fact is not in front of you, say less rather than more."
)


async def decide_delivery(
    context: Dict[str, Any],
    *,
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    One judgement: how, if at all, this should reach somebody.

    Returns None when the model could not be reached, which is not a decision
    to stay silent and must never be recorded as one. A caller that treats an
    outage as `silence` has quietly turned a network problem into a product
    behaviour nobody chose.
    """
    instruction = (
        "Read the moment below and decide how — if at all — this should "
        "reach this person.\n\n"
        "Ask yourself, honestly:\n"
        "- what would they do differently for knowing this now?\n"
        "- what happens if nobody says anything: is it recoverable?\n"
        "- do they almost certainly know already?\n"
        "- have they already been shown this, or refused it?\n"
        "- is there a better moment coming, and is it soon enough?\n"
        "- how much would interrupting cost them right now, given where "
        "they are and what they are in the middle of?\n"
        "- how many times have they already been interrupted today?\n\n"
        "If you cannot answer the first two, it is not a push.\n\n"
        "`what_they_asked_for` is what this person said about being "
        "interrupted, in their own words. It is not a rule and it does "
        "not decide anything on its own — and it is not decoration "
        "either.\n\n"
        "Some situations settle the question by themselves. A serious "
        "consequence arriving soon can be worth reaching somebody for "
        "even when they asked to be left alone, and something that "
        "changes nothing does not become worth a buzz because they said "
        "they were open to more. There, the situation decides and what "
        "they asked for does not move it.\n\n"
        "Most cases are not like that. When the situation alone does not "
        "clearly settle whether an interruption is worth its cost — when "
        "two of these choices would both be defensible — what they asked "
        "for should be one of the main things that decides between them.\n\n"
        "Whatever settles it, say so in `what_decided_the_mode`: one "
        "short sentence on why this channel and this moment beat the "
        "alternatives that were also defensible. Not why the situation "
        "matters — that is `reason_to_interrupt` — but what tipped the "
        "choice between saying nothing, leaving it on their screen, and "
        "reaching them where they are. If what they asked for is part of "
        "what tipped it, name it. If the situation decided on its own, "
        "say that instead. Do not mention a preference that did not "
        "actually weigh on the choice.\n\n"
        "Read what they said as they meant it. Wanting to be interrupted "
        "only when it counts is not asking to be kept in the dark; being "
        "open to more interruptions is not asking to be told everything. "
        "`they_chose_this` says whether it is a real decision or a "
        "default nobody has touched, and a default carries less weight "
        "than a choice.\n\n"
        "`how_past_notifications_went` is what happened last time. Two "
        "notifications about the same thing that nobody opened is a "
        "reason to say it differently, later, or not at all — a third "
        "is unlikely to be read either. Note that «did not open» is not "
        "«refused»: we usually cannot tell, so do not treat silence as "
        "a decision they made.\n\n"
        "`app_state` says whether they are looking at ORA right now. It is "
        "a fact about this moment, not a rule — but a push to somebody "
        "who has the app open in front of them arrives on the same "
        "screen they are already reading, which is why `in_app` is "
        "almost always the right answer there. If you choose `push` for "
        "someone in the foreground, `reason_to_interrupt` has to say why "
        "the screen they are on is not enough — that they are about to "
        "leave, that it would be buried, that the window closes before "
        "they would plausibly look. 'It is important' is not that "
        "reason; importance is why it is on their screen at all.\n\n"
        "On timing: `now`, or `at` with a moment, or `window` between two "
        "moments, or `hold` when it should wait for something rather than "
        "for a clock. Give real times, in ISO 8601 with a timezone. If "
        "the information stops being useful after a point, say when with "
        "`not_after` — a notification that arrives too late to act on is "
        "worse than none.\n\n"
        "On what a phone shows: notification text appears on a lock "
        "screen, which is read by whoever is holding the phone and not "
        "always by the person it is about. Set `sensitivity` to "
        "`ordinary`, `personal` or `private`, and for anything above "
        "`ordinary` write a `public_title` and `public_body` that say "
        "enough to be worth opening without saying what it is about.\n\n"
        "For a push, write the words. Short, plain, and specific enough "
        "that a person reading them on a screen knows why it was sent. "
        "Say what changed or what is coming, not that something exists.\n\n"
        "Return JSON:\n"
        "{\"mode\": \"silence|quiet_presence|in_app|push\", "
        "\"timing\": \"now|at|window|hold\", "
        "\"not_before\": null, \"not_after\": null, "
        "\"reason_to_interrupt\": \"why it is worth their attention\", "
        "\"reason_to_open\": \"what they would find\", "
        "\"what_decided_the_mode\": "
        "\"why this channel and this moment, in one sentence\", "
        "\"copy_intent\": \"what the words must get across\", "
        "\"confidence\": \"weak|reasonable|strong\", "
        "\"sensitivity\": \"ordinary|personal|private\", "
        "\"requires_recheck\": true, "
        "\"copy\": {\"title\": \"\", \"body\": \"\", "
        "\"public_title\": \"\", \"public_body\": \"\"}}\n\n"
        "`copy` only for `push`. Write everything a person reads in "
        "their language, with no ids and no jargon."
    )

    data = await _ask_model(_DISCIPLINE + "\n\n" + instruction, _dump(context))
    if not isinstance(data, dict):
        return None
    mode = str(data.get("mode") or "").strip().lower()
    if mode not in ("silence", "quiet_presence", "in_app", "push"):
        return None
    data["mode"] = mode
    return data


async def describe_ambient(
    activity: Dict[str, Any],
    *,
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Say what ORA actually did, in one line, without embellishing it.

    The input is a record of work that really happened. The job is to say it
    plainly — and to say it smaller when it was smaller. "Ho ricontrollato
    tutto" about a review that could not reach half its sources is the kind of
    small confident lie that makes a product feel untrustworthy long before
    anybody can say why.
    """
    instruction = (
        "Below is work ORA actually did. Write one short line telling "
        "this person what happened, in their language.\n\n"
        "Rules, and they matter more than the phrasing:\n"
        "- claim only what the record shows. If some sources could not be "
        "checked, say what was checked rather than implying everything "
        "was.\n"
        "- «tutto tranquillo» is only honest when a real review ran and "
        "reached what it needed. Otherwise say something truer and "
        "smaller.\n"
        "- no reassurance theatre: never «sto lavorando per te», «sto "
        "monitorando», «ho controllato tutto».\n"
        "- no implementation words. Nobody says «scan» about their own "
        "life.\n"
        "- it is a note, not an announcement. Quiet, ordinary, and "
        "possible to ignore.\n\n"
        "If nothing here is worth a person reading, say so with "
        "`worth_saying: false` — a line that adds nothing is worse than "
        "no line.\n\n"
        "Return JSON: {\"worth_saying\": true, "
        "\"line\": \"one short sentence\"}"
    )

    data = await _ask_model(_DISCIPLINE + "\n\n" + instruction, _dump(activity))
    if not isinstance(data, dict):
        return None
    if not data.get("worth_saying"):
        return {"worth_saying": False, "line": ""}
    line = str(data.get("line") or "").strip()
    if not line:
        return None
    return {"worth_saying": True, "line": line[:200]}


def _dump(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)[:9000]
