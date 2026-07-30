"""
Life Graph — persistent nodes + edges representing the user's life.

Isolated from the Decision Engine. This module ONLY stores knowledge; it never
ranks or decides. In a future iteration the Decision Engine will read this
graph as a context source (via DecisionContext.signals["life_graph"]).

Public API:
    from life_graph import LifeGraphService, NodeType, RelationType
"""
from .types import NodeType, RelationType, NODE_TYPES, RELATION_TYPES
from .service import LifeGraphService

__all__ = [
    "LifeGraphService",
    "NodeType",
    "RelationType",
    "NODE_TYPES",
    "RELATION_TYPES",
]
