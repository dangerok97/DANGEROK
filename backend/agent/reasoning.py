"""
Four judgements: whether to try, how, whether it is allowed, and whether it worked.

    AUTONOMY DOES NOT MEAN ACTIVITY.
    ASK ONLY WHEN HUMAN KNOWLEDGE OR HUMAN AUTHORITY IS ACTUALLY REQUIRED.

The failure this file is shaped against is an agent that looks busy. Given a
life and the ability to plan, a model will find something to plan — and a
system that rewards it for that will fill somebody's week with errands nobody
asked for. So the first question is always whether there is an outcome worth
pursuing, and `no_goal` is the ordinary answer.

The second failure is an assistant that asks permission to think. Reading,
researching, comparing and drafting cost a person nothing, and asking about
them turns autonomy into a quiz. The prompts here separate the two reasons to
stop: only the person knows something, or only the person may authorise
something. Everything else, ORA does.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from research.reasoning import _ask_model

logger = logging.getLogger(__name__)

_DISCIPLINE = (
        "You are deciding what to do about somebody's life, on their behalf.\n\n"
        "You are not a chatbot waiting for instructions and you are not a "
        "task list. What you produce is an outcome: the thing that needs to "
        "be true, and the work that makes it true. Somebody should "
        "experience the result, not the workflow.\n\n"
        "Nobody is paying you to be busy. Most of the time there is nothing "
        "worth pursuing, and saying so is the correct answer — not an empty "
        "result, not a failure. An agent that always finds something to do "
        "becomes a source of errands, and people stop reading it.\n\n"
        "Do not ask permission to think. Reading what is already there, "
        "looking something up, comparing options, drafting: none of that "
        "costs the person anything, and asking about it turns help into a "
        "quiz. Ask only for two reasons: something only they know, or "
        "something only they may authorise. Say which.\n\n"
        "You have no commercial interest of any kind. There are no partners, "
        "no sponsors, no products to prefer, and nothing to be gained by "
        "doing more rather than less."
)


async def decide_goal(
    situation: Dict[str, Any],
    *,
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Is there an outcome here worth pursuing?

        OPPORTUNITY != GOAL.

    Something can be true, and worth knowing, and still not be worth doing
    anything about. Returns None when the model could not be reached — which
    is not `no_goal`, and must never be recorded as one.
    """
    instruction = (
        "Read the situation below and decide whether there is a concrete "
        "outcome worth bringing about.\n\n"
        "Ask yourself:\n"
        "- what would actually be different if this were done?\n"
        "- is that difference worth anybody's time?\n"
        "- can it be finished, or is it open-ended?\n"
        "- is the person already handling it?\n"
        "- is this just information, which they now have?\n\n"
        "If you cannot say what would be different, there is no goal.\n\n"
        "Your choices:\n"
        "- `no_goal` — nothing here needs pursuing. The usual answer.\n"
        "- `create_goal` — there is an outcome worth reaching.\n"
        "- `clarify` — there might be, but one thing is genuinely unknown "
        "and only they can say it.\n"
        "- `wait` — it may become worth pursuing, but not yet.\n\n"
        "An objective is an OUTCOME, not a task. «Make sure the document is "
        "in hand before the appointment» is an outcome. «Open the website», "
        "«send an email», «check the calendar» are steps, and steps are not "
        "your business here.\n\n"
        "Return JSON: {\"outcome\": \"no_goal|create_goal|clarify|wait\", "
        "\"reasoning\": \"one short sentence\"}\n\n"
        "For `create_goal` add: {\"objective\": \"the outcome, in "
        "one sentence\", \"desired_outcome\": \"what will be true "
        "when it is done\", \"why_now\": \"...\", "
        "\"success_criteria\": [], \"stop_conditions\": [], "
        "\"evidence_refs\": []}\n\n"
        "For `clarify` add: {\"question\": \"the one thing only they "
        "can answer\"}\n\n"
        "Write anything a person reads in their language."
    )

    data = await _ask_model(_DISCIPLINE + "\n\n" + instruction, _dump(situation))
    if not isinstance(data, dict):
        return None
    outcome = str(data.get("outcome") or "").strip()
    if outcome not in ("no_goal", "create_goal", "clarify", "wait"):
        return None
    data["outcome"] = outcome
    return data


async def make_plan(
    goal: Dict[str, Any],
    *,
    capabilities: List[Dict[str, Any]],
    context: Dict[str, Any],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    How to reach it — in terms of what is needed, never of what to call.

    The model is shown what ORA can do and what it cannot, with the reason.
    Told only about what works it will plan around a gap it cannot see; told
    nothing it will invent a tool.
    """
    instruction = (
        "Work out how to reach this outcome.\n\n"
        "Each step says what it is FOR and what it needs to be able to do — "
        "never which service to call or which button to press. Say "
        "`capability_needed` using only the names in the list you are given. "
        "If what you need is not there, plan around it or say plainly that "
        "it cannot be done; do not assume something exists.\n\n"
        "Step types:\n"
        "- `inspect` — look at what ORA already holds.\n"
        "- `research` — find something out.\n"
        "- `compare` — weigh alternatives.\n"
        "- `prepare` — produce something without touching the world.\n"
        "- `ask_user` — only for what one person alone can supply.\n"
        "- `execute` — change something in the world.\n"
        "- `verify` — check the outcome is actually true.\n"
        "- `wait` — depend on something that has not happened yet.\n\n"
        "Do the work before you ask. Everything that can be found out, "
        "compared or drafted should be a step you take, so that when you do "
        "reach them, the sentence is «this is ready, may I» and not «what "
        "would you like me to do».\n\n"
        "Plan the shortest route that actually gets there. Extra steps are "
        "not thoroughness; they are cost and delay. End with a way of "
        "checking the outcome, because something completing is not the same "
        "as the outcome being true.\n\n"
        "For every `execute` step say whether it changes something outside "
        "ORA (`external_effect`) and how hard that would be to undo "
        "(`reversibility`: easily, with_effort, hardly, irreversible).\n\n"
        "Return JSON: {\"plan_summary\": \"one sentence\", "
        "\"expected_outcome\": \"...\", \"assumptions\": [], "
        "\"known_constraints\": [], \"steps\": ["
        "{\"intent\": \"what this step is for\", "
        "\"step_type\": \"inspect|research|compare|prepare|ask_user|"
        "execute|verify|wait\", \"capability_needed\": \"\", "
        "\"expected_result\": \"\", \"external_effect\": false, "
        "\"reversibility\": \"easily\", \"asks\": \"\", "
        "\"ask_kind\": null}]}\n\n"
        "`asks` only on `ask_user` steps, with `ask_kind` set to "
        "\"knowledge\" when only they know the answer, or \"authority\""
        " when you know what to do and may not do it. Ask the smallest "
        "question that unblocks the plan, and never ask for something you "
        "were already told."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump({"goal": goal, "what_ora_can_do": capabilities, "context": context}),
    )
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        return None
    return data


async def assess_authority(
    step: Dict[str, Any],
    *,
    goal: Dict[str, Any],
    facts: Dict[str, Any],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    What kind of act is this, really?

    A judgement about meaning, which is why it is worth asking: «send this
    email» is a different act depending on who it reaches and what it says,
    and no table of capabilities knows that. What comes back is a
    recommendation — code narrows it and may refuse it outright.
    """
    instruction = (
        "You are about to do something. Say what kind of act it is.\n\n"
        "Weigh it honestly:\n"
        "- could it be undone, and at what cost?\n"
        "- does it reach anybody other than this person?\n"
        "- does it commit them to anything, or cost them money?\n"
        "- does it reveal something about them?\n"
        "- would they be surprised to find it had happened?\n\n"
        "Your choices:\n"
        "- `proceed_autonomously` — routine, undoable, theirs alone, and "
        "they would not be surprised.\n"
        "- `prepare_then_confirm` — do all the work, then show them and ask.\n"
        "- `ask_before_execution` — they should decide before anything moves.\n"
        "- `needs_user_information` — something is missing that only they "
        "can supply.\n"
        "- `cannot_proceed` — it should not happen this way at all.\n\n"
        "Reading, researching, comparing and drafting are not acts on the "
        "world. Do not ask about them.\n\n"
        "What you say here is a recommendation. It can be made more "
        "cautious afterwards and never less, so do not reach for permission "
        "you would not defend.\n\n"
        "Return JSON: {\"outcome\": \"proceed_autonomously|"
        "prepare_then_confirm|ask_before_execution|needs_user_information|"
        "cannot_proceed\", \"reasoning\": \"one short sentence\", "
        "\"reversibility\": \"easily|with_effort|hardly|irreversible\", "
        "\"financial_effect\": false, \"external_communication\": false, "
        "\"third_party_impact\": false, \"privacy_disclosure\": false, "
        "\"legal_effect\": false, \"security_effect\": false}"
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump({"about_to_do": step, "for_this_goal": goal, "what_is_known": facts}),
    )
    if not isinstance(data, dict):
        return None
    outcome = str(data.get("outcome") or "").strip()
    if outcome not in (
        "proceed_autonomously", "prepare_then_confirm", "ask_before_execution",
        "needs_user_information", "cannot_proceed",
    ):
        return None
    data["outcome"] = outcome
    return data


async def reconsider(
    goal: Dict[str, Any],
    *,
    plan: Dict[str, Any],
    what_happened: Dict[str, Any],
    capabilities: List[Dict[str, Any]],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Something happened. Does the plan still make sense?

    Deliberately not "write a new plan": a plan rewritten from scratch after
    every observation loses everything already learned and costs a full
    generation each time. What is asked for is the smallest change that
    accounts for what happened.
    """
    instruction = (
        "A step has finished, or failed, or turned out differently. Decide "
        "what to do with the rest of the plan.\n\n"
        "Your choices:\n"
        "- `continue` — nothing needs changing.\n"
        "- `modify` — some remaining steps should change. Give only those.\n"
        "- `wait` — it depends on something that has not happened yet; say "
        "roughly how long is worth waiting.\n"
        "- `ask` — it is blocked on the person. Say which kind and what.\n"
        "- `abandon` — it is not going to work, or is no longer worth it.\n"
        "- `complete` — the outcome has been reached.\n\n"
        "Prefer the smallest change that accounts for what happened. "
        "Rewriting a plan from scratch throws away what has already been "
        "learned. If a capability was unavailable, find another route or say "
        "plainly that there is none — do not retry the same thing hoping.\n\n"
        "Return JSON: {\"decision\": \"continue|modify|wait|ask|"
        "abandon|complete\", \"reasoning\": \"one short sentence\", "
        "\"revised_steps\": [], \"wait_hours\": null, "
        "\"asks\": \"\", \"ask_kind\": null}\n\n"
        "`revised_steps` only for `modify`, in the same shape as a plan step."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump({
            "goal": goal,
            "plan": plan,
            "what_happened": what_happened,
            "what_ora_can_do": capabilities,
        }),
    )
    if not isinstance(data, dict):
        return None
    decision = str(data.get("decision") or "").strip()
    if decision not in ("continue", "modify", "wait", "ask", "abandon", "complete"):
        return None
    data["decision"] = decision
    return data


async def verify_goal(
    goal: Dict[str, Any],
    *,
    evidence: Dict[str, Any],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Is the outcome actually true?

        A TOOL RETURNING SUCCESS IS NOT THE GOAL BEING ACHIEVED.

    An email accepted by a server has not been read. A form submitted is not
    a booking. This is the question that keeps ORA from telling somebody
    their problem is solved because a call returned 200.
    """
    instruction = (
        "Look at what was found and decide whether the outcome is actually "
        "true — not whether the steps finished.\n\n"
        "Something completing is not the same as the thing being so. A "
        "message accepted has not been read; a request submitted has not "
        "been agreed to; a page that loaded does not mean what was on it is "
        "still true tomorrow. Be honest about the gap.\n\n"
        "You are given evidence, and each piece says where it came from. "
        "Anything marked as a simulation did not happen: it is a stand-in "
        "used to exercise the machinery, and it proves nothing whatsoever "
        "about the world. If the only thing supporting this outcome is a "
        "simulation, the outcome has not been achieved.\n\n"
        "Evidence also says how old it is. Old is not the same as wrong — "
        "say what you are relying on and how much weight it bears.\n\n"
        "Say which success criterion each conclusion rests on. A criterion "
        "with nothing behind it is not met, however well the steps went.\n\n"
        "Your choices:\n"
        "- `achieved` — it is true, and you can say why.\n"
        "- `partially_achieved` — part of it holds; say which part does not.\n"
        "- `not_achieved` — it did not work.\n"
        "- `uncertain` — you genuinely cannot tell from what you have.\n"
        "- `needs_followup` — something more has to happen.\n"
        "- `waiting_for_external_result` — it depends on somebody else, and "
        "there is nothing to do but look again later.\n\n"
        "Return JSON: {\"outcome\": \"achieved|partially_achieved|"
        "not_achieved|uncertain|needs_followup|waiting_for_external_result\", "
        "\"reasoning\": \"one short sentence\", "
        "\"what_is_missing\": \"\", \"revisit_in_hours\": null, "
        "\"relied_on\": [], \"criteria_met\": []}"
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump({"goal": goal, "what_was_done": evidence}),
    )
    if not isinstance(data, dict):
        return None
    outcome = str(data.get("outcome") or "").strip()
    if outcome not in (
        "achieved", "partially_achieved", "not_achieved", "uncertain",
        "needs_followup", "waiting_for_external_result",
    ):
        return None
    data["outcome"] = outcome
    return data


async def choose_next_action(
    goal: Dict[str, Any],
    *,
    plan: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
    capabilities: List[Dict[str, Any]],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Which of the things still to do is the useful one now.

        A PLAN IS STATE, NOT A SCRIPT.

    The reason this is a judgement rather than an increment: a plan is written
    before anything is known, and what the first steps found routinely makes
    a later one pointless, premature, or already answered. Walking the list in
    order would carry out a step whose reason evaporated two steps ago — which
    looks like diligence and is waste.

    What comes back is a choice among things that already exist, plus the
    option of saying that none of them is right. Code decides nothing here and
    the model executes nothing; it names a step and says why.
    """
    instruction = (
        "Work is under way on this outcome. Some of the plan is done and "
        "some is not. Decide what is worth doing next.\n\n"
        "You are shown what has already been found out. Use it. A step that "
        "was going to look something up you now know is finished, not "
        "pending. A step that assumed something the evidence contradicts "
        "should not be carried out because it is next in the list.\n\n"
        "Your choices:\n"
        "- `execute` — carry out one of the steps still to do. Say which.\n"
        "- `skip` — one of them is no longer worth doing. Say which and why.\n"
        "- `verify` — enough has been found; check whether the outcome holds.\n"
        "- `wait` — it depends on something that has not happened yet.\n"
        "- `ask` — it is blocked on the person, and only on the person.\n"
        "- `replan` — what was found means the route has to change.\n"
        "- `complete` — the outcome is already true.\n\n"
        "Do everything you can before you reach for `ask`. Looking "
        "something up, reading what is already held, comparing, drafting: "
        "all of that is yours to do, and asking about it wastes their time "
        "and yours. Ask only when the answer exists nowhere except in their "
        "head, or when only they may authorise what comes next.\n\n"
        "Prefer finishing to elaborating. Extra work is not thoroughness.\n\n"
        "Return JSON: {\"decision\": \"execute|skip|verify|wait|ask|"
        "replan|complete\", \"step_id\": \"\", "
        "\"reasoning\": \"one short sentence\", "
        "\"asks\": \"\", \"ask_kind\": null, \"wait_hours\": null}\n\n"
        "`step_id` must be one of the ids you were given, for `execute` and "
        "`skip`. `ask_kind` is \"knowledge\" when only they know the "
        "answer and \"authority\" when you know what to do and may not do "
        "it."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump({
            "goal": goal,
            "plan": plan,
            "still_to_do": candidates,
            "what_has_been_found": evidence,
            "what_ora_can_do": capabilities,
        }),
    )
    if not isinstance(data, dict):
        return None
    decision = str(data.get("decision") or "").strip()
    if decision not in (
        "execute", "skip", "verify", "wait", "ask", "replan", "complete"
    ):
        return None
    data["decision"] = decision
    return data


async def decide_visibility(
    goal: Dict[str, Any],
    *,
    what_happened: Dict[str, Any],
    already_said: List[Dict[str, Any]],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Is this worth their knowing, and in what words?

        SILENCE IS A VALID DECISION, NOT A DEFAULT PERSONALITY.
        DO NOT CONFUSE AVOIDING INTERRUPTION WITH HIDING USEFUL WORK.

    The failure this exists against is subtle, and it is the failure a
    well-built quiet system falls into. Having learned not to interrupt, it
    learns not to speak; having learned that most things are not worth a
    notification, it concludes that most things are not worth mentioning. The
    result is an assistant that works hard and appears to do nothing, which
    is indistinguishable from one that does nothing.

    The opposite failure is cheaper to reach and easier to spot: an assistant
    that narrates. Both are named below, because a prompt that warns against
    one always produces the other.

    This decides worth, not channel. Whether anything interrupts is V3.8's
    question and stays there.
    """
    instruction = (
        "ORA has just done some work on somebody's behalf. Decide whether "
        "that is worth them knowing, and if so, what to say.\n\n"
        "Do not confuse avoiding interruption with hiding useful work.\n\n"
        "If ORA has done meaningful work, changed something relevant, found "
        "something useful, reached a decision, or needs the person, decide "
        "whether that should be made visible.\n\n"
        "Silence is correct only when showing the update would add no "
        "meaningful value.\n\n"
        "Your choices:\n"
        "- `silent` — there is nothing useful to say. Often right.\n"
        "- `quiet_update` — real work worth seeing, not worth a moment of "
        "their attention. Put it somewhere they will find it.\n"
        "- `inform_user` — they should know the result. Nothing is being "
        "asked of them.\n"
        "- `ask_user` — something is needed that only they know, or only "
        "they may allow.\n"
        "- `requires_attention` — without them this cannot go on, or the "
        "result matters enough to say so plainly.\n\n"
        "Never say any of these things:\n"
        "- that you are working, without saying what you found;\n"
        "- that you checked something, when nothing had changed;\n"
        "- anything you have already said (you are shown what you said);\n"
        "- one line per step;\n"
        "- congratulations, encouragement, or anything written to be liked.\n\n"
        "A person reading this wants to know whether a thing in their life "
        "is handled. Write one sentence they would say themselves. Never "
        "mention steps, tools, capabilities, plans, providers, confidence "
        "or how many of anything.\n\n"
        "Return JSON: {\"outcome\": \"silent|quiet_update|inform_user|"
        "ask_user|requires_attention\", "
        "\"headline\": \"one sentence, empty when silent\", "
        "\"reasoning\": \"one short sentence, never shown to them\", "
        "\"about\": \"a few words naming what this update is about\"}\n\n"
        "`about` is how the same news is recognised if it comes round again. "
        "Write anything a person reads in their language."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump({
            "goal": goal,
            "what_ora_did": what_happened,
            "what_they_have_already_been_told": already_said,
        }),
    )
    if not isinstance(data, dict):
        return None
    outcome = str(data.get("outcome") or "").strip()
    if outcome not in (
        "silent", "quiet_update", "inform_user", "ask_user", "requires_attention"
    ):
        return None
    data["outcome"] = outcome
    return data


def _dump(payload: Dict[str, Any]) -> str:
    """
    What the model is shown, bounded.

    Truncation is a privacy boundary as much as a cost one: a payload that
    can grow without limit is a payload that eventually carries somebody's
    inbox into a prompt.
    """
    return json.dumps(payload, ensure_ascii=False, default=str)[:9000]
