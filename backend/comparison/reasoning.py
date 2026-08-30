"""
The three places a comparison thinks, and they are all the model.

    frame_decision       what matters here, what is absolute, what to work out
    assess_alternatives  what each one is good and bad at, and what trades off
    recommend            what ORA would say, or that it cannot say it yet

Between the first and the second, the code does the arithmetic and checks the
constraints. That order is the whole design: the model decides what to compute
and what is non-negotiable, Python produces the numbers and the verdicts on
those conditions, and the model reads the results back and interprets them.

No criteria live in this file. What matters for a loan and what matters for a
language course are both written by the model, from the same prompt, and the
prompt describes *how to weigh a decision* rather than any decision in
particular. If a list of criteria appeared here, ORA would have stopped
thinking about the person in front of it.

The model plumbing — one JSON answer, validated, trimmed to the contract — is
V3.4's and is imported rather than rewritten.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from comparison.models import (
    Alternative,
    ComparisonCriterion,
    ComparisonNeed,
    ComparisonRun,
    Computation,
    Constraint,
    Recommendation,
)
from research.reasoning import _ask_model, _fit

logger = logging.getLogger("ora.comparison.reasoning")


_DISCIPLINE = """You are the part of ORA that helps somebody choose.

You are not ranking products. You are working out what this decision turns on
for this particular person, and whether one of the options in front of them is
actually the one to take.

Hold to these:

- Decide what matters here. Not what usually matters for things like this —
  what matters given what you know about them. Say why each thing matters, and
  when it matters because of something about them, say which thing.
- Separate what is absolute from what is preferred. An absolute requirement
  rules an option out; a preference makes it better or worse. Most things are
  preferences.
- Every fact you use about an option has to have come from somewhere: the
  evidence you were given, or something they told you. If you cannot point at
  where a fact came from, do not use it.
- Do not do arithmetic. Say which figures need working out and the code will
  work them out, then you read the results.
- Do not flatten a real trade-off into an order. "A costs less, B costs more
  and removes a risk that matters to them" is the answer, not a step towards
  one. If it depends on what they care about most, say so and say which way
  each way goes.
- There does not have to be a winner. If you do not know enough to say
  responsibly, say that instead, and say what would settle it. Recommending
  something because a recommendation was asked for is the one thing you must
  not do.
- Nobody is paying you. No option gets an advantage for any reason other than
  being better for this person.

Answer with one JSON object and nothing else."""


async def frame_decision(
    need: ComparisonNeed,
    *,
    alternatives: List[Alternative],
    evidence: List[Dict[str, Any]],
    personal_context: List[str],
) -> Optional[Dict[str, Any]]:
    """
    What this decision turns on: criteria, what is absolute, what to compute.

    Also whether the alternatives are worth comparing at all, and what is
    missing — either from the world (more research) or from the person.
    """
    user = json.dumps(
        {
            "the_decision": need.decision,
            "why_now": need.purpose,
            "what_i_already_know_about_them": (need.already_known or []) + list(personal_context or []),
            "options_on_the_table": [
                {
                    "id": a.id,
                    "name": a.name,
                    "summary": a.summary,
                    "attributes": [
                        {
                            # This is the handle. Everything you say about this
                            # fact later has to quote it back exactly.
                            "attribute_id": at.id,
                            "label": at.name,
                            "value": at.value,
                            "number": at.number,
                            "unit": at.unit,
                            "from": at.source_ids or (["la persona"] if at.stated_by_user else []),
                        }
                        for at in a.attributes
                    ],
                }
                for a in alternatives
            ],
            "evidence_available": evidence,
            "produce": {
                "criteria": [
                    {
                        "name": "what matters",
                        "why_it_matters": "in one sentence",
                        "importance": "deal_breaker | major | moderate | minor",
                        "personal_basis": "what about them makes it matter this much, or empty",
                        "attribute_id": "the attribute_id it is about, if one is",
                    }
                ],
                "constraints": [
                    {
                        "name": "short name",
                        "attribute_id": "the attribute_id it applies to",
                        "operator": "<= | < | >= | > | == | != | in | not_in",
                        "value": "for text comparisons",
                        "number": "for numeric ones",
                        "unit": "the unit the number is in",
                        "why": "why this is absolute rather than preferred",
                        "personal_basis": "what about them makes it absolute",
                    }
                ],
                "computations": [
                    {
                        "name": "what the figure is",
                        "operation": "sum | difference | product | quotient | percent_of | percent_change",
                        "operands": ["attribute_ids, or literal numbers"],
                        "unit": "the unit of the result",
                        "why": "why comparing needs it",
                    }
                ],
                "not_comparable": ["ids of options that are not really comparable, and nothing else"],
                "missing_from_the_world": ["what evidence is still needed, if any"],
                "missing_from_them": [
                    "what only they can tell you AND that would actually change "
                    "the recommendation — leave empty if you can advise without it"
                ],
            },
            "note": (
                "Ask them for nothing you can already see above. A comparison "
                "that turns into an interview has failed them twice. "
                "Refer to things by the ids you were given. Every fact above "
                "has an attribute_id: quote it back exactly when you say a "
                "constraint applies to it or a calculation uses it. Do not "
                "retype the label, do not improve it, do not add the value to "
                "it. A label is for reading; an id is what makes the figure "
                "actually get worked out, and a reference that does not match "
                "one is dropped rather than guessed at."
            ),
        },
        ensure_ascii=False,
    )
    data = await _ask_model(_DISCIPLINE, user)
    if not data:
        return None
    return data


async def assess_alternatives(
    *,
    need: ComparisonNeed,
    alternatives: List[Alternative],
    criteria: List[ComparisonCriterion],
    computations: List[Computation],
    checks: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """What each option is good and bad at, once the figures are in."""
    user = json.dumps(
        {
            "the_decision": need.decision,
            "what_matters": [
                {
                    "name": c.name,
                    "why": c.why_it_matters,
                    "importance": c.importance,
                    "because_of_them": c.personal_basis,
                    "about_attribute": c.attribute_id or None,
                }
                for c in criteria
            ],
            "figures_worked_out_for_you": [
                {
                    "name": c.name,
                    "result": c.result,
                    "unit": c.unit,
                    "could_not_compute": c.failed_reason or None,
                    "for_alternative": c.alternative_id or None,
                    "from_inputs": c.inputs,
                }
                for c in computations
            ],
            "constraint_results": checks,
            "options": [
                {
                    "id": a.id,
                    "name": a.name,
                    "attributes": [
                        {
                            "attribute_id": at.id, "label": at.name, "value": at.value,
                            "number": at.number, "unit": at.unit,
                        }
                        for at in a.attributes
                    ],
                }
                for a in alternatives
            ],
            "produce": {
                "assessments": [
                    {
                        "alternative_id": "id",
                        "strengths": ["in words, tied to what matters"],
                        "weaknesses": ["likewise"],
                        "excluded": "true only if it breaches something absolute",
                        "excluded_because": "which requirement, and by how much",
                        "missing": ["what is not known about this one"],
                    }
                ],
                "trade_offs": [
                    {
                        "between": ["option names"],
                        "about": "what they cannot both be",
                        "detail": "which way each way goes",
                        "decided_by": "what about this person would settle it",
                    }
                ],
            },
            "note": (
                "A constraint that could not be checked is not a breach. Do not "
                "exclude an option for a figure nobody has — say it is unknown."
            ),
        },
        ensure_ascii=False,
    )
    data = await _ask_model(_DISCIPLINE, user)
    if not data:
        return None
    return data


async def recommend(
    *,
    run: ComparisonRun,
) -> Optional[Recommendation]:
    """What ORA would say, or that it cannot say it yet."""
    user = json.dumps(
        {
            "the_decision": run.need.decision,
            "what_matters": [
                {"name": c.name, "importance": c.importance, "because_of_them": c.personal_basis}
                for c in run.criteria
            ],
            "options": [
                {
                    "id": a.id,
                    "name": a.name,
                    "strengths": next(
                        (x.strengths for x in run.assessments if x.alternative_id == a.id), []
                    ),
                    "weaknesses": next(
                        (x.weaknesses for x in run.assessments if x.alternative_id == a.id), []
                    ),
                    "excluded": next(
                        (x.excluded for x in run.assessments if x.alternative_id == a.id), False
                    ),
                    "excluded_because": next(
                        (x.excluded_because for x in run.assessments if x.alternative_id == a.id), ""
                    ),
                    "still_unknown": next(
                        (x.missing for x in run.assessments if x.alternative_id == a.id), []
                    ),
                }
                for a in run.alternatives
            ],
            "trade_offs": [
                {"about": t.about, "detail": t.detail, "decided_by": t.decided_by}
                for t in run.trade_offs
            ],
            "what_i_know_about_them": run.personal_context_used,
            "produce": {
                "verdict": "clear_choice | conditional | no_clear_winner | insufficient",
                "confidence": "strong | tentative | weak",
                "chosen_alternative_id": "only for clear_choice",
                "message": (
                    "what you would say to them, in Italian, plainly. Name the "
                    "trade-off if there is one. Never present a preference as a "
                    "certainty, and never give a number you were not given."
                ),
                "deciding_factors": ["the few things that actually decided it"],
                "conditional": [
                    {
                        "condition": "if what matters most to you is …",
                        "alternative_id": "id",
                        "because": "why that one, under that condition",
                    }
                ],
                "unresolved": ["what stayed open"],
                "needed_to_decide": [
                    "for insufficient: what would settle it, as short as possible"
                ],
            },
            "note": (
                "insufficient is a real answer and often the right one. So is "
                "no_clear_winner. Do not pick something to avoid saying either."
            ),
        },
        ensure_ascii=False,
    )
    data = await _ask_model(_DISCIPLINE, user)
    if not data:
        return None
    try:
        recommendation = Recommendation.model_validate(_fit(data, Recommendation))
    except Exception as e:
        logger.info("recommendation rejected: %s", type(e).__name__)
        return None

    # A choice has to be one of the things on the table, and cannot be one that
    # was ruled out.
    known = {a.id for a in run.alternatives}
    excluded = {a.alternative_id for a in run.assessments if a.excluded}
    if recommendation.chosen_alternative_id not in known:
        recommendation.chosen_alternative_id = None
    if recommendation.chosen_alternative_id in excluded:
        logger.info("recommended an excluded alternative; dropped")
        recommendation.chosen_alternative_id = None
    if recommendation.verdict == "clear_choice" and not recommendation.chosen_alternative_id:
        recommendation.verdict = "no_clear_winner"
    recommendation.conditional = [
        choice for choice in recommendation.conditional if choice.alternative_id in known
    ]
    return recommendation


async def explain_change(
    *, previous: ComparisonRun, current: ComparisonRun
) -> Optional[str]:
    """
    Why the answer is different from last time.

    Not a sentence assembled from a template: the model is shown both and says
    what moved. A recommendation that changes without being able to say why is
    one nobody should trust.
    """
    user = json.dumps(
        {
            "the_decision": current.need.decision,
            "what_i_said_before": {
                "verdict": previous.recommendation.verdict if previous.recommendation else None,
                "chose": (
                    (previous.alternative(previous.recommendation.chosen_alternative_id) or Alternative(name="?")).name
                    if previous.recommendation and previous.recommendation.chosen_alternative_id
                    else None
                ),
                "because": previous.recommendation.deciding_factors if previous.recommendation else [],
                "when": previous.started_at,
            },
            "what_i_say_now": {
                "verdict": current.recommendation.verdict if current.recommendation else None,
                "chose": (
                    (current.alternative(current.recommendation.chosen_alternative_id) or Alternative(name="?")).name
                    if current.recommendation and current.recommendation.chosen_alternative_id
                    else None
                ),
                "because": current.recommendation.deciding_factors if current.recommendation else [],
            },
            "produce": {
                "what_changed": (
                    "one or two sentences in Italian saying what is different "
                    "and why it changed the answer. If nothing material changed, "
                    "say that."
                )
            },
        },
        ensure_ascii=False,
    )
    data = await _ask_model(_DISCIPLINE, user)
    if not data:
        return None
    text = data.get("what_changed")
    return str(text)[:400] if isinstance(text, str) and text.strip() else None
