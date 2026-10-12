"""Current, owned Memory sources behind autonomous work and queued results.

This is a provenance check, not a relevance judgement. A correction requires
new work; a forgotten source cannot support new work or replay an old result.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from agent.memory_sources import MEMORY_READ_PROJECTION, memory_source_id, memory_source_version

MAX_SOURCES = 64
CURRENT_STATUSES = (None, "active", "known", "likely", "ambiguous")


class MemorySourcesUnavailable(RuntimeError):
    """Reading source validity failed; absence has not been established."""


@dataclass
class MemorySourceState:
    status: str = "current"
    replacements: dict[str, str] = field(default_factory=dict)
    versions: dict[str, str] = field(default_factory=dict)

    @property
    def snapshot(self) -> str:
        if not self.versions:
            return ""
        payload = json.dumps(self.versions, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def _ref(memory_id: str) -> str:
    return memory_id if memory_id.startswith("mem_") else f"memory:{memory_id}"


async def inspect_memory_sources(db, owner_id: str, goal) -> MemorySourceState:
    """Read bounded versions, never transfer Memory text into the result.

    Explicit goal refs cover work before its first read. Provenance covers
    bounded discovery reads and drafts that depend on memories not originally
    cited by the goal. The preparation's evidence remains in the check even
    when newer reads have displaced it from the ordinary recent window.
    """
    if getattr(goal, "owner_id", owner_id) != owner_id:
        return MemorySourceState(status="revoked")
    refs = {str(ref) for ref in (getattr(goal, "source_refs", None) or []) if memory_source_id(ref)}
    goal_id = getattr(goal, "id", "")
    try:
        rows = await db.agent_evidence.find({
            "owner_id": owner_id, "goal_id": goal_id, "superseded": {"$ne": True},
            "$or": [{"provenance.capability": "information.read"},
                    {"provenance.source_versions": {"$exists": True, "$ne": {}}}],
        }, {"_id": 0, "id": 1, "claim": 1, "provenance": 1}).sort("observed_at", -1).limit(40).to_list(40) if goal_id else []
        prepared = list(getattr(goal, "prepared_sources", None) or [])[:12]
        unbound_preparation = bool(getattr(goal, "prepared_text", "")) and not prepared
        if prepared:
            cited = await db.agent_evidence.find({
                "owner_id": owner_id, "goal_id": goal_id, "id": {"$in": prepared},
            }, {"_id": 0, "id": 1, "claim": 1, "provenance": 1, "superseded": 1}).limit(12).to_list(12)
            current_ids = {row.get("id") for row in cited if not row.get("superseded")}
            unbound_preparation = not set(prepared) <= current_ids
            # Keep the provenance of superseded cited rows long enough to
            # detect a withdrawal. A missing row instead requires rereading;
            # its absence cannot certify the text from today's empty state.
            known = {row.get("id") for row in rows}
            rows.extend(row for row in cited if row.get("id") not in known)
        expected: dict[str, set[str]] = {}
        unversioned = set()
        unbound_read = False
        for row in rows:
            provenance = row.get("provenance") or {}
            versions = provenance.get("source_versions") or {}
            recorded_refs = [*versions, *(provenance.get("source_refs") or [])]
            if (provenance.get("capability") == "information.read" and row.get("claim")
                    and provenance.get("source_class") != "simulated"
                    and not any(memory_source_id(ref) for ref in recorded_refs)
                    and provenance.get("memory_read_scope") != "empty"):
                # The previous reader recorded text without handles, even
                # for a nonempty Memory read. Invalidate it once and reread;
                # a currently empty store does not prove the old claim safe.
                unbound_read = True
            for raw, digest in versions.items():
                memory_id = memory_source_id(raw)
                if memory_id:
                    refs.add(raw)
                    expected.setdefault(memory_id, set()).add(str(digest))
            for raw in provenance.get("source_refs") or []:
                memory_id = memory_source_id(raw)
                if memory_id:
                    refs.add(raw)
                    if not any(memory_source_id(key) == memory_id for key in versions):
                        unversioned.add(memory_id)
        ids = {memory_source_id(ref) for ref in refs}
        pending = (getattr(goal, "source_situation", None) or {}).get("memory_refresh_pending") == "true"
        if not ids:
            return MemorySourceState(status="changed" if unbound_read or unbound_preparation or pending else "current")
        if len(ids) > MAX_SOURCES:
            raise MemorySourcesUnavailable("memory_source_check_bounded")
        projection = {**MEMORY_READ_PROJECTION, "superseded_by": 1, "supersedes_refs": 1}
        docs = await db.memories.find({"user_id": owner_id, "id": {"$in": sorted(ids)}},
                                     projection).limit(MAX_SOURCES).to_list(MAX_SOURCES)
        by_id = {str(doc.get("id")): doc for doc in docs}
        state = MemorySourceState(status="changed" if unbound_read or unbound_preparation or pending else "current")
        for memory_id in sorted(ids):
            doc = by_id.get(memory_id)
            if doc is None or doc.get("status") == "forgotten":
                return MemorySourceState(status="revoked")
            visited = {memory_id}
            while doc.get("status") == "superseded":
                replacement_id = memory_source_id(str(doc.get("superseded_by") or ""))
                if not replacement_id or replacement_id in visited or len(visited) >= 4:
                    return MemorySourceState(status="revoked")
                replacement = await db.memories.find_one(
                    {"user_id": owner_id, "id": replacement_id}, projection,
                )
                # Both ends are governed and owned. An arbitrary pointer may
                # not substitute someone else's memory for this person's fact.
                if not replacement or str(doc["id"]) not in (replacement.get("supersedes_refs") or []):
                    return MemorySourceState(status="revoked")
                visited.add(replacement_id)
                doc = replacement
                state.status = "changed"
            if doc.get("status") not in CURRENT_STATUSES:
                return MemorySourceState(status="revoked")
            current_ref = _ref(str(doc["id"]))
            version = memory_source_version(doc)
            state.versions[current_ref] = version
            for original in refs:
                if memory_source_id(original) == memory_id:
                    state.replacements[original] = current_ref
            if (memory_id in unversioned
                    or any(version != old for old in expected.get(memory_id, set()))):
                state.status = "changed"
        return state
    except MemorySourcesUnavailable:
        raise
    except Exception as exc:
        raise MemorySourcesUnavailable(type(exc).__name__) from None


async def memory_result_current(db, owner_id: str, goal, snapshot: str) -> bool:
    """Old delivery/visibility records cannot borrow newer source versions."""
    state = await inspect_memory_sources(db, owner_id, goal)
    return state.status == "current" and state.snapshot == (snapshot or "")


async def opportunity_memories_current(db, owner_id: str, opportunity) -> bool:
    """A queued concern cannot quote a canonically withdrawn Memory source."""
    from types import SimpleNamespace

    if getattr(opportunity, "owner_id", owner_id) != owner_id:
        return False
    refs = [getattr(item, "ref", "") for item in getattr(opportunity, "evidence", [])
            if getattr(item, "kind", "") == "memory"]
    if not any(memory_source_id(ref) for ref in refs):
        return True
    state = await inspect_memory_sources(
        db, owner_id, SimpleNamespace(id="", owner_id=owner_id, source_refs=refs),
    )
    return state.status == "current"
