"""Grounded arithmetic for explicit comparable monetary totals only.

No inference about cancellation, provider fees, terms or execution. The
augmented draft is still subjected to the existing source-and-claim audit.
"""
from decimal import Decimal, InvalidOperation
import re

_AMOUNT = re.compile(r"(?<![\w\d])(?P<value>\d{1,6}(?:,\d{1,2})?)\s*(?:€(?!\w)|euro\b)", re.I)
_PERIOD = re.compile(r"\b(?P<count>\d{1,2}|dodici)\s+(?P<unit>mesi|mese|anni|anno)\b", re.I)
_PER_MONTH = re.compile(r"\b(?:al|per)\s+mese\b|\bmensil\w*\b", re.I)
_COMPARE = re.compile(r"\b(?:confront\w*|compar\w*|differenz\w*)\b", re.I)


def _money(text):
    for found in _AMOUNT.finditer(text):
        try:
            yield found, Decimal(found.group("value").replace(",", "."))
        except InvalidOperation:
            continue


def _explicit_totals(source):
    groups = {}
    for clause in re.split(r"[;.\n]+", source):
        periods = list(_PERIOD.finditer(clause))
        if not periods:
            continue
        for match, amount in _money(clause):
            if _PER_MONTH.search(clause[match.end():match.end() + 20]):
                continue
            for period in periods:
                count = ("12" if period.group("count").lower() == "dodici"
                         else str(int(period.group("count"))))
                unit = "mesi" if period.group("unit").lower() in ("mesi", "mese") else "anni"
                groups.setdefault((count, unit), set()).add(amount)
    return groups


def complete_explicit_price_comparison(draft, source, purpose):
    """Complete a missing difference for exactly two source-stated same-period prices.

    Ambiguous source totals or omitted prices cannot justify arithmetic.
    Source attribution is copied only when the saved note explicitly says so.
    """
    if not all(isinstance(x, str) for x in (draft, source, purpose)):
        return draft
    if not draft.strip() or not _COMPARE.search(purpose):
        return draft
    draft_amounts = {amount for _, amount in _money(draft)}
    for (count, unit), totals in _explicit_totals(source).items():
        if len(totals) != 2 or any(x <= 0 for x in totals):
            continue
        smaller, larger = sorted(totals)
        if smaller not in draft_amounts or larger not in draft_amounts:
            continue
        original = draft.strip()
        prefix = ""
        if (re.search(r"\bnota\s+salvata\s+in\s+ORA\b", source, re.I)
                and re.search(r"dati\s+riferiti\s+dall['’]utente", source, re.I)
                and re.search(r"non\s+confermati\s+dal\s+fornitore", source, re.I)
                and not re.search(r"\bnota\b|dati.{0,45}utente", original, re.I)):
            prefix = ("Fonte: nota salvata in ORA; dati riferiti dall'utente "
                      "e non confermati dal fornitore.\n\n")
        result = prefix + original if len(prefix) + len(original) <= 4000 else original
        difference = larger - smaller
        if difference in draft_amounts:
            return result
        formatted = format(difference.normalize(), "f").replace(".", ",")
        addition = (f"\n\nDifferenza aritmetica dei due costi indicati per "
                    f"{count} {unit}: {formatted} euro. "
                    "Il calcolo non dimostra condizioni contrattuali non specificate dalla fonte.")
        return result + addition if len(result) + len(addition) <= 4000 else result
    return draft
