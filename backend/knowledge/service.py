"""
KnowledgeService — owner of the `node_knowledge` MongoDB collection.

Guarantees provided by this module
----------------------------------
1. **Provenance-first storage.** Every property is stored as an envelope
   containing value + type + unit + sensitivity + a full `provenance` block.
2. **Optimistic concurrency.** Each doc has a `version`. Writes accept an
   `expected_version`; a mismatch raises `VersionConflict` (mapped to HTTP 409).
3. **Rich audit log.** Every mutation appends a `history` entry with
   `{at, actor_type, actor_id, source_type, property, previous, next, reason, event}`.
   Sensitive property values are redacted (`"***"`) in the audit stream.
4. **Soft delete.** `DELETE` sets `status="archived"` + `archived_at/by/reason`;
   `restore()` reactivates. Permanent purge is intentionally NOT exposed.
5. **Cross-user isolation.** Every op verifies the node belongs to `user_id`
   by reading `life_nodes` in read-only. Direct queries are always filtered.
6. **No premature interpretation.** The service does NOT link to decisions,
   modify the Life Graph, call GPT, or auto-derive facts.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .normalize import NormalizationError, normalize_key, normalize_properties, sanitize_value
from .provenance import (
    VALID_SENSITIVITY,
    build_envelope,
    coerce_provenance,
    merge_envelope_update,
    value_of,
)
from .schemas import SCHEMAS, schema_for, schema_index, sensitive_keys_of


SCHEMA_VERSION = 2  # bumped in iteration 5 (envelope-based storage)

logger = logging.getLogger("ora.knowledge")


class VersionConflict(Exception):
    """Raised when an optimistic-lock version mismatch occurs."""
    def __init__(self, expected: int, current: int):
        super().__init__(f"version conflict: expected {expected}, got {current}")
        self.expected = expected
        self.current = current


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"know_{uuid.uuid4().hex[:12]}"


class KnowledgeService:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------
    # collections
    # ------------------------------------------------------------------
    @property
    def col(self):
        return self.db.node_knowledge

    @property
    def nodes_col(self):
        return self.db.life_nodes

    # ------------------------------------------------------------------
    # ownership
    # ------------------------------------------------------------------
    async def _resolve_node(self, user_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        """Read-only lookup; returns node dict or None if not owned."""
        return await self.nodes_col.find_one(
            {"id": node_id, "user_id": user_id},
            {"_id": 0, "id": 1, "type": 1, "label": 1, "user_id": 1, "status": 1},
        )

    # ------------------------------------------------------------------
    # read
    # ------------------------------------------------------------------
    async def get(self, user_id: str, node_id: str, *, include_archived: bool = False) -> Optional[Dict[str, Any]]:
        node = await self._resolve_node(user_id, node_id)
        if not node:
            return None
        q: Dict[str, Any] = {"user_id": user_id, "node_id": node_id}
        if not include_archived:
            q["status"] = {"$ne": "archived"}
        doc = await self.col.find_one(q, {"_id": 0})
        if not doc:
            return self._empty_doc(user_id, node_id, node["type"])
        doc["schema"] = schema_for(node["type"])
        doc["node_type"] = node["type"]
        return doc

    async def get_property(self, user_id: str, node_id: str, key: str) -> Optional[Dict[str, Any]]:
        try:
            nk = normalize_key(key)
        except NormalizationError as e:
            raise NormalizationError(str(e))
        doc = await self.get(user_id, node_id)
        if doc is None:
            return None
        env = (doc.get("properties") or {}).get(nk)
        return {
            "key": nk,
            "envelope": env,
            "value": value_of(env) if env else None,
        }

    async def history(self, user_id: str, node_id: str, limit: int = 200) -> Optional[List[Dict[str, Any]]]:
        node = await self._resolve_node(user_id, node_id)
        if not node:
            return None
        doc = await self.col.find_one({"user_id": user_id, "node_id": node_id}, {"_id": 0, "history": 1})
        events = (doc or {}).get("history") or []
        limit = max(1, min(limit, 1000))
        return events[-limit:]

    async def list_for_user(self, user_id: str, include_archived: bool = False) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if not include_archived:
            q["status"] = {"$ne": "archived"}
        cursor = self.col.find(q, {"_id": 0}).sort("updated_at", -1)
        return await cursor.to_list(length=1000)

    def _empty_doc(self, user_id: str, node_id: str, node_type: str) -> Dict[str, Any]:
        return {
            "id": None,
            "user_id": user_id,
            "node_id": node_id,
            "node_type": node_type,
            "properties": {},
            "schema": schema_for(node_type),
            "schema_version": SCHEMA_VERSION,
            "version": 0,
            "status": "active",
            "created_at": None,
            "updated_at": None,
            "history": [],
        }

    # ------------------------------------------------------------------
    # write helpers
    # ------------------------------------------------------------------
    def _build_envelopes(self, node_type: str, properties: Dict[str, Any], *, default_source: str, actor_provenance: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Normalize keys/values, then wrap each into a full envelope."""
        cleaned = normalize_properties(properties)
        schema = schema_index(node_type)
        out: Dict[str, Any] = {}
        for k, v in cleaned.items():
            if k == "_extra":
                # `_extra` is stored as a plain object; not envelope-wrapped.
                out[k] = v if isinstance(v, dict) else {}
                continue
            if v is None:
                # sentinel used by merge() to erase — keep None here, merge() strips
                out[k] = None
                continue
            hint = schema.get(k)
            env = build_envelope(v, schema_hint=hint, default_source=default_source, actor_provenance=actor_provenance)
            # Enforce sensitivity to legal set.
            if env.get("sensitivity") not in VALID_SENSITIVITY:
                env["sensitivity"] = "personal"
            # Serialized-size guard.
            try:
                _size_ok(env)
            except NormalizationError as e:
                raise NormalizationError(f"proprietà '{k}': {e}")
            out[k] = env
        return out

    def _history_entry(self, *, event: str, property: Optional[str], previous: Any, next_: Any, actor_type: str, actor_id: Optional[str], source_type: str, reason: Optional[str], node_type: str) -> Dict[str, Any]:
        """Build an audit entry with sensitive values redacted."""
        sset = set(sensitive_keys_of(node_type))
        def _safe(env: Any) -> Any:
            if env is None:
                return None
            if property and property in sset:
                # Never log raw values of sensitive fields.
                return {"redacted": True, "value_type": (env.get("value_type") if isinstance(env, dict) else None)}
            # For non-sensitive envelopes, keep only the primitive value + type.
            if isinstance(env, dict) and "value" in env and "value_type" in env:
                return {"value": env.get("value"), "value_type": env.get("value_type")}
            return env
        return {
            "at": _now(),
            "event": event,
            "property": property,
            "previous": _safe(previous),
            "next": _safe(next_),
            "actor_type": actor_type,
            "actor_id": actor_id,
            "source_type": source_type,
            "reason": reason,
        }

    async def _ensure_doc(self, user_id: str, node_id: str, node_type: str) -> Dict[str, Any]:
        """Return existing doc, or create a fresh one and return it (with `_id`)."""
        doc = await self.col.find_one({"user_id": user_id, "node_id": node_id})
        if doc:
            return doc
        seed = {
            "id": _new_id(),
            "user_id": user_id,
            "node_id": node_id,
            "node_type": node_type,
            "properties": {},
            "version": 0,
            "status": "active",
            "schema_version": SCHEMA_VERSION,
            "created_at": _now(),
            "updated_at": _now(),
            "history": [],
        }
        await self.col.insert_one(seed)
        # Return the doc (find_one includes _id which the caller uses only as filter).
        return await self.col.find_one({"user_id": user_id, "node_id": node_id})

    # ------------------------------------------------------------------
    # public writes
    # ------------------------------------------------------------------
    async def replace(
        self,
        user_id: str,
        node_id: str,
        properties: Dict[str, Any],
        *,
        expected_version: Optional[int] = None,
        actor_type: str = "user",
        actor_id: Optional[str] = None,
        source_type: str = "user_input",
        reason: Optional[str] = None,
        actor_provenance: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        node = await self._resolve_node(user_id, node_id)
        if not node:
            return None
        doc = await self._ensure_doc(user_id, node_id, node["type"])
        if expected_version is not None and doc["version"] != expected_version:
            raise VersionConflict(expected_version, doc["version"])

        envelopes = self._build_envelopes(node["type"], properties or {}, default_source=source_type, actor_provenance=actor_provenance)
        # Strip Nones on replace (bare-value semantics).
        envelopes = {k: v for k, v in envelopes.items() if v is not None}

        # Compare with existing to build fine-grained per-property audit entries.
        prev = doc.get("properties") or {}
        events: List[Dict[str, Any]] = [
            self._history_entry(
                event="replaced", property=None, previous=None, next_=None,
                actor_type=actor_type, actor_id=actor_id, source_type=source_type,
                reason=reason, node_type=node["type"],
            )
        ]
        for k in set(list(prev.keys()) + list(envelopes.keys())):
            if k == "_extra":
                continue
            events.append(self._history_entry(
                event="property_replaced" if k in envelopes else "property_removed",
                property=k, previous=prev.get(k), next_=envelopes.get(k),
                actor_type=actor_type, actor_id=actor_id, source_type=source_type,
                reason=reason, node_type=node["type"],
            ))

        res = await self.col.update_one(
            {"_id": doc["_id"], "version": doc["version"]},
            {
                "$set": {"properties": envelopes, "updated_at": _now(), "schema_version": SCHEMA_VERSION, "status": "active"},
                "$inc": {"version": 1},
                "$push": {"history": {"$each": events}},
                "$unset": {"archived_at": "", "archived_by": "", "archive_reason": ""},
            },
        )
        if res.matched_count == 0:
            # Someone else moved the version between load and write.
            latest = await self.col.find_one({"user_id": user_id, "node_id": node_id}, {"version": 1})
            raise VersionConflict(doc["version"], (latest or {}).get("version", -1))

        self._log_write(node["type"], "replace", user_id, node_id, envelopes)
        return await self.get(user_id, node_id, include_archived=True)

    async def merge(
        self,
        user_id: str,
        node_id: str,
        patch: Dict[str, Any],
        *,
        expected_version: Optional[int] = None,
        actor_type: str = "user",
        actor_id: Optional[str] = None,
        source_type: str = "user_input",
        reason: Optional[str] = None,
        actor_provenance: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        node = await self._resolve_node(user_id, node_id)
        if not node:
            return None
        doc = await self._ensure_doc(user_id, node_id, node["type"])
        if expected_version is not None and doc["version"] != expected_version:
            raise VersionConflict(expected_version, doc["version"])

        incoming = self._build_envelopes(node["type"], patch or {}, default_source=source_type, actor_provenance=actor_provenance)
        current = dict(doc.get("properties") or {})
        events: List[Dict[str, Any]] = []

        for k, v in incoming.items():
            if k == "_extra":
                cur_extra = current.get("_extra") or {}
                new_extra = dict(cur_extra)
                if isinstance(v, dict):
                    for ek, ev in v.items():
                        if ev is None:
                            if ek in new_extra:
                                new_extra.pop(ek)
                        else:
                            new_extra[ek] = ev
                if new_extra:
                    current["_extra"] = new_extra
                else:
                    current.pop("_extra", None)
                events.append(self._history_entry(
                    event="extra_merged", property="_extra", previous=cur_extra, next_=new_extra,
                    actor_type=actor_type, actor_id=actor_id, source_type=source_type,
                    reason=reason, node_type=node["type"],
                ))
                continue
            if v is None:
                # Erase semantics.
                if k in current:
                    prev_env = current.pop(k)
                    events.append(self._history_entry(
                        event="property_removed", property=k, previous=prev_env, next_=None,
                        actor_type=actor_type, actor_id=actor_id, source_type=source_type,
                        reason=reason, node_type=node["type"],
                    ))
                continue
            prev_env = current.get(k)
            new_env = merge_envelope_update(prev_env, v) if prev_env else v
            current[k] = new_env
            events.append(self._history_entry(
                event="property_set" if prev_env is None else "property_updated",
                property=k, previous=prev_env, next_=new_env,
                actor_type=actor_type, actor_id=actor_id, source_type=source_type,
                reason=reason, node_type=node["type"],
            ))

        if not events:
            # No changes → don't bump version, but return current state.
            return await self.get(user_id, node_id, include_archived=True)

        res = await self.col.update_one(
            {"_id": doc["_id"], "version": doc["version"]},
            {
                "$set": {"properties": current, "updated_at": _now(), "schema_version": SCHEMA_VERSION, "status": "active"},
                "$inc": {"version": 1},
                "$push": {"history": {"$each": events}},
                "$unset": {"archived_at": "", "archived_by": "", "archive_reason": ""},
            },
        )
        if res.matched_count == 0:
            latest = await self.col.find_one({"user_id": user_id, "node_id": node_id}, {"version": 1})
            raise VersionConflict(doc["version"], (latest or {}).get("version", -1))

        self._log_write(node["type"], "merge", user_id, node_id, incoming)
        return await self.get(user_id, node_id, include_archived=True)

    async def set_property(
        self,
        user_id: str,
        node_id: str,
        key: str,
        value: Any,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        try:
            nk = normalize_key(key)
        except NormalizationError as e:
            raise NormalizationError(str(e))
        return await self.merge(user_id, node_id, {nk: value}, **kwargs)

    async def remove_property(
        self,
        user_id: str,
        node_id: str,
        key: str,
        *,
        expected_version: Optional[int] = None,
        actor_type: str = "user",
        actor_id: Optional[str] = None,
        source_type: str = "user_input",
        reason: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            nk = normalize_key(key)
        except NormalizationError as e:
            raise NormalizationError(str(e))
        node = await self._resolve_node(user_id, node_id)
        if not node:
            return None
        doc = await self.col.find_one({"user_id": user_id, "node_id": node_id})
        if not doc:
            return await self.get(user_id, node_id, include_archived=True)
        if expected_version is not None and doc["version"] != expected_version:
            raise VersionConflict(expected_version, doc["version"])

        props = dict(doc.get("properties") or {})
        prev = None
        if nk in props:
            prev = props.pop(nk)
        elif isinstance(props.get("_extra"), dict) and nk in props["_extra"]:
            extra = dict(props["_extra"])
            prev = extra.pop(nk)
            if extra:
                props["_extra"] = extra
            else:
                props.pop("_extra", None)
        else:
            return await self.get(user_id, node_id, include_archived=True)

        entry = self._history_entry(
            event="property_removed", property=nk, previous=prev, next_=None,
            actor_type=actor_type, actor_id=actor_id, source_type=source_type,
            reason=reason, node_type=node["type"],
        )
        res = await self.col.update_one(
            {"_id": doc["_id"], "version": doc["version"]},
            {
                "$set": {"properties": props, "updated_at": _now()},
                "$inc": {"version": 1},
                "$push": {"history": entry},
            },
        )
        if res.matched_count == 0:
            latest = await self.col.find_one({"user_id": user_id, "node_id": node_id}, {"version": 1})
            raise VersionConflict(doc["version"], (latest or {}).get("version", -1))

        self._log_write(node["type"], "remove_property", user_id, node_id, {nk: None})
        return await self.get(user_id, node_id, include_archived=True)

    # ------------------------------------------------------------------
    # soft delete + restore
    # ------------------------------------------------------------------
    async def archive(
        self,
        user_id: str,
        node_id: str,
        *,
        reason: Optional[str] = None,
        actor_type: str = "user",
        actor_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        node = await self._resolve_node(user_id, node_id)
        if not node:
            return None
        doc = await self.col.find_one({"user_id": user_id, "node_id": node_id})
        if not doc:
            # Create a placeholder + immediately archive so users always get a stable shape.
            doc = await self._ensure_doc(user_id, node_id, node["type"])
        entry = self._history_entry(
            event="archived", property=None, previous=None, next_=None,
            actor_type=actor_type, actor_id=actor_id, source_type="user_input",
            reason=reason, node_type=node["type"],
        )
        await self.col.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "status": "archived",
                    "archived_at": _now(),
                    "archived_by": actor_id or user_id,
                    "archive_reason": reason,
                    "updated_at": _now(),
                },
                "$inc": {"version": 1},
                "$push": {"history": entry},
            },
        )
        return await self.get(user_id, node_id, include_archived=True)

    async def restore(
        self,
        user_id: str,
        node_id: str,
        *,
        reason: Optional[str] = None,
        actor_type: str = "user",
        actor_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        node = await self._resolve_node(user_id, node_id)
        if not node:
            return None
        doc = await self.col.find_one({"user_id": user_id, "node_id": node_id})
        if not doc:
            return await self.get(user_id, node_id, include_archived=True)
        entry = self._history_entry(
            event="restored", property=None, previous=None, next_=None,
            actor_type=actor_type, actor_id=actor_id, source_type="user_input",
            reason=reason, node_type=node["type"],
        )
        await self.col.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {"status": "active", "updated_at": _now()},
                "$unset": {"archived_at": "", "archived_by": "", "archive_reason": ""},
                "$inc": {"version": 1},
                "$push": {"history": entry},
            },
        )
        return await self.get(user_id, node_id, include_archived=True)

    # ------------------------------------------------------------------
    # log helper — never log raw values.
    # ------------------------------------------------------------------
    def _log_write(self, node_type: str, op: str, user_id: str, node_id: str, envelopes: Dict[str, Any]):
        # Log only keys + value_types. Never values, never provenance sub-fields.
        summary: Dict[str, Optional[str]] = {}
        for k, env in envelopes.items():
            if k == "_extra":
                summary[k] = "extras"
                continue
            if isinstance(env, dict):
                summary[k] = env.get("value_type") if env.get("sensitivity") not in ("sensitive", "highly_sensitive") else "***"
            else:
                summary[k] = "erased" if env is None else "value"
        logger.info("knowledge.%s user=%s node=%s type=%s keys=%s", op, user_id, node_id, node_type, summary)


# ------------------------------------------------------------------
# module-level helpers for size checks
# ------------------------------------------------------------------
def _size_ok(env: Dict[str, Any]) -> None:
    """Cheap serialized-size guard using JSON-like traversal."""
    import json
    try:
        raw = json.dumps(env, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as e:
        raise NormalizationError(f"serializzazione fallita: {e}")
    from .normalize import MAX_SERIALIZED_VALUE_BYTES
    if len(raw.encode("utf-8")) > MAX_SERIALIZED_VALUE_BYTES:
        raise NormalizationError(f"payload troppo grande (>{MAX_SERIALIZED_VALUE_BYTES} bytes)")


# Public re-exports
__all__ = [
    "KnowledgeService",
    "VersionConflict",
    "SCHEMAS",
    "schema_for",
    "SCHEMA_VERSION",
    "sanitize_value",
    "coerce_provenance",
]
