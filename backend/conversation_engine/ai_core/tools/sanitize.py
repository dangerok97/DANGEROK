"""External query minimization — never dump Profile/Memory into search."""
from __future__ import annotations

import re
from typing import Optional, Tuple

_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b", re.I)
_PHONE = re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b", re.I)
_CF = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", re.I)

# Patterns that suggest dumping a personal dossier into web search
_OVERSHARE = re.compile(
    r"(codice fiscale|password|secret|girlfriend|fidanzat|"
    r"lives in|abita a|user_id|profile dump|my full name is|"
    r"mi chiamo .{3,40} e (abito|lavoro|vivo))",
    re.I,
)

MAX_QUERY_LEN = 180


def sanitize_external_query(query: str) -> Tuple[Optional[str], str]:
    """
    Return (clean_query, reason).
    reason=ok when accepted; otherwise failure reason code fragment.
    """
    q = " ".join((query or "").split()).strip()
    if not q:
        return None, "empty_query"
    if len(q) > 400:
        return None, "query_too_long"
    # Strip sensitive tokens
    q = _EMAIL.sub(" ", q)
    q = _PHONE.sub(" ", q)
    q = _IBAN.sub(" ", q)
    q = _CF.sub(" ", q)
    q = " ".join(q.split()).strip()
    if len(q) < 2:
        return None, "empty_after_sanitize"
    if _OVERSHARE.search(q) and len(q) > 80:
        # Over-personal narrative — reject rather than leak
        return None, "overpersonal_query"
    if len(q) > MAX_QUERY_LEN:
        q = q[:MAX_QUERY_LEN].rsplit(" ", 1)[0] or q[:MAX_QUERY_LEN]
    return q, "ok"
