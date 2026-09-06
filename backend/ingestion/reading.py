"""
Reading a normalized payload back, once, in the place that wrote it.

    A FIELD THAT TRAVELS WITH ITS PROVENANCE HAS TO BE UNWRAPPED SOMEWHERE.
    IF THAT SOMEWHERE IS "EVERY READER", IT IS NOWHERE.

Ingestion stores each field as a `NormalizedField` — its value together with
where that value came from and how sensitive it is — so a real calendar row
holds `{"title": {"value": "Dentista", "provenance": {...}}}` and not
`{"title": "Dentista"}`. That envelope is the right design: a fact without
its provenance is a fact nobody can check later.

It has one failure mode, and this module exists because it happened three
times. A reader that forgets the envelope does not crash and does not warn:
`payload.get("starts_at")` returns a dict, which is truthy, so the guard
above it passes; the parse below it throws; the `except` skips the row. The
result is a screen that says "nessun impegno" over a calendar full of
appointments, and nothing anywhere says why.

So the module that puts the envelope on offers the way to take it off, and
every reader uses this. What is *not* offered is a way to read a single field
by name — that is how the envelope gets forgotten one field at a time.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def plain(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    The payload with every field's envelope taken off, values only.

    Accepts both shapes on purpose. The pipeline writes the enveloped one;
    tests, fixtures and older rows sometimes hold flat values, and unwrapping
    a flat value is the identity — so a caller never has to know which kind
    of row it is holding, which is the whole point.

    What it never does is guess: a dict without a `value` key is a value in
    its own right (an `extendedProperties` bag, a reminders block) and is
    passed through untouched.
    """
    out: Dict[str, Any] = {}
    for field, value in (payload or {}).items():
        if isinstance(value, dict) and "value" in value:
            out[field] = value.get("value")
        elif isinstance(value, list):
            out[field] = [
                item.get("value") if isinstance(item, dict) and "value" in item else item
                for item in value
            ]
        else:
            out[field] = value
    return out


def where(field: str) -> str:
    """
    How to name a normalized field inside a Mongo query.

    `where("starts_at")` → `"normalized_payload.starts_at.value"`.

    Here because the same forgetting happens in queries, and there it is even
    quieter: a filter on `normalized_payload.starts_at` matches no enveloped
    row at all, so the collection looks empty rather than wrong.
    """
    return f"normalized_payload.{field}.value"
