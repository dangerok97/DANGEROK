"""Expand opportunity evidence into the concrete source handles an agent can use.

An opportunity may cite a disagreement row because that is the fact the model
judged relevant. The disagreement itself already points at the two real
sources behind it. Passing only the link id to the agent would preserve
traceability while throwing away actionability.

This module follows recorded links only. It never matches strings, invents
relationships, or reads private content.
"""
from __future__ import annotations

from typing import Any, Iterable, List


_SAFE_SITUATION_LINK_PREFIXES = (
    "place:",
    "situation:",
    "goal:",
    "plan:",
    "object:",
    "document:",
    "calendar:",
    "profile:",
    "file:",
    "presence:",
)


def _safe_situation_link(value: str) -> str:
    ref = str(value or "").strip()[:120]
    if ref.startswith(_SAFE_SITUATION_LINK_PREFIXES):
        return ref
    if ref.startswith("mem_") and 6 <= len(ref) <= 44:
        return ref
    return ""


def _value(item: Any, key: str) -> str:
    if isinstance(item, dict):
        return str(item.get(key) or "").strip()
    return str(getattr(item, key, "") or "").strip()


def _append_unique(out: List[str], value: str) -> None:
    value = str(value or "").strip()[:120]
    if value and value not in out and len(out) < 8:
        out.append(value)


def _calendar_ref(raw: str) -> str:
    raw = str(raw or "").strip()
    if not raw:
        return ""
    return raw if raw.startswith("calendar:") else f"calendar:{raw}"


async def expand_opportunity_source_refs(
    db, owner_id: str, evidence: Iterable[Any]
) -> List[str]:
    """Return cited refs plus concrete handles recorded behind disagreements."""
    rows = list(evidence or [])
    link_ids = [
        _value(item, "ref")
        for item in rows
        if _value(item, "kind") == "disagreement" and _value(item, "ref")
    ]

    situation_ids = [
        _value(item, "ref").split(":", 1)[1]
        for item in rows
        if _value(item, "kind") == "situation"
        and _value(item, "ref").startswith("situation:")
        and ":" in _value(item, "ref")
    ]
    situations = {}
    if situation_ids:
        try:
            docs = await db.situations.find(
                {"user_id": owner_id, "id": {"$in": situation_ids}},
                {"_id": 0, "id": 1, "linked_object_refs": 1},
            ).to_list(len(situation_ids))
            situations = {str(doc.get("id") or ""): doc for doc in docs}
        except Exception:
            situations = {}

    links = {}
    if link_ids:
        try:
            docs = await db.connected_situation_links.find(
                {"owner_id": owner_id, "id": {"$in": link_ids}},
                {
                    "_id": 0,
                    "id": 1,
                    "source_type": 1,
                    "source_object_ref": 1,
                    "target_kind": 1,
                    "target_ref": 1,
                },
            ).to_list(len(link_ids))
            links = {str(doc.get("id") or ""): doc for doc in docs}
        except Exception:
            links = {}

    out: List[str] = []
    for item in rows:
        ref = _value(item, "ref")
        _append_unique(out, ref)

        if _value(item, "kind") == "situation" and ref.startswith("situation:"):
            situation = situations.get(ref.split(":", 1)[1])
            for linked in (situation or {}).get("linked_object_refs") or []:
                safe = _safe_situation_link(linked)
                if safe:
                    _append_unique(out, safe)

        if _value(item, "kind") != "disagreement":
            continue
        link = links.get(ref)
        if not link:
            continue

        source_type = str(link.get("source_type") or "")
        source_object_ref = str(link.get("source_object_ref") or "").strip()
        if source_type == "email" and source_object_ref:
            _append_unique(out, f"mail:{source_object_ref}")
        elif source_object_ref:
            _append_unique(out, source_object_ref)

        target_ref = str(link.get("target_ref") or "").strip()
        if str(link.get("target_kind") or "") == "appointment" and target_ref:
            _append_unique(out, _calendar_ref(target_ref))
        elif target_ref:
            _append_unique(out, target_ref)

    return out[:8]
