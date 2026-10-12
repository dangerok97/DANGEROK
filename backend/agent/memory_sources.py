"""Version identity for governed and legacy Memory used as agent evidence."""
from __future__ import annotations

import hashlib
import json


MEMORY_VERSION_FIELDS = (
    "id", "status", "revision", "statement", "content", "summary", "fact_summary",
    "epistemic_status", "authority", "confidence", "temporal_scope", "created_at", "updated_at",
)
MEMORY_READ_PROJECTION = {"_id": 0, **{key: 1 for key in MEMORY_VERSION_FIELDS}}
MAX_MEMORY_PREVIEWS = 8
MEMORY_PREVIEW_CHARACTERS = 600


def memory_source_id(raw: str) -> str:
    ref = str(raw or "").strip()
    if not ref or len(ref) > 120 or ref == "memory:index":
        return ""
    if ref.startswith(("user_memory:", "memory:")):
        return ref.split(":", 1)[1]
    return ref if ref.startswith("mem_") else ""


def memory_source_version(doc: dict) -> str:
    """Legacy notes may lack revision; a material change still invalidates reuse.

    Only a digest is persisted with evidence, never a second raw copy of the
    memory. Reads and later fences use the exact same fields and encoding.
    """
    payload = {key: doc.get(key) for key in MEMORY_VERSION_FIELDS}
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def read_memory_previews(db, owner_id: str, refs, *, limit: int = MAX_MEMORY_PREVIEWS) -> list[dict]:
    """Project only cited, current Memory for admission and discovery.

    This is context for deciding whether work is useful, not agent evidence
    or a fresh observation of the fact. Missing and withdrawn references do
    not fall back to unrelated recent notes. Callers report missing coverage;
    database errors propagate so an outage cannot look like a complete read.
    """
    bound = max(1, min(int(limit), MAX_MEMORY_PREVIEWS))
    requested: dict[str, str] = {}
    for raw in refs or []:
        memory_id = memory_source_id(raw)
        if memory_id and memory_id not in requested:
            requested[memory_id] = str(raw).strip()
            if len(requested) == bound:
                break
    if not requested:
        return []

    docs = await db.memories.find(
        {"user_id": owner_id, "id": {"$in": list(requested)},
         "status": {"$in": [None, "active", "known", "likely", "ambiguous"]}},
        {**MEMORY_READ_PROJECTION, "provenance": 1},
    ).limit(bound).to_list(bound)
    by_id = {str(doc.get("id") or ""): doc for doc in docs}
    previews = []
    for memory_id, ref in requested.items():
        doc = by_id.get(memory_id)
        if doc is None:
            continue
        statement = next((doc[key].strip() for key in ("statement", "content", "summary", "fact_summary")
                          if isinstance(doc.get(key), str) and doc[key].strip()), "")
        if not statement:
            continue
        temporal = doc.get("temporal_scope") or {}
        temporal = temporal if isinstance(temporal, dict) else {}
        epistemic = doc.get("epistemic_status") or (
            doc.get("status") if doc.get("status") in ("known", "likely", "ambiguous") else "unknown"
        )
        provenance = doc.get("provenance") or []
        provenance = provenance if isinstance(provenance, list) else []
        previews.append({
            "ref": ref,
            "source": "memory",
            "statement": statement[:MEMORY_PREVIEW_CHARACTERS],
            "excerpt_truncated": len(statement) > MEMORY_PREVIEW_CHARACTERS,
            "status": str(doc.get("status") or "unknown")[:40],
            "epistemic_status": str(epistemic)[:40],
            "authority": str(doc.get("authority") or "unknown")[:40],
            "provenance": [value[:80] for value in provenance[:3] if isinstance(value, str)],
            "temporal_scope": {
                key: str(temporal[key])[:120]
                for key in ("permanence", "starts_at", "ends_at", "recurrence")
                if temporal.get(key) is not None
            },
            "recorded_at": str(doc.get("updated_at") or doc.get("created_at") or "")[:80] or None,
            # Reading a stored belief today does not confirm it today.
            "freshness": "unknown",
        })
    return previews
