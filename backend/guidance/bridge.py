"""
Where the reasoning's vocabulary meets guidance's.

The AI Core describes what it is missing as `MissingInformation`; guidance
reasons about `Variable`. Keeping the translation in one small module means the
cognitive contract and the constitutional rules can each change without the
other having to know, and it is the only place that has to be read to answer
"what exactly does the model have to say for a question to be allowed?".

It also carries the two adaptations V3.1 needs in order to receive a bundle:
the requested variables travel with the question, so a partial answer can be
told apart from a complete one, and a refusal can be recorded per variable
rather than for the whole request.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from guidance.models import Variable

# A `strategy` of "ask" was the old way of saying "this has to come from the
# person". `necessity` says something stronger and more useful — whether the
# next step is impossible without it — so both are honoured: an explicit
# `required` wins, and a legacy `blocking` ask is treated as required.
_REQUIRED_STRATEGIES = {"ask"}


def variables_from_missing(items: Sequence[Any], *, blocking_default: bool = False) -> List[Variable]:
    """Translate what the reasoning said it lacks into what guidance judges."""
    out: List[Variable] = []
    for item in items or []:
        ref = str(getattr(item, "ref", "") or "").strip()
        if not ref:
            continue
        stated = getattr(item, "necessity", None)
        if stated in ("required", "useful", "optional"):
            # The model said. Nothing here second-guesses it — an explicit
            # "useful" must not be promoted into a question by the fact that
            # the turn as a whole was blocking.
            necessity = str(stated)
        else:
            # It did not say. Decisions written before `necessity` existed
            # expressed the same thing differently: an information need marked
            # blocking that the model wanted to ask about was, in the only
            # sense that matters, required.
            necessity = (
                "required"
                if (
                    bool(getattr(item, "blocking", False) or blocking_default)
                    and str(getattr(item, "strategy", "")) in _REQUIRED_STRATEGIES
                )
                else "useful"
            )

        sensitivity = str(getattr(item, "sensitivity", "") or "normal")
        if sensitivity not in ("normal", "sensitive", "high"):
            sensitivity = "normal"

        out.append(
            Variable(
                ref=ref[:120],
                label=str(getattr(item, "label", "") or getattr(item, "description", "") or ref)[:160],
                purpose=str(getattr(item, "purpose", "") or "")[:240],
                necessity=necessity,  # type: ignore[arg-type]
                sensitivity=sensitivity,  # type: ignore[arg-type]
            )
        )
    return out


def _step_binding(outcome: Any) -> Dict[str, Any]:
    """
    Which step this question belongs to, taken from the decision that made it.

    Without this the question travelled alone and the work it was shown under
    came from the session's current plan item — whatever that happened to be.
    Live, a question about scheduling a meeting was labelled "Definire la data
    esatta di fine rapporto": two different steps, one row, and no way for the
    person to tell which one they were answering.
    """
    step = getattr(outcome, "next_step", None)
    ref = str(getattr(step, "milestone_ref", "") or "") or None
    title = str(getattr(step, "title", "") or "")[:160]
    plan_item_id = None
    state = getattr(outcome, "state", None)
    for milestone in list(getattr(state, "milestones", None) or []):
        if ref and getattr(milestone, "ref", None) == ref:
            plan_item_id = getattr(milestone, "plan_item_id", None)
            title = title or str(getattr(milestone, "title", "") or "")[:160]
            break
    return {
        "step_title": title,
        "milestone_ref": ref,
        "plan_item_id": str(plan_item_id) if plan_item_id else None,
    }


def blocking_ask_payload(
    outcome: Any,
    *,
    fallback_question: str = "",
) -> Dict[str, Any]:
    """
    The shape V3.1 persists, carrying what guidance decided.

    `requested_variables` is the addition: without it a bundle is a sentence
    and a partial answer is unreadable, because nothing records which of the
    things asked for were actually needed.
    """
    step = outcome.next_step
    requested = list(step.requested or [])
    return {
        "question": (step.question or fallback_question or "").strip()[:600],
        "why_needed": (step.why_needed or "")[:400],
        "asked_refs": [v.ref for v in requested][:8],
        "answer_kind": "bundle" if len(requested) > 1 else "free_text",
        "sensitive": any(v.sensitivity != "normal" for v in requested),
        "requested_variables": [
            {
                "ref": v.ref,
                "label": v.label,
                "purpose": v.purpose,
                "required": v.necessity == "required",
            }
            for v in requested
        ][:10],
        # Kept for observability, never shown: how many things the person did
        # not have to be asked because ORA already knew them.
        "avoided": int(getattr(outcome, "avoided", 0) or 0),
        # The step this came from, so what is stored and what is shown cannot
        # drift apart from what was decided.
        **_step_binding(outcome),
    }


def resolution_observation(outcome: Any) -> Dict[str, Any]:
    """
    What to hand the reasoning when a question turned out to be unnecessary.

    The model asked; ORA found the answers it was missing. Rather than emitting
    that question, the loop tells the model what is now known and lets it think
    again — which is the difference between suppressing a question and actually
    answering it.

    Sensitive values are named, not quoted: the reasoning needs to know the
    variable is available, not to have it repeated into a prompt.
    """
    known = [v for v in outcome.sufficiency.variables if v.resolved]
    deferred = outcome.sufficiency.deferred()
    return {
        "failure_code": "INFORMATION_ALREADY_KNOWN",
        "reason": (
            "You asked for information ORA already has. Do not ask for it again: "
            "continue with the next step using these values, and only ask for "
            "something that is genuinely required and genuinely unknown."
        ),
        "resolved": [
            {
                "ref": v.ref,
                "label": v.label,
                "from": v.origin,
                "note": v.resolved_note if v.sensitivity == "normal" else "già noto",
            }
            for v in known
        ][:8],
        "not_required_now": [v.ref for v in deferred][:8],
    }


def declined_refs_from(history: Iterable[Any]) -> List[str]:
    """
    Which variables the person has already declined to give.

    A refusal is an answer, and re-asking it is the loop the design forbids.
    The record lives on the session's clarification history, which the loop
    already keeps for its own purposes.
    """
    out: List[str] = []
    for entry in history or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("declined") and entry.get("key"):
            out.append(str(entry["key"])[:120])
    return out
