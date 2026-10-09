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
    """Reject unsupported amounts and prefer an exact, unique source datetime.

    An email may have a dated body and a subject saying "in two days".
    When cognition already identified a due commitment, the exact source
    timestamp and its IANA timezone outrank a rounded, model-inferred day.
    """
    excerpt = str(observation.get("private_source_excerpt") or "").strip()
    if not excerpt:
        return answer
    corrected = dict(answer)
    if answer.get("amount") is not None and not amount_supported(
        answer.get("amount"), excerpt
    ):
        corrected["amount"] = None
        missing = [str(v) for v in (answer.get("what_is_not_known") or [])]
        if not any("importo" in v.lower() for v in missing):
            missing.append("l'importo non è confermato dal messaggio originale")
        corrected["what_is_not_known"] = missing[:8]

    # Do not create a due date if the AI never found an obligation/date.
    if answer.get("what_it_is") == "commitment" and answer.get("due_at"):
        exact = exact_source_datetime(excerpt)
        if exact is not None:
            corrected["due_at"] = exact
    return corrected


def exact_source_datetime(excerpt: str) -> str | None:
    """Extract one explicit local timestamp with an IANA timezone.

    Multiple timestamps, malformed/unknown zones, DST gaps and ambiguous
    fall-back hours cannot safely be picked as a due date; return None.
    Semantic classification remains with cognition.
    """
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    candidates = re.findall(
        r"(?<!\d)(\d{4}-\d{2}-\d{2})[ T]"
        r"(\d{2}:\d{2}:\d{2})\s+"
        r"([A-Za-z][A-Za-z_]+/[A-Za-z_]+(?:/[A-Za-z_]+)?)",
        excerpt or "",
    )
    if len(set(candidates)) != 1:
        return None
    date_part, time_part, zone_name = candidates[0]
    try:
        zone = ZoneInfo(zone_name)
        local = datetime.fromisoformat(
            f"{date_part}T{time_part}"
        ).replace(tzinfo=zone)
        # Nonexistent hour on spring-forward or ambiguous fall-back.
        if local.astimezone(timezone.utc).astimezone(zone).replace(
            tzinfo=None
        ) != local.replace(tzinfo=None):
            return None
        if local.replace(fold=1).utcoffset() != local.utcoffset():
            return None
        return local.isoformat()
    except (ValueError, ZoneInfoNotFoundError, OverflowError):
        return None
