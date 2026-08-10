"""Presentation language by confidence band — deterministic safe fallback.

KNOWN → assertive · LIKELY → soft · AMBIGUOUS → uncertain (actionable).
No large phrase taxonomy; no domain-specific wording.
"""
from __future__ import annotations

import re
from typing import Tuple


def assertive_core(statement: str) -> str:
    s = " ".join((statement or "").split()).strip()
    s = re.sub(
        r"(?i)^mi (risulta|sembra) che\s+",
        "",
        s,
    )
    s = re.sub(r"(?i),\s*ma non ne sono ancora sicur[ao]\.?$", "", s)
    s = re.sub(r"(?i)^forse\s+", "", s)
    s = s.strip()
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    if s and not s.endswith((".", "!", "?")):
        s += "."
    return s


def present_statement(statement: str, status: str) -> Tuple[str, str]:
    """Return (presentation, belief_core)."""
    core = assertive_core(statement)
    if status == "known":
        return core, core
    if status == "likely":
        body = core.rstrip(".")
        soft = f"Mi sembra che {body[0].lower() + body[1:]}."
        return soft, core
    if status == "ambiguous":
        body = core.rstrip(".")
        soft = (
            f"Mi risulta che {body[0].lower() + body[1:]}, "
            "ma non ne sono ancora sicura."
        )
        return soft, core
    return core, core
