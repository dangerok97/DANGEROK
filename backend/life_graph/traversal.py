"""
Graph traversal helpers. Pure, dict-based, no MongoDB awareness.

The service loads the raw nodes and edges into memory (per user, per request)
and hands them to these functions. Kept intentionally simple — no NetworkX
dependency, no query optimizer. It's more than fast enough for a personal
graph of a few hundred nodes.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, Iterable, List, Set, Tuple


def build_adjacency(edges: Iterable[Dict[str, Any]]) -> Dict[str, List[Tuple[str, Dict[str, Any]]]]:
    """Return {node_id: [(neighbor_id, edge_doc), ...]}, treating edges as
    undirected unless `directed=True`."""
    adj: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
    for e in edges:
        a, b = e.get("from_node"), e.get("to_node")
        if not a or not b:
            continue
        adj.setdefault(a, []).append((b, e))
        if not e.get("directed"):
            adj.setdefault(b, []).append((a, e))
    return adj


def bfs_expand(root_id: str, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], depth: int = 2) -> Dict[str, Any]:
    """Return the subgraph reachable from `root_id` within `depth` hops.

    Response shape:
        {"root": <node>, "nodes": [...], "edges": [...], "distances": {node_id: hops}}
    Nodes and edges beyond depth are excluded.
    """
    depth = max(0, min(depth, 6))
    by_id = {n["id"]: n for n in nodes}
    if root_id not in by_id:
        return {"root": None, "nodes": [], "edges": [], "distances": {}}

    adj = build_adjacency(edges)
    seen: Set[str] = {root_id}
    dist: Dict[str, int] = {root_id: 0}
    queue: deque[str] = deque([root_id])
    kept_edges: List[Dict[str, Any]] = []
    kept_edge_ids: Set[str] = set()

    while queue:
        current = queue.popleft()
        if dist[current] >= depth:
            continue
        for nb, edge in adj.get(current, []):
            if edge["id"] not in kept_edge_ids:
                kept_edges.append(edge)
                kept_edge_ids.add(edge["id"])
            if nb in seen:
                continue
            seen.add(nb)
            dist[nb] = dist[current] + 1
            queue.append(nb)

    return {
        "root": by_id[root_id],
        "nodes": [by_id[nid] for nid in seen if nid in by_id],
        "edges": kept_edges,
        "distances": dist,
    }
