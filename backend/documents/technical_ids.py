"""Technical identifiers detector — Iterazione 22.

Extracts a **separate** category ("Identificativi tecnici") for tokens
that are clearly system-generated codes and should never contaminate
`phones` / `tax_ids` / `numbers`. This keeps the user-facing UI clean
while preserving everything for the "Insights" tab.

Deterministic. Runs AFTER label-aware buckets have claimed their spans.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

# UUID (v1..v5 canonical)
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
# Hexadecimal hashes (>= 16 hex chars, standalone token)
_HASH_RE = re.compile(r"(?<![A-Za-z0-9])[0-9a-fA-F]{16,64}(?![A-Za-z0-9])")

# Label-anchored technical identifiers: TktID, ET (event token), barcode,
# batch id, transaction id, session id, correlation id, ecc.
_TECH_LABEL_ALT = (
    r"tkt(?:\s*id)?|barcode|ean|qr(?:\s*code)?|"
    r"batch(?:\s*id)?|txn(?:\s*id)?|transaction\s*id|"
    r"session\s*id|correlation\s*id|trace\s*id|request\s*id|"
    r"tracking(?:\s*(?:id|code|number|n[.°]?))?|"
    r"et(?:\s*(?:id|code))?|serial(?:\s*(?:no|number|n[.°]?))?|"
    r"progressivo|matricola|imei"
)
_TECH_LABELED_RE = re.compile(
    r"(?i)\b(?:" + _TECH_LABEL_ALT + r")[\s:#\-.]{0,10}"
    r"([A-Z0-9][A-Z0-9\-_/]{2,60})\b"
)

# Long numeric progressive (>= 12 digits) not otherwise labelled — treated
# as technical ID rather than a phone or generic number. This is safe
# because we only invoke this AFTER phones / order_ids / tax_ids have
# claimed their spans.
_LONG_NUMERIC_ID_RE = re.compile(r"(?<![\w.,])\d{12,}(?![\w.,])")


def _spans_overlap(a: Tuple[int, int], claimed: List[Tuple[int, int]]) -> bool:
    s, e = a
    for cs, ce in claimed:
        if not (e <= cs or s >= ce):
            return True
    return False


def extract_technical_identifiers(
    text: str,
    claimed_spans: List[Tuple[int, int]],
) -> Dict[str, List[str]]:
    """Returns dict grouping technical IDs by sub-kind.

    Also **mutates** ``claimed_spans`` in place so that the caller's
    generic-number fallback skips these tokens.
    """
    if not text:
        return {}

    out: Dict[str, List[str]] = {"uuids": [], "hashes": [], "labelled": [], "long_numeric": []}
    seen: set[str] = set()

    def _push(bucket: str, val: str, span: Tuple[int, int]) -> None:
        key = val.lower()
        if key in seen:
            return
        seen.add(key)
        out[bucket].append(val)
        claimed_spans.append(span)

    for m in _UUID_RE.finditer(text):
        s, e = m.span(0)
        if _spans_overlap((s, e), claimed_spans):
            continue
        _push("uuids", m.group(0), (s, e))

    for m in _HASH_RE.finditer(text):
        s, e = m.span(0)
        if _spans_overlap((s, e), claimed_spans):
            continue
        val = m.group(0)
        # Skip pure decimal strings; those go to numbers / long_numeric.
        if val.isdigit():
            continue
        _push("hashes", val, (s, e))

    for m in _TECH_LABELED_RE.finditer(text):
        try:
            gs, ge = m.span(1)
        except IndexError:
            continue
        ms, me = m.span(0)
        if _spans_overlap((ms, me), claimed_spans):
            continue
        val = (m.group(1) or "").strip()
        if not val or not any(ch.isdigit() for ch in val):
            continue
        _push("labelled", val, (ms, me))

    for m in _LONG_NUMERIC_ID_RE.finditer(text):
        s, e = m.span(0)
        if _spans_overlap((s, e), claimed_spans):
            continue
        _push("long_numeric", m.group(0), (s, e))

    # Drop empty buckets for a lean payload
    return {k: v for k, v in out.items() if v}


def flatten(tech: Dict[str, List[str]]) -> List[str]:
    """Return a single de-duped list for UI display."""
    out: list[str] = []
    seen: set[str] = set()
    for bucket in ("labelled", "uuids", "hashes", "long_numeric"):
        for v in tech.get(bucket, []):
            k = v.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(v)
    return out
