"""Life Context Graph V1 — domain-neutral relationship model.

An edge connects two CANONICAL refs the AI already sees in its context payload
(situation:, goal:, plan:, object:, document:, calendar:, profile:, file:,
presence:, or a bare governed mem_ id). It never duplicates the referenced
entity's own data — only the relationship between two existing records.

`predicate` is open free text (AI-authored), never a closed enum: the runtime
only enforces length/format/ref-validity, never a cognitive taxonomy.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

EdgeOperation = Literal["none", "create", "update", "supersede", "deactivate"]
EdgeStatus = Literal["active", "superseded", "resolved", "rejected"]
EdgeAuthority = Literal[
    "user_confirmed", "user_stated", "document", "structured", "inferred", "device"
]
EdgeSensitivity = Literal["normal", "sensitive", "high"]

# Recognized canonical-ref prefixes — the exact vocabulary already surfaced to
# the AI via ContextFact.ref (context_sources.py) plus "object:" for
# GenerativeObject, which has no existing ContextBroker source of its own.
# This is a SECURITY/STRUCTURAL boundary (valid ref shape), never a cognitive
# taxonomy — predicate stays fully open.
KNOWN_REF_PREFIXES: tuple[str, ...] = (
    "situation:",
    "goal:",
    "plan:",
    "object:",
    "document:",
    "calendar:",
    "profile:",
    "file:",
    "presence:",
)

_PREDICATE_RE = re.compile(r"^[a-z0-9_]{1,60}$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_recognized_ref(ref: Optional[str]) -> bool:
    """Structural validity only — never a semantic/domain judgement."""
    if not ref or not isinstance(ref, str):
        return False
    r = ref.strip()
    if not r or len(r) > 160:
        return False
    if r.startswith(KNOWN_REF_PREFIXES):
        return True
    # Governed Memory refs are bare mem_<hex> (no colon), matching the
    # existing_memory_ref convention already used by life_memory.
    return bool(re.match(r"^mem_[a-f0-9]{6,40}$", r))


def normalize_predicate(value: Optional[str]) -> str:
    """Format hygiene only (lowercase/underscore/length) — vocabulary stays open."""
    t = " ".join(str(value or "").strip().lower().split())
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t[:60]


class ContextEdgeUpdate(BaseModel):
    """AI-facing mutation proposal. Runtime governs; AI decides meaning."""

    operation: EdgeOperation = "none"
    edge_id: Optional[str] = Field(default=None, max_length=80)
    subject_ref: Optional[str] = Field(default=None, max_length=160)
    predicate: Optional[str] = Field(default=None, max_length=60)
    object_ref: Optional[str] = Field(default=None, max_length=160)
    semantic_summary: Optional[str] = Field(default=None, max_length=240)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    authority: EdgeAuthority = "inferred"
    provenance: List[str] = Field(default_factory=list, max_length=6)
    evidence_refs: List[str] = Field(default_factory=list, max_length=6)
    temporal_scope: Optional[Dict[str, Any]] = None
    sensitivity: EdgeSensitivity = "normal"
    reversible: bool = True
    coexists_with_refs: List[str] = Field(default_factory=list, max_length=4)
    reason: Optional[str] = Field(default=None, max_length=240)

    @field_validator("predicate")
    @classmethod
    def _norm_predicate(cls, v: Optional[str]) -> Optional[str]:
        return normalize_predicate(v) if v else v

    @field_validator("subject_ref", "object_ref", "edge_id")
    @classmethod
    def _strip_ref(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) else v

    @field_validator("provenance", "evidence_refs", "coexists_with_refs")
    @classmethod
    def _bounded_strings(cls, values: List[str]) -> List[str]:
        out: List[str] = []
        for value in values or []:
            clean = " ".join(str(value or "").split())[:160]
            if clean and clean not in out:
                out.append(clean)
        return out


class ContextEdgeEvent(BaseModel):
    revision: int
    operation: EdgeOperation
    at: str = Field(default_factory=now_iso)
    reasoning_epoch: Optional[str] = None
    changes: Dict[str, Any] = Field(default_factory=dict)


class ContextEdge(BaseModel):
    """Persisted record. AI proposes; this shape is what governance guarantees."""

    id: str
    user_id: str
    session_id: Optional[str] = None
    subject_ref: str
    predicate: str
    object_ref: str
    semantic_summary: Optional[str] = None
    status: EdgeStatus = "active"
    confidence: float = 0.5
    authority: EdgeAuthority = "inferred"
    provenance: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    temporal_scope: Optional[Dict[str, Any]] = None
    sensitivity: EdgeSensitivity = "normal"
    reversible: bool = True
    coexists_with_refs: List[str] = Field(default_factory=list)
    supersedes_ref: Optional[str] = None
    superseded_by: Optional[str] = None
    governance_key: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    revision: int = 1
    history: List[ContextEdgeEvent] = Field(default_factory=list)

    def context_preview(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "subject_ref": self.subject_ref,
            "predicate": self.predicate,
            "object_ref": self.object_ref,
            "semantic_summary": self.semantic_summary,
            "status": self.status,
            "confidence": self.confidence,
            "authority": self.authority,
            "sensitivity": self.sensitivity,
            "temporal_scope": self.temporal_scope,
            "revision": self.revision,
            "updated_at": self.updated_at,
        }
