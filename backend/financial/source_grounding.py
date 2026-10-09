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


def explicit_named_zone_due_at(observation: dict) -> str | None:
    """Preserve one complete datetime with an explicit IANA timezone.

    A message can say "in two days" in the subject but give a full provider
    timestamp in its content. Only a *single* explicit timestamp is eligible,
    and this function never decides whether it is a renewal or a payment.
    The financial judgement must first identify an actual due obligation.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    excerpt = str((observation or {}).get("private_source_excerpt") or "")
    matches = set(re.findall(
        r"(?<!\d)(\d{4}-\d{2}-\d{2})[ T]"
        r"(\d{2}:\d{2}:\d{2})\s+"
        r"([A-Za-z_]+/[A-Za-z_]+(?:/[A-Za-z_]+)?)",
        excerpt,
    ))
    if len(matches) != 1:
        return None
    date, clock, zone = next(iter(matches))
    try:
        z = ZoneInfo(zone)
        parsed = datetime.fromisoformat(f"{date}T{clock}").replace(tzinfo=z)
        # Invalid local wall-clock times in DST jumps are not safe deadlines.
        back = parsed.astimezone(ZoneInfo("UTC")).astimezone(z)
        if back.replace(tzinfo=None) != parsed.replace(tzinfo=None):
            return None
        return parsed.isoformat()
    except (ValueError, ZoneInfoNotFoundError):
        return None
