"""Narrow, evidence-bound comparison of the seller component of energy costs.

Only explicitly labelled fixed tariffs are comparable. A bill total includes
taxes, network charges and adjustments; it is never used as a tariff input.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


_NUMBER = r"(\d{1,3}(?:[.,]\d{1,4})?)"
_BILL_UNIT_LABEL = r"(?:prezzo\s+materia\s+(?:energia|gas)|corrispettivo\s+(?:energia|gas))"
_OFFER_UNIT_LABEL = r"(?:prezzo\s+(?:fisso|energia|gas)|corrispettivo\s+(?:energia|gas))"
_BILL_FIXED_LABEL = r"(?:quota\s+fissa\s+(?:di\s+)?commercializzazione|(?:costi|quota)\s+di\s+commercializzazione)"
_OFFER_FIXED_LABEL = r"(?:quota\s+fissa(?:\s+(?:di\s+)?commercializzazione)?|(?:costi|quota)\s+di\s+commercializzazione|commercializzazione)"
_VARIABLE = re.compile(r"\b(?:indicizzat\w*|variabil\w*|PUN|PSV)\b", re.I)


def _decimal(raw: str) -> Decimal | None:
    try:
        value = Decimal(raw.replace(",", "."))
        return value if value >= 0 else None
    except InvalidOperation:
        return None


def _terms(text: str, commodity: str, *, seller_page: bool = False) -> dict[str, float] | None:
    if commodity not in ("electricity", "gas") or not text:
        return None
    if seller_page and _VARIABLE.search(text):
        return None
    unit = "kwh" if commodity == "electricity" else "smc"
    unit_label = _OFFER_UNIT_LABEL if seller_page else _BILL_UNIT_LABEL
    fixed_label = _OFFER_FIXED_LABEL if seller_page else _BILL_FIXED_LABEL
    unit_pattern = re.compile(
        rf"{unit_label}[^\n]{{0,70}}?{_NUMBER}\s*(?:€\s*/\s*{unit}|euro\s*/\s*{unit})\b",
        re.I,
    )
    fixed_pattern = re.compile(
        rf"{fixed_label}[^\n]{{0,65}}?{_NUMBER}\s*(?:€|euro)\s*(?:/\s*(mese|anno)|al\s+(mese|anno))\b",
        re.I,
    )
    fixed_after_pattern = re.compile(
        rf"{_NUMBER}\s*(?:€|euro)\s*(?:/\s*(mese|anno)|al\s+(mese|anno))"
        rf"\s*\([^\n)]{{0,50}}{fixed_label}[^\n)]{{0,20}}\)",
        re.I,
    )
    unit_hits = list(unit_pattern.finditer(text))
    fixed_hits = list(fixed_pattern.finditer(text)) + list(fixed_after_pattern.finditer(text))
    if len(unit_hits) != 1 or len(fixed_hits) != 1:
        return None
    unit_hit, fixed_hit = unit_hits[0], fixed_hits[0]
    rate = _decimal(unit_hit.group(1))
    fixed = _decimal(fixed_hit.group(1))
    if rate is None or fixed is None:
        return None
    if rate > (Decimal("2") if commodity == "electricity" else Decimal("5")):
        return None
    annual_fixed = fixed * (12 if (fixed_hit.group(2) or fixed_hit.group(3)).lower() == "mese" else 1)
    if annual_fixed > 2000:
        return None
    return {"unit_price": float(rate), "fixed_year": float(annual_fixed)}


def bill_terms(text: str, commodity: str) -> dict[str, float] | None:
    return _terms(text, commodity)


def offer_terms(snippet: str, commodity: str) -> dict[str, float] | None:
    return _terms(snippet, commodity, seller_page=True)


def seller_year(annual_consumption: float, terms: dict[str, Any]) -> float:
    value = (
        Decimal(str(annual_consumption)) * Decimal(str(terms["unit_price"]))
        + Decimal(str(terms["fixed_year"]))
    )
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
