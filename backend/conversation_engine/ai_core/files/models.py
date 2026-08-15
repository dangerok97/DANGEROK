"""ContextFile — user-supplied evidence for AI Core (domain-neutral).

Wraps Documents V2 storage/extraction. Cognition must NOT branch on document type.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

FileStatus = Literal["uploaded", "processing", "ready", "failed"]

MAX_ATTACHMENTS_PER_MESSAGE = 5
MAX_SESSION_FILES = 20
PREVIEW_CHARS = 400
CHUNK_CHARS = 3500
MAX_CHUNKS_PER_READ = 4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_context_file_id() -> str:
    return f"lcf_{uuid.uuid4().hex[:14]}"


class ContextFile(BaseModel):
    """Canonical AI-readable file evidence (references Documents V2 blob)."""

    id: str = Field(default_factory=new_context_file_id)
    user_id: str
    document_id: str  # Documents V2 id (doc_…)
    session_id: Optional[str] = None
    original_name: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    content_hash: str = ""
    status: FileStatus = "uploaded"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    # Derived (never dump full text into every prompt)
    preview: str = ""
    page_count: Optional[int] = None
    extraction_method: str = ""
    processing_notes: str = ""
    text_available: bool = False
    char_count: int = 0
    # Soft associations (opaque ids)
    goal_refs: List[str] = Field(default_factory=list)
    plan_refs: List[str] = Field(default_factory=list)
    object_refs: List[str] = Field(default_factory=list)
    message_ref: Optional[str] = None
    # AI-optional descriptive label — NOT a closed domain enum / router
    semantic_label: str = ""
    user_supplied: bool = True
    provenance: Dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def lightweight(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "name": (self.original_name or "")[:120],
            "mime_type": self.mime_type,
            "status": self.status,
            "preview": (self.preview or "")[:PREVIEW_CHARS],
            "text_available": bool(self.text_available),
            "char_count": int(self.char_count or 0),
            "page_count": self.page_count,
            "user_supplied": True,
            "semantic_label": (self.semantic_label or "")[:160],
            "plan_refs": list(self.plan_refs or [])[:4],
            "object_refs": list(self.object_refs or [])[:4],
            "processing_notes": (self.processing_notes or "")[:200],
        }

    def evidence_dict(self) -> Dict[str, Any]:
        name = (self.semantic_label or self.original_name or "user_file")[:120]
        return {
            "ref": self.document_id or self.id,
            "kind": "USER_PROVIDED_CONTENT",
            "label": name,
            "display_name": name,
            "source_type": "user_file",
            "source_id": self.document_id or self.id,
            "status": "active",
        }


def sanitize_filename(name: str) -> str:
    base = os.path.basename(name or "")[:255] or "file.bin"
    # Strip control chars / path tricks
    base = re.sub(r"[\x00-\x1f]", "", base)
    if ".." in base or base.startswith("\\") or base.startswith("/"):
        base = "file.bin"
    return base


def content_sha256(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def chunk_text(text: str, *, start: int = 0, max_chunks: int = MAX_CHUNKS_PER_READ) -> List[Dict[str, Any]]:
    raw = text or ""
    if not raw:
        return []
    out: List[Dict[str, Any]] = []
    i = max(0, int(start or 0))
    n = 0
    while i < len(raw) and n < max_chunks:
        piece = raw[i : i + CHUNK_CHARS]
        out.append(
            {
                "offset": i,
                "length": len(piece),
                "text": piece,
                "has_more": i + len(piece) < len(raw),
            }
        )
        i += CHUNK_CHARS
        n += 1
    return out
