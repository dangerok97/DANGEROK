"""Source provenance — replace bare source_count with typed source lists.

Non-destructive: keeps `source_count` as alias of `total_sources`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from life_objects.models import LifeObject


SOURCE_KINDS = (
    "document",
    "conversation",
    "goal",
    "calendar",
    "brain",
    "manual",
)


def _unique_append(lst: List[str], value: Optional[str]) -> List[str]:
    if not value:
        return lst
    if value not in lst:
        lst.append(value)
    return lst


def ensure_provenance_fields(obj: LifeObject) -> LifeObject:
    """Migrate legacy source lists into typed provenance (non-destructive)."""
    doc_src = list(getattr(obj, "document_sources", None) or [])
    conv_src = list(getattr(obj, "conversation_sources", None) or [])
    goal_src = list(getattr(obj, "goal_sources", None) or [])
    cal_src = list(getattr(obj, "calendar_sources", None) or [])
    brain_src = list(getattr(obj, "brain_sources", None) or [])
    manual_src = list(getattr(obj, "manual_sources", None) or [])

    # Seed from legacy arrays if typed lists empty
    if not doc_src:
        for d in obj.documents or []:
            doc_src = _unique_append(doc_src, d)
    if not goal_src:
        for g in obj.goals or []:
            goal_src = _unique_append(goal_src, g)
    if not cal_src:
        for c in obj.calendar_events or []:
            cal_src = _unique_append(cal_src, c)
    if not brain_src:
        for b in obj.brain_nodes or []:
            brain_src = _unique_append(brain_src, b)

    obj.document_sources = doc_src
    obj.conversation_sources = conv_src
    obj.goal_sources = goal_src
    obj.calendar_sources = cal_src
    obj.brain_sources = brain_src
    obj.manual_sources = manual_src
    recompute_totals(obj)
    return obj


def recompute_totals(obj: LifeObject) -> None:
    total = (
        len(obj.document_sources or [])
        + len(obj.conversation_sources or [])
        + len(obj.goal_sources or [])
        + len(obj.calendar_sources or [])
        + len(obj.brain_sources or [])
        + len(obj.manual_sources or [])
    )
    obj.total_sources = total
    obj.source_count = total  # backward compat


def add_source(
    obj: LifeObject,
    *,
    kind: str,
    source_id: Optional[str],
) -> LifeObject:
    ensure_provenance_fields(obj)
    if not source_id:
        return obj
    k = str(kind or "manual").strip().lower()
    if k == "document":
        obj.document_sources = _unique_append(list(obj.document_sources or []), source_id)
        if source_id not in (obj.documents or []):
            obj.documents.append(source_id)
    elif k == "conversation":
        obj.conversation_sources = _unique_append(list(obj.conversation_sources or []), source_id)
    elif k == "goal":
        obj.goal_sources = _unique_append(list(obj.goal_sources or []), source_id)
        if source_id not in (obj.goals or []):
            obj.goals.append(source_id)
    elif k == "calendar":
        obj.calendar_sources = _unique_append(list(obj.calendar_sources or []), source_id)
        if source_id not in (obj.calendar_events or []):
            obj.calendar_events.append(source_id)
    elif k == "brain":
        obj.brain_sources = _unique_append(list(obj.brain_sources or []), source_id)
        if source_id not in (obj.brain_nodes or []):
            obj.brain_nodes.append(source_id)
    else:
        obj.manual_sources = _unique_append(list(obj.manual_sources or []), source_id)
    recompute_totals(obj)
    return obj


def provenance_public(obj: LifeObject) -> Dict[str, Any]:
    ensure_provenance_fields(obj)
    return {
        "document_sources": list(obj.document_sources or []),
        "conversation_sources": list(obj.conversation_sources or []),
        "goal_sources": list(obj.goal_sources or []),
        "calendar_sources": list(obj.calendar_sources or []),
        "brain_sources": list(obj.brain_sources or []),
        "manual_sources": list(obj.manual_sources or []),
        "total_sources": int(obj.total_sources or 0),
        "source_count": int(obj.source_count or obj.total_sources or 0),
    }
