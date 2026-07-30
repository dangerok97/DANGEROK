"""
Knowledge Layer — structured, per-node-type properties.

Adds *meaning* to Life Graph nodes without modifying the Life Graph module or
the Decision Engine. Uses its own MongoDB collection (`node_knowledge`) keyed
by (user_id, node_id).

Public API:
    from knowledge import KnowledgeService, SCHEMAS, schema_for
"""
from .schemas import SCHEMAS, schema_for, SUPPORTED_TYPES
from .service import KnowledgeService

__all__ = ["KnowledgeService", "SCHEMAS", "schema_for", "SUPPORTED_TYPES"]
