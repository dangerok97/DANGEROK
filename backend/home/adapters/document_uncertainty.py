"""
The one thing ORA could not work out, when it actually needs it.

Reading a document is ORA's job, not the person's. Most of the time it goes
well and there is nothing to say. Sometimes a field really is unreadable — two
plausible dates on a scan, a number the OCR mangled — and then the honest thing
is one short question about that field, rather than handing the whole document
back with a "Verifica" button and letting somebody work out what was wanted.

So: a question exists only when there is a specific thing ORA could not
resolve. No uncertainty, no question. Uncertainty about something nothing
depends on stays where it is, in the record, until it matters.

The questions here are about *fields* — a date, a missing piece, a document
that would not open. Nothing in this module knows what kind of document it is
looking at.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# How low a reading has to be before ORA should admit it did not understand.
# Matched to the analyzer's own bar for `requires_review`.
_UNREADABLE_BELOW = 0.5


def _events(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [e for e in (doc.get("event_candidates") or []) if isinstance(e, dict)]


def _ambiguous_date_question(event: Dict[str, Any]) -> str:
    """Name the alternatives when the extraction kept them, ask plainly when it did not."""
    options = [str(c) for c in (event.get("date_candidates") or []) if c]
    if len(options) >= 2:
        return (
            f"Non riesco a capire se la data è {options[0]} o {options[1]}. "
            "Qual è quella corretta?"
        )
    return "Non riesco a leggere con certezza la data. Qual è quella giusta?"


def blocking_uncertainty(doc: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    The single field worth asking about, or None.

    None is the ordinary answer. It is the answer for every document ORA read
    properly, however much it learned from it.
    """
    analysis = doc.get("analysis") or {}
    status = doc.get("pipeline_status") or ""

    if status == "failed":
        return {
            "field": "document",
            "question": "Non sono riuscita a leggere questo documento. Vuoi caricarlo di nuovo?",
        }

    # The analyzer's own statement that it could not resolve something, in
    # either of the two places it makes it: the flag it sets while analysing,
    # and the terminal state it lands on when there was nothing to propose.
    # Both mean the same thing, and neither is implied by having finished
    # reading a document successfully.
    if not (analysis.get("requires_review") or status == "needs_review"):
        return None

    for event in _events(doc):
        if event.get("ambiguous_date"):
            return {"field": "date", "question": _ambiguous_date_question(event)}

    for event in _events(doc):
        missing = [str(m) for m in (event.get("missing_fields") or []) if m]
        if missing:
            if any("date" in m or "datetime" in m for m in missing):
                return {
                    "field": "date",
                    "question": "Mi manca la data di questo documento. Me la dici?",
                }
            return {
                "field": missing[0],
                "question": "Mi manca un dato di questo documento. Puoi completarlo?",
            }

    confidence = analysis.get("confidence")
    if isinstance(confidence, (int, float)) and confidence < _UNREADABLE_BELOW:
        return {
            "field": "document",
            "question": "Non ho capito bene questo documento. Di cosa si tratta?",
        }

    # Marked for review with nothing specific behind it. ORA keeps that to
    # itself: an unexplained "controlla" is not a question.
    return None
