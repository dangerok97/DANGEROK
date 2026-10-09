"""Check monetary claims against the transient source, never its subject alone.

A date, a card number, a GB allowance or a percentage is not a charge.
Only currency-marked amounts count as an explicit amount in a mail excerpt.
This is a guard on AI output, not a keyword classifier of what an email means.
"""
from __future__ import annotations

import math
import re

_AMOUNT = r"\d+(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?"
_WITH_CURRENCY = re.compile(
    rf"(?i)(?:(?:€|\bEUR\b|\beuro\b)\s*(?P<after>{_AMOUNT})|"
    rf"(?P<before>{_AMOUNT})\s*(?:€|\bEUR\b|\beuro\b))"
)


def source_amounts(excerpt: str) -> list[float]:
    amounts: list[float] = []
    for match in _WITH_CURRENCY.finditer(excerpt or ""):
        token = (match.group("after") or match.group("before") or "").replace(" ", "")
        # 1.234,56 or 1,234.56 => 1234.56; 0,99 => 0.99.
        if "," in token and "." in token:
            decimal = "," if token.rfind(",") > token.rfind(".") else "."
            thousands = "." if decimal == "," else ","
            token = token.replace(thousands, "").replace(decimal, ".")
        elif "," in token:
            token = token.replace(",", ".")
        elif token.count(".") > 1:
            token = token.replace(".", "")
        try:
            amounts.append(float(token))
        except ValueError:
            continue
    return amounts


def amount_supported(value: object, excerpt: str) -> bool:
    try:
        target = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(target) and any(
        math.isclose(target, candidate, rel_tol=0.0, abs_tol=0.005)
        for candidate in source_amounts(excerpt)
    )


def check_financial_extraction(answer: dict, observation: dict) -> dict:
    """Reject unsupported amount without discarding the grounded obligation."""
    excerpt = str(observation.get("private_source_excerpt") or "").strip()
    if not excerpt or answer.get("amount") is None:
        return answer
    if amount_supported(answer.get("amount"), excerpt):
        return answer
    corrected = dict(answer)
    corrected["amount"] = None
    missing = [str(v) for v in (answer.get("what_is_not_known") or [])]
    if not any("importo" in v.lower() for v in missing):
        missing.append("l'importo non è confermato dal messaggio originale")
    corrected["what_is_not_known"] = missing[:8]
    return corrected
