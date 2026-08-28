"""
Know before asking.

This is the step that decides whether ORA is a guide or an intake form. Every
variable the next step needs is looked for in what ORA already holds — the
turn that just happened, the work in progress, governed memory, the profile,
the life graph, documents, and answers the person has already given — before
anything reaches them as a question.

It deliberately does not retrieve anything itself. The Context Broker already
knows how to ask every source ORA has, with authority and provenance attached;
a second retrieval path here would drift from it and would have to be governed
twice. This module decides *what to look for* and *whether what came back
answers it*, and hands the looking to the broker.

The judgement is conservative on purpose. A variable is only treated as known
when the evidence is specific enough to have plausibly been about it: a wrong
"I already know this" is worse than one extra question, because the person
never finds out what ORA thought it knew.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from guidance.models import Origin, Variable

logger = logging.getLogger("ora.guidance")

# How much of the person's own knowledge one pass may pull in. Bounded because
# a resolution step that reads everything is a retrieval system, not a lookup.
MAX_FACTS_PER_VARIABLE = 6

# Words that carry no discriminating power in either language the product uses.
_STOP = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "a", "da",
    "in", "con", "su", "per", "tra", "fra", "del", "della", "dei", "delle",
    "che", "e", "o", "il tuo", "tuo", "tua", "quanto", "quale", "qual",
    "the", "a", "an", "of", "to", "for", "and", "or", "your", "you", "is",
}


# Italian elides its articles onto the next word: "l'importo", "dell'immobile".
# Left glued, the person can say the exact thing ORA is missing and ORA will
# not recognise its own word.
_ELISION = re.compile(r"^(?:l|d|un|all|dell|nell|sull|dall|quell|c|n)'")


def _tokens(text: str) -> set:
    words = re.findall(r"[\w']+", (text or "").lower())
    out = set()
    for w in words:
        w = _ELISION.sub("", w)
        if len(w) > 2 and w not in _STOP:
            out.add(w)
    return out


def _fact_text(fact: Any) -> str:
    """A ContextFact carries its content under two historical names."""
    return str(getattr(fact, "statement", "") or getattr(fact, "fact", "") or "")


def _fact_source(fact: Any) -> str:
    return str(getattr(fact, "source", "") or "unknown")


# Which `Origin` a retrieved fact counts as. The broker's source names are the
# vocabulary; anything unrecognised is still real knowledge, recorded honestly
# as memory rather than silently upgraded to something stronger.
_ORIGIN_BY_SOURCE: Dict[str, Origin] = {
    "profile": "profile",
    "memory": "memory",
    "life_os": "life_os",
    "goals": "life_os",
    "situations": "memory",
    "files": "document",
    "life_context_graph": "memory",
}


# Sources that describe the work rather than state a value. ORA's own
# situation and plan records are its restatement of what the person asked for,
# so resolving a variable from them is resolving it from the question. Found
# live: a situation reading "…in attesa di specificare data e ora" made ORA
# decide it already knew the date it was, in the same sentence, waiting for.
_SOURCES_THAT_DESCRIBE_WORK = {"situations", "goals", "life_os", "plan"}


def states_values(source: str) -> bool:
    return (source or "").strip().lower() not in _SOURCES_THAT_DESCRIBE_WORK


def origin_for(source: str) -> Origin:
    return _ORIGIN_BY_SOURCE.get((source or "").strip().lower(), "memory")


def _matches(variable: Variable, fact_text: str) -> bool:
    """
    Is this fact plausibly *about* the thing we are missing?

    Token overlap between what the variable is *called* and what the fact says.
    Crude on purpose: the alternative is a semantic matcher, which would be a
    second reasoning system making silent claims about the person's life. When
    it is unsure it says no, and ORA asks — which is recoverable.

    `purpose` is deliberately excluded. It describes why the next step needs
    this, not what it is, and several variables serving one step share it —
    so matching on it made every variable in a bundle "already known" the
    moment the person mentioned the step. A false "I already know this" is the
    one error here that never surfaces: the person is simply never asked, and
    never finds out what ORA thought it had.
    """
    label = _tokens(variable.label)
    # The ref is a machine name nobody says out loud. It can stand in when
    # there is no label; it is never part of what has to be matched, or a
    # one-word label could not be recognised at all.
    ref = _tokens(variable.ref.replace("_", " "))
    wanted = label or ref
    if not wanted:
        return False
    found = _tokens(fact_text)
    # A ref of two words or more, present in full, is its own evidence: a
    # `durata_mutuo` inside "la durata del mutuo preferita è 25 anni" is about
    # that and nothing else. It catches what a differently-worded label misses
    # — "durata del piano di rimborso" shares only one word with that sentence
    # — without loosening the rule below.
    if len(ref) >= 2 and ref <= found:
        return True
    # Everything the thing is *called* has to be in there. Partial overlap is
    # what made ORA claim it knew things it had only heard named: "fissa
    # l'appuntamento dal notaio" shares two words with "data e ora
    # dell'appuntamento dal notaio", and a date it was never told became
    # "already known". Naming a thing is not stating its value.
    return bool(wanted <= found)


def resolve_from_turn(variables: Sequence[Variable], user_message: str) -> int:
    """
    What the person just said, before anything else is consulted.

    Asking for something contained in the sentence that triggered the question
    is the most visible way a system can fail to listen.
    """
    resolved = 0
    for v in variables:
        if v.resolved or not user_message:
            continue
        if _matches(v, user_message):
            v.origin = "user_turn"
            v.resolved_note = "detto in questo messaggio"
            resolved += 1
    return resolved


def resolve_from_answers(
    variables: Sequence[Variable], answered_refs: Iterable[str]
) -> int:
    """
    Things the person has already answered — including "I would rather not".

    A refusal is an answer. Re-asking it is the loop §58 forbids, and it reads
    as ORA not having heard.
    """
    known = {str(r).strip() for r in answered_refs if str(r).strip()}
    resolved = 0
    for v in variables:
        if v.resolved or v.ref not in known:
            continue
        v.origin = "prior_answer"
        v.resolved_note = "già risposto"
        resolved += 1
    return resolved


def mark_declined(variables: Sequence[Variable], declined_refs: Iterable[str]) -> int:
    declined = {str(r).strip() for r in declined_refs if str(r).strip()}
    n = 0
    for v in variables:
        if v.ref in declined and v.origin == "unresolved":
            v.origin = "declined"
            v.resolved_note = "preferisce non dirlo"
            n += 1
    return n


def resolve_from_facts(variables: Sequence[Variable], facts: Sequence[Any]) -> int:
    """Match what the broker returned against what is still missing."""
    resolved = 0
    for v in variables:
        if v.resolved:
            continue
        for fact in facts[: MAX_FACTS_PER_VARIABLE * 4]:
            if not states_values(_fact_source(fact)):
                continue
            text = _fact_text(fact)
            if not text or not _matches(v, text):
                continue
            v.origin = origin_for(_fact_source(fact))
            # A trace, not the value: a resolved sensitive variable must not
            # leave its content in a log line or a trace payload.
            v.resolved_note = (
                "già noto" if v.sensitivity != "normal" else text[:120]
            )
            resolved += 1
            break
    return resolved


async def resolve_from_knowledge(
    variables: Sequence[Variable],
    *,
    db: Any,
    user_id: str,
    user_message: str = "",
    active_goal: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
) -> int:
    """
    Ask ORA's own sources, once, for everything still missing.

    One retrieval for the whole set rather than one per variable: the broker
    ranks across every source it has, and a query per variable would multiply
    reads without improving the answer.
    """
    pending = [v for v in variables if not v.resolved]
    if not pending or db is None or not user_id:
        return 0

    try:
        from conversation_engine.ai_core.context_broker import ContextBroker
        from conversation_engine.ai_core.models import ContextNeed

        query = "; ".join(
            (v.label or v.ref) for v in pending[:8] if (v.label or v.ref)
        )[:400]
        need = ContextNeed(
            query=query,
            purpose="Verificare quali di queste informazioni ORA conosce già.",
            desired_evidence=[(v.label or v.ref)[:120] for v in pending[:6]],
            max_items=8,
        )
        facts = await ContextBroker(db).retrieve(
            user_id=user_id,
            user_message=user_message,
            active_goal=active_goal,
            context_need=need,
            stage="B",
            session_id=session_id,
        )
    except Exception:
        # Retrieval failing means ORA does not know, which is the safe answer:
        # it asks. It must never mean the turn fails.
        logger.info("guidance knowledge lookup soft-fail", exc_info=True)
        return 0

    return resolve_from_facts(pending, facts or [])
