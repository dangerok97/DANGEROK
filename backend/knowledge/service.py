"""
KnowledgeService — owner of the `node_knowledge` MongoDB collection.

Kept 100% independent from the Life Graph and Decision Engine modules:
- Reads `life_nodes` in READ-ONLY mode just to verify ownership + node type.
- Writes ONLY to its own collection.
- Emits a small `history` per knowledge doc (created/replaced/merged/property_set/property_removed/cleared).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .schemas import SCHEMAS, coerce_properties, schema_for


SCHEMA_VERSION = 1  # bump only when a breaking schema change happens.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"know_{uuid.uuid4().hex[:12]}"


class KnowledgeService:
    def __init__(self, db):
        self.db = db

    @property
    def col(self):
        return self.db.node_knowledge

    @property
    def nodes_col(self):
        return self.db.life_nodes

    # ------------------------------------------------------------------
    # ownership check
    # ------------------------------------------------------------------
    async def _resolve_node(self, user_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        """Return the raw node doc (without _id) or None if not owned."""
        return await self.nodes_col.find_one(
            {"id": node_id, "user_id": user_id},
            {"_id": 0, "id": 1, "type": 1, "label": 1, "user_id": 1, "status": 1},
        )

    # ------------------------------------------------------------------
    # read
    # ------------------------------------------------------------------
    async def get(self, user_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        """Return the knowledge doc for a node (never returns None if the node
        exists: yields an empty-properties doc so the caller has a stable shape).
        Returns None ONLY if the node does not belong to the user."""
        node = await self._resolve_node(user_id, node_id)
        if not node:
            return None
        doc = await self.col.find_one({"user_id": user_id, "node_id": node_id}, {"_id": 0})
        if not doc:
            return self._empty_doc(user_id, node_id, node["type"])
        # Attach the schema for the client's convenience.
        doc["schema"] = schema_for(node["type"])
        doc["node_type"] = node["type"]
        return doc

    def _empty_doc(self, user_id: str, node_id: str, node_type: str) -> Dict[str, Any]:
        return {
            "id": None,
            "user_id": user_id,
            "node_id": node_id,
            "node_type": node_type,
            "properties": {},
            "schema": schema_for(node_type),
            "schema_version": SCHEMA_VERSION,
            "created_at": None,
            "updated_at": None,
            "history": [],
        }

    # ------------------------------------------------------------------
    # write
    # ------------------------------------------------------------------
    async def replace(self, user_id: str, node_id: str, properties: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """PUT semantics: overwrite the properties bag entirely."""
        node = await self._resolve_node(user_id, node_id)
        if not node:
            return None
        clean = coerce_properties(node["type"], properties)
        clean = _strip_nones(clean)

        existing = await self.col.find_one({"user_id": user_id, "node_id": node_id})
        entry = {"at": _now(), "event": "replaced", "data": {"keys": list(clean.keys())}}
        if existing:
            await self.col.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "properties": clean,
                        "updated_at": _now(),
                        "schema_version": SCHEMA_VERSION,
                    },
                    "$push": {"history": entry},
                },
            )
        else:
            doc = {
                "id": _new_id(),
                "user_id": user_id,
                "node_id": node_id,
                "node_type": node["type"],
                "properties": clean,
                "schema_version": SCHEMA_VERSION,
                "created_at": _now(),
                "updated_at": _now(),
                "history": [{"at": _now(), "event": "created", "data": {"keys": list(clean.keys())}}],
            }
            await self.col.insert_one(doc)
        return await self.get(user_id, node_id)

    async def merge(self, user_id: str, node_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """PATCH semantics: merge `patch` into existing properties.

        Rules:
          - Known keys are coerced against the schema.
          - `None` values ERASE the corresponding key.
          - Unknown keys go under `_extra` (deep-merged with existing `_extra`).
          - Lists REPLACE (not append). Callers that need append can read+write.
        """
        node = await self._resolve_node(user_id, node_id)
        if not node:
            return None

        existing = await self.col.find_one({"user_id": user_id, "node_id": node_id})
        current = (existing or {}).get("properties", {}) or {}

        coerced = coerce_properties(node["type"], patch)
        merged = dict(current)

        # Merge top-level; delete on None.
        for k, v in coerced.items():
            if k == "_extra":
                # deep-merge extras
                current_extra = merged.get("_extra") or {}
                new_extra = dict(current_extra)
                for ek, ev in v.items():
                    if ev is None:
                        new_extra.pop(ek, None)
                    else:
                        new_extra[ek] = ev
                if new_extra:
                    merged["_extra"] = new_extra
                else:
                    merged.pop("_extra", None)
                continue
            if v is None:
                merged.pop(k, None)
            else:
                merged[k] = v

        entry = {"at": _now(), "event": "merged", "data": {"keys": list(coerced.keys())}}
        if existing:
            await self.col.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {"properties": merged, "updated_at": _now(), "schema_version": SCHEMA_VERSION},
                    "$push": {"history": entry},
                },
            )
        else:
            doc = {
                "id": _new_id(),
                "user_id": user_id,
                "node_id": node_id,
                "node_type": node["type"],
                "properties": merged,
                "schema_version": SCHEMA_VERSION,
                "created_at": _now(),
                "updated_at": _now(),
                "history": [{"at": _now(), "event": "created", "data": {"keys": list(coerced.keys())}}],
            }
            await self.col.insert_one(doc)
        return await self.get(user_id, node_id)

    async def set_property(self, user_id: str, node_id: str, key: str, value: Any) -> Optional[Dict[str, Any]]:
        """Set / overwrite a single property. Convenience wrapper over merge."""
        return await self.merge(user_id, node_id, {key: value})

    async def remove_property(self, user_id: str, node_id: str, key: str) -> Optional[Dict[str, Any]]:
        node = await self._resolve_node(user_id, node_id)
        if not node:
            return None
        existing = await self.col.find_one({"user_id": user_id, "node_id": node_id})
        if not existing:
            # Nothing to remove — return the current (empty) shape.
            return await self.get(user_id, node_id)
        props = dict(existing.get("properties") or {})
        removed = False
        if key in props:
            props.pop(key)
            removed = True
        else:
            extra = dict(props.get("_extra") or {})
            if key in extra:
                extra.pop(key)
                if extra:
                    props["_extra"] = extra
                else:
                    props.pop("_extra", None)
                removed = True
        if removed:
            await self.col.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {"properties": props, "updated_at": _now()},
                    "$push": {"history": {"at": _now(), "event": "property_removed", "data": {"key": key}}},
                },
            )
        return await self.get(user_id, node_id)

    async def clear(self, user_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        node = await self._resolve_node(user_id, node_id)
        if not node:
            return None
        existing = await self.col.find_one({"user_id": user_id, "node_id": node_id})
        if existing:
            await self.col.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {"properties": {}, "updated_at": _now()},
                    "$push": {"history": {"at": _now(), "event": "cleared", "data": {}}},
                },
            )
        return await self.get(user_id, node_id)

    # ------------------------------------------------------------------
    # bulk
    # ------------------------------------------------------------------
    async def list_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        cursor = self.col.find({"user_id": user_id}, {"_id": 0}).sort("updated_at", -1)
        return await cursor.to_list(length=1000)


def _strip_nones(d: Dict[str, Any]) -> Dict[str, Any]:
    """Remove keys whose value is None. Preserve `_extra` after inner strip."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if k == "_extra" and isinstance(v, dict):
            inner = {ek: ev for ek, ev in v.items() if ev is not None}
            if inner:
                out[k] = inner
            continue
        out[k] = v
    return out


# Re-export for convenience.
SCHEMAS = SCHEMAS  # noqa: PLW0127
