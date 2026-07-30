"""
Knowledge Layer — structured, per-node-type properties.

Adds *meaning* to Life Graph nodes without modifying the Life Graph module or
the Decision Engine. Uses its own MongoDB collection (`node_knowledge`) keyed
by (user_id, node_id).

Public API:
    from knowledge import (
        KnowledgeService, VersionConflict,
        SCHEMAS, schema_for, SUPPORTED_TYPES,
    )
"""
from .schemas import SCHEMAS, schema_for, SUPPORTED_TYPES, sensitive_keys_of
from .service import KnowledgeService, VersionConflict, SCHEMA_VERSION
from .normalize import NormalizationError

__all__ = [
    "KnowledgeService",
    "VersionConflict",
    "NormalizationError",
    "SCHEMAS",
    "schema_for",
    "SUPPORTED_TYPES",
    "sensitive_keys_of",
    "SCHEMA_VERSION",
]
