"""
The model says what is absolute. The code says who breaches it.

Deciding that something is a hard requirement rather than a preference is a
judgement about somebody's life, and it belongs to the reasoning. Checking a
stated number against a stated limit is arithmetic, and it belongs here —
because a model reading "1.180 is under the 1.100 ceiling" is a mistake nobody
would catch, and it would arrive inside a sentence that sounded certain.

So the constraint arrives already structured: an attribute, a relation, a
value. This evaluates it and says one of three things — satisfied, breached, or
not checkable. The third is not the second: an alternative whose figure is
missing has not failed anything, and excluding it would be inventing a fact
about it.

Nothing here knows what any of the attributes mean.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from comparison.models import Alternative, Constraint, ConstraintCheck

logger = logging.getLogger("ora.comparison.constraints")


def _compare_numbers(operator: str, observed: float, limit: float) -> Optional[bool]:
    if operator == "<=":
        return observed <= limit
    if operator == "<":
        return observed < limit
    if operator == ">=":
        return observed >= limit
    if operator == ">":
        return observed > limit
    if operator == "==":
        return observed == limit
    if operator == "!=":
        return observed != limit
    return None


def _compare_text(operator: str, observed: str, expected: str) -> Optional[bool]:
    left = (observed or "").strip().lower()
    right = (expected or "").strip().lower()
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    if operator == "in":
        return left in right
    if operator == "not_in":
        return left not in right
    return None


def check(constraint: Constraint, alternative: Alternative) -> ConstraintCheck:
    """One condition, one alternative."""
    result = ConstraintCheck(
        alternative_id=alternative.id,
        constraint_name=constraint.name,
        attribute_id=constraint.attribute_id,
    )
    # By id, and only by id: a requirement that quietly stops being checked
    # because a label was reworded is worse than one nobody stated.
    attribute = alternative.attribute(constraint.attribute_id)
    if attribute is None:
        result.reason = "il dato richiesto non è noto per questa alternativa"
        return result
    result.source_ids = list(attribute.source_ids)
    result.stated_by_user = attribute.stated_by_user

    if constraint.number is not None:
        if attribute.number is None:
            # A limit expressed as a number cannot be checked against a phrase.
            result.reason = f"«{attribute.name}» non è un valore numerico"
            result.observed = attribute.value[:200]
            return result
        # Units are the code's business too: comparing a monthly figure with an
        # annual ceiling is a wrong answer that looks like a right one.
        if (constraint.unit or "").strip() and (attribute.unit or "").strip():
            if constraint.unit.strip().lower() != attribute.unit.strip().lower():
                result.reason = (
                    f"unità diverse: «{attribute.unit}» contro «{constraint.unit}»"
                )
                result.observed = f"{attribute.number} {attribute.unit}"
                return result
        satisfied = _compare_numbers(constraint.operator, attribute.number, constraint.number)
        result.observed = f"{attribute.number}{(' ' + attribute.unit) if attribute.unit else ''}"
    else:
        satisfied = _compare_text(constraint.operator, attribute.value, constraint.value)
        result.observed = attribute.value[:200]

    if satisfied is None:
        result.reason = "la relazione non è applicabile a questi valori"
        return result
    result.satisfied = satisfied
    return result


def check_all(
    constraints: List[Constraint], alternatives: List[Alternative]
) -> List[ConstraintCheck]:
    return [
        check(constraint, alternative)
        for alternative in alternatives
        for constraint in constraints
    ]


def breaches(checks: List[ConstraintCheck], alternative_id: str) -> List[ConstraintCheck]:
    """
    What this alternative definitely fails.

    Definitely: `satisfied is False`. A check that could not be made is left
    out, because "we do not know" is not a reason to rule anything out.
    """
    return [
        item
        for item in checks
        if item.alternative_id == alternative_id and item.satisfied is False
    ]


def unverifiable(checks: List[ConstraintCheck], alternative_id: str) -> List[ConstraintCheck]:
    """What could not be checked at all — worth saying, and not the same thing."""
    return [
        item
        for item in checks
        if item.alternative_id == alternative_id and item.satisfied is None
    ]
