"""Version identity for governed and legacy Memory used as agent evidence."""
from __future__ import annotations

import hashlib
import json


MEMORY_VERSION_FIELDS = (
    "id", "status", "revision", "statement", "content", "summary", "fact_summary",
    "epistemic_status", "authority", "confidence", "temporal_scope", "created_at", "updated_at",
)
MEMORY_READ_PROJECTION = {"_id": 0, **{key: 1 for key in MEMORY_VERSION_FIELDS}}


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
