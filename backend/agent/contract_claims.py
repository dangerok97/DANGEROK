"""Conservative one-way guard for unsupported consumer-contract exit rights.

This does not interpret prices, infer a contract, or approve a statement.
It only catches certain *affirmative* claims about fee-free termination or
refund availability when the saved source never expressly grants that right
to the same named billing option. Failure is not permission to rewrite text.
Unknown/conditional terms should be stated as unknown instead.

No model call, hidden user data, new database schema, or external effect.
"""
from __future__ import annotations

import re
from typing import Any


_SCOPES = re.compile(r"\b(?:mensil\w*|annua\w*|monthly|annual)\b", re.I)
_MONTHLY = ("mensil", "monthly")
_EPISTEMIC = re.compile(
    r"\b(?:non\s+(?:è\s+)?(?:noto|chiaro|confermat\w*|accertat\w*|sappiamo)|"
    r"da\s+verificare\s+se|non\s+si\s+sa\s+se|"
    r"non\s+è\s+detto\s+che)\b", re.I,
)
_NO_PENALTY = re.compile(
    r"\b(?:senza\s+(?:(?:alcun\w*|nessun\w*)\s+)?"
    r"(?:penal\w*|vincol\w*|oner\w*|(?:costi?|spese)\s+di\s+(?:disdetta|recesso)|perdite)"
    r"|nessun\w*\s+(?:penal\w*|vincol\w*|oner\w*|"
    r"(?:costi?|spese)\s+di\s+(?:disdetta|recesso))"
    r"|(?:penal\w*|vincol\w*)\s+(?:assent\w*|non\s+previst\w*|non\s+applicat\w*)|non\s+(?:prevede|applica)\s+(?:alcun\w*\s+)?penal\w*)\b",
    re.I,
)
_REFUND_ALLOWED = re.compile(
    r"\brimbors\w*.{0,46}\b(?:non\s+(?:è\s+)?vietat\w*|"
    r"(?:è\s+)?possibil\w*|consentit\w*|disponibil\w*)\b",
    re.I | re.S,
)
_FREE_EXIT = re.compile(
    r"\b(?:disdire|interrompere|interruzione|disdetta)\b.{0,65}"
    r"\b(?:liberamente|in\s+qualsiasi\s+momento)\b",
    re.I | re.S,
)


def _scope(text: str, at: int) -> str | None:
    latest = None
    for match in _SCOPES.finditer(text, 0, at):
        latest = match
    if latest is None or at - latest.end() > 480:
        return None
    return "monthly" if latest.group(0).lower().startswith(_MONTHLY) else "annual"


def _assertions(text: str):
    for name, pattern in (("no_penalty", _NO_PENALTY),
                          ("refund_possible", _REFUND_ALLOWED),
                          ("free_exit", _FREE_EXIT)):
        for match in pattern.finditer(text):
            # "I don't know whether it is penalty-free" is not a warranty.
            # A disclaimer *after* an asserted guarantee is not this case.
            leading = text[max(0, match.start() - 90):match.start()]
            if _EPISTEMIC.search(leading):
                continue
            scope = _scope(text, match.start())
            if scope:
                yield scope, name


def unsupported_contract_exit_claims(text: str, rows: list[dict[str, Any]]) -> list[str]:
    """Return only bounded risk codes; never return or persist source text.

    This is an additional refusal condition for *source-grounded* internal
    drafts, not a general semantic entailment checker. It is deliberately
    conservative: absence of an explicit clause cannot establish a right.
    """
    if not isinstance(text, str) or not text or not isinstance(rows, list):
        return []
    # The source class comes from code-owned evidence, not the model review.
    source = "\n".join(row["claim"] for row in rows
                       if isinstance(row, dict)
                       and row.get("source_class") in (
                           "internal_observation", "connected_provider", "external_research")
                       and isinstance(row.get("claim"), str))
    if not source:
        return []
    source_claims = set(_assertions(source))
    hazards = []
    for scope, kind in _assertions(text):
        # Explicit monthly wording cannot borrow an annual condition.
        if ((scope, kind) not in source_claims
                and not (kind == "free_exit" and (scope, "no_penalty") in source_claims)):
            code = f"{scope}_{kind}_not_in_source"
            if code not in hazards:
                hazards.append(code)
    return hazards[:6]
