"""
The model chooses the calculation. Python does it.

A model asked to compare a monthly figure with an annual one will usually see
that one has to be converted, and will sometimes get the multiplication wrong —
and a wrong number inside a confident sentence is worse than no number. So the
division of labour is: it says which operation over which operands and why, and
the arithmetic happens here.

There are six operations and none of them knows a subject. `percent_change` is
the same function whether it is applied to a rate, a rent or a course fee, and
nothing in this file could tell which it was. A formula that belonged to one
kind of decision would be a formula the code had opinions about, which is the
thing this phase must not contain.

Operands are attribute names on the alternative being computed, or literal
numbers. Anything that cannot be resolved to a number leaves the computation
unresolved and says so: a missing input is not zero.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from comparison.models import Alternative, Computation

logger = logging.getLogger("ora.comparison.arithmetic")


def _resolve(token: str, alternative: Alternative) -> tuple[Optional[float], Dict[str, Any]]:
    """
    An operand's value: an attribute of this alternative by id, or a literal.

    By id only. A reference that does not resolve is not searched for by any
    other means — the alternative is that the code guesses which field was
    meant, and a figure produced from the wrong field is worse than no figure.
    """
    ref = (token or "").strip()
    if not ref:
        return None, {"ref": ref, "resolved": False, "why": "riferimento vuoto"}

    attribute = alternative.attribute(ref)
    if attribute is not None:
        if attribute.number is None:
            return None, {
                "ref": ref, "resolved": False,
                "why": f"«{attribute.name}» non è un valore numerico",
            }
        return float(attribute.number), {
            "ref": ref,
            "resolved": True,
            "label": attribute.name,
            "value": attribute.number,
            "unit": attribute.unit,
            "source_ids": list(attribute.source_ids),
            "stated_by_user": attribute.stated_by_user,
        }

    # A literal the model wrote into the operands, like a number of months.
    try:
        literal = float(ref.replace(",", "."))
    except (TypeError, ValueError):
        return None, {
            "ref": ref, "resolved": False,
            "why": "non è un id di attributo né un numero",
        }
    return literal, {"ref": ref, "resolved": True, "literal": literal}


def _apply(operation: str, values: List[float]) -> Optional[float]:
    if not values:
        return None
    if operation == "sum":
        return sum(values)
    if operation == "product":
        total = 1.0
        for value in values:
            total *= value
        return total
    if len(values) < 2:
        return None
    first, second = values[0], values[1]
    if operation == "difference":
        return first - second
    if operation == "quotient":
        return None if second == 0 else first / second
    if operation == "percent_of":
        return None if second == 0 else (first / second) * 100.0
    if operation == "percent_change":
        return None if first == 0 else ((second - first) / abs(first)) * 100.0
    return None


def compute(computation: Computation, alternative: Alternative) -> Computation:
    """Work out one figure for one alternative, or say why it could not be."""
    computation.alternative_id = alternative.id
    computation.inputs = []
    resolved: List[float] = []
    for token in computation.operands:
        value, trace = _resolve(token, alternative)
        computation.inputs.append(trace)
        if value is None:
            computation.result = None
            computation.failed_reason = trace.get("why") or f"«{token}» non risolve"
            return computation
        resolved.append(value)

    result = _apply(computation.operation, resolved)
    if result is None:
        computation.result = None
        computation.failed_reason = "il calcolo non è applicabile a questi valori"
        return computation

    computation.result = round(result, 4)
    computation.failed_reason = ""
    return computation


def compute_all(
    computations: List[Computation], alternatives: List[Alternative]
) -> List[Computation]:
    """
    Every named figure, for every alternative it can be worked out for.

    An operand id belongs to a field, and alternatives describing the same
    field share it, so one declared computation runs against each of them. The
    result is written onto a copy per alternative, so a recommendation can
    point at the number it used and at whose it was.
    """
    out: List[Computation] = []
    for alternative in alternatives:
        for template in computations:
            attempt = template.model_copy(deep=True)
            attempt.name = f"{template.name} · {alternative.name}"
            out.append(compute(attempt, alternative))
    return out
