"""
Candidate discovery — narrow the set of nodes considered for a Decision.

Rationale: iterating over ALL user nodes is fine at 20 or 200 nodes, but
becomes wasteful with real integrations. This module returns a small,
opinionated candidate set produced by three cheap filters:

1. Explicit references: `decision.node_ids` + `decision.linked_to` if they
   point to nodes.
2. Category compatibility: all nodes whose `type` is compatible with
   `decision.category` (via CATEGORY_TYPE_COMPAT).
3. Text scan: nodes whose `label` normalized is a substring of the decision
   text — cheap keyword filter to catch loosely-mentioned entities.

The Candidate objects returned here still need to be scored by the matchers;
this module never assigns confidence.
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

from .matcher import decision_text, normalize_text
from .types import CATEGORY_TYPE_COMPAT, Candidate


# Which decision.metadata identifier keys imply which node types should be
# force-included in the candidate set (regardless of category compat).
_ID_TO_NODE_TYPES: Dict[str, List[str]] = {
    "plate":       ["car"],
    "contract_id": ["contract", "subscription"],
    "document_id": ["document"],
    "iban":        ["finance"],
    "flight":      ["trip"],
}


async def find_candidates(repo, user_id: str, decision: Dict[str, Any]) -> List[Candidate]:
    """Return a de-duplicated list of Candidate stubs (no signals yet)."""
    explicit_ids: Set[str] = set(decision.get("node_ids") or [])
    for lid in decision.get("linked_to") or []:
        explicit_ids.add(lid)

    compat_types: Set[str] = set(CATEGORY_TYPE_COMPAT.get(decision.get("category") or "generic", frozenset()))

    # Broaden with identifier-hinted node types from decision.metadata.
    md = decision.get("metadata") or {}
    if isinstance(md, dict):
        for k, extra_types in _ID_TO_NODE_TYPES.items():
            if md.get(k):
                compat_types.update(extra_types)

    # One bulk fetch of nodes we care about: compat types + explicit ids.
    q_types: List[str] = list(compat_types) if compat_types else []
    nodes = await repo.list_nodes(user_id, node_types=q_types or None)

    # Also fetch explicit ones that may not match compat types.
    if explicit_ids:
        explicit_nodes: List[Dict[str, Any]] = []
        for nid in explicit_ids:
            n = await repo.get_node(user_id, nid)
            if n:
                explicit_nodes.append(n)
        # de-dup by id
        by_id = {n["id"]: n for n in nodes}
        for n in explicit_nodes:
            by_id[n["id"]] = n
        nodes = list(by_id.values())

    # Text-scan: bring in any active node whose label appears in decision text.
    dtext = decision_text(decision)
    if dtext:
        # cheap: iterate ALL nodes only if we have very few explicit / compat matches.
        # For scale, we'd add a text index. Here we just scan actively-typed nodes.
        seen = {n["id"] for n in nodes}
        all_nodes = await repo.list_nodes(user_id)  # active only
        for n in all_nodes:
            if n["id"] in seen:
                continue
            label_norm = normalize_text(n.get("label") or "")
            if label_norm and len(label_norm) >= 3 and label_norm in dtext:
                nodes.append(n)
                seen.add(n["id"])

    return [
        Candidate(
            node_id=n["id"],
            node_type=n.get("type") or "generic",
            node_label=n.get("label") or "",
        )
        for n in nodes
    ]
