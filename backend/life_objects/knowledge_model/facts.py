"""Fact store — Digital Twin confirmed knowledge.

FUNDAMENTAL RULE: A Fact is NEVER deleted.
It may be replaced, superseded, or archived — history remains queryable.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from life_objects.knowledge_model.models import KnowledgeFact, now_iso


class FactImmutabilityError(RuntimeError):
    """Raised when code attempts to hard-delete a Fact."""


def list_facts(
    facts: List[KnowledgeFact],
    *,
    active_only: bool = False,
    fact_type: Optional[str] = None,
    include_superseded: bool = True,
) -> List[KnowledgeFact]:
    out: List[KnowledgeFact] = []
    for f in facts or []:
        if fact_type and f.type != fact_type:
            continue
        if active_only and not f.active:
            continue
        if not include_superseded and f.status == "superseded":
            continue
        out.append(f)
    return out


def current_fact_for_type(
    facts: List[KnowledgeFact], fact_type: str,
) -> Optional[KnowledgeFact]:
    for f in facts or []:
        if f.type == fact_type and f.status == "current" and f.active:
            return f
    return None


def find_fact(facts: List[KnowledgeFact], fact_id: str) -> Optional[KnowledgeFact]:
    for f in facts or []:
        if f.id == fact_id:
            return f
    return None


def add_fact(
    facts: List[KnowledgeFact],
    fact: KnowledgeFact,
    *,
    supersede_same_type: bool = True,
) -> List[KnowledgeFact]:
    """Append a new Fact. Optionally supersede previous current of same type.

    Never removes old facts from the list.
    """
    bag = list(facts or [])
    if supersede_same_type and fact.type:
        for old in bag:
            if (
                old.type == fact.type
                and old.status == "current"
                and old.active
                and old.id != fact.id
            ):
                # Value unchanged → bump version in place (still no delete)
                if _values_equal(old.value, fact.value):
                    old.updated_at = now_iso()
                    old.version = int(old.version or 1) + 1
                    old.confidence = max(float(old.confidence or 0), float(fact.confidence or 0))
                    if fact.source_id and not old.source_id:
                        old.source_id = fact.source_id
                    if fact.explanation and not old.explanation:
                        old.explanation = fact.explanation
                    return bag
                old.status = "superseded"
                old.active = False
                old.superseded_by = fact.id
                old.superseded_at = now_iso()
                old.updated_at = now_iso()
    fact.status = "current"
    fact.active = True
    fact.updated_at = now_iso()
    bag.append(fact)
    return bag


def supersede_fact(
    facts: List[KnowledgeFact],
    *,
    old_fact_id: str,
    new_fact: KnowledgeFact,
) -> List[KnowledgeFact]:
    """Explicit supersede: old stays in history, new becomes current."""
    bag = list(facts or [])
    old = find_fact(bag, old_fact_id)
    if old is None:
        bag.append(new_fact)
        return bag
    old.status = "superseded"
    old.active = False
    old.superseded_by = new_fact.id
    old.superseded_at = now_iso()
    old.updated_at = now_iso()
    new_fact.status = "current"
    new_fact.active = True
    new_fact.type = new_fact.type or old.type
    new_fact.version = int(old.version or 1) + 1
    new_fact.updated_at = now_iso()
    bag.append(new_fact)
    return bag


def archive_fact(facts: List[KnowledgeFact], fact_id: str) -> List[KnowledgeFact]:
    """Archive (soft) — Fact remains in Digital Twin history."""
    bag = list(facts or [])
    f = find_fact(bag, fact_id)
    if f is None:
        return bag
    f.status = "archived"
    f.active = False
    f.updated_at = now_iso()
    return bag


def delete_fact(_facts: List[KnowledgeFact], _fact_id: str) -> None:
    """HARD BLOCK — Facts must never be deleted."""
    raise FactImmutabilityError(
        "A Fact is never deleted. Use supersede_fact() or archive_fact() instead."
    )


def facts_history_for_type(facts: List[KnowledgeFact], fact_type: str) -> List[KnowledgeFact]:
    """Full history including superseded — enables 'how many suppliers in 5 years?'."""
    items = [f for f in (facts or []) if f.type == fact_type]
    items.sort(key=lambda x: x.created_at or "")
    return items


def _values_equal(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return str(a).strip().lower() == str(b).strip().lower()


def serialize_facts(facts: List[KnowledgeFact]) -> List[Dict[str, Any]]:
    return [f.model_dump() for f in (facts or [])]
