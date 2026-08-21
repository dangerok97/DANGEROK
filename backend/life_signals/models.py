"""Life Change Signal V2.9.1 — domain-neutral "something changed" fact.

A LifeChangeSignal states exactly one thing: a known part of the user's life
state was mutated and the mutation was persisted. It deliberately does NOT
say whether that change matters, what it implies, or whether ORA should
speak — those are V2.9.2 (impact reasoning) and V2.9.3 (attention) and must
not leak backwards into this layer.

It never duplicates the changed entity: it carries canonical refs plus the
minimum technical metadata a future consumer needs to re-resolve authorized
context through the existing Context Broker. No conversation text, no entity
payload, no document content, no AI-generated intent/urgency/importance.

Refs reuse the existing canonical namespace (`context_graph.models`) rather
than inventing a second one.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from context_graph.models import is_recognized_ref

# Technical shape of the mutation — never a domain/semantic taxonomy. This
# vocabulary describes WHAT HAPPENED TO A RECORD, not what it means in the
# user's life. Adding a domain-flavoured member here (e.g. "trip_changed")
# would be an architectural regression.
ChangeKind = Literal[
    "created",
    "updated",
    "cancelled",
    "completed",
    "superseded",
    "linked",
    "unlinked",
]

# Which ORA subsystem owns the mutated record. Used by a future consumer to
# know which service can re-resolve the ref, and for aggregate observability
# without touching content.
SourceSystem = Literal[
    "situation",
    "life_memory",
    "context_graph",
    "life_os",
    "calendar",
]

# How the mutation entered the system. V2.9.1 emits only from the AI Core
# cognitive loop, the single production call site for every AI-native
# mutation subsystem; other entry points stay deliberately unconnected
# (see docs/ARCHITECTURE.md V2.9.1).
SignalProvenance = Literal["ai_core_conversation"]

SignalStatus = Literal["pending", "processed", "failed"]

_MAX_AFFECTED_REFS = 8


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_signal_id() -> str:
    return f"lcs_{uuid.uuid4().hex[:16]}"


def is_valid_dedupe_key(value: Optional[str]) -> bool:
    """Structural check only. A dedupe key must be derivable from the stable
    identity of the mutation (entity ref + revision, or reasoning epoch +
    capability) — never from a timestamp or a fresh random value, which
    would silently disable idempotency."""
    if not value or not isinstance(value, str):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_:.\-]{3,180}", value.strip()))


class LifeChangeSignal(BaseModel):
    """One persisted mutation of the user's known life state."""

    id: str = Field(default_factory=new_signal_id, max_length=40)
    user_id: str = Field(max_length=80)

    # WHAT changed — canonical ref of the mutated entity itself.
    source_ref: str = Field(max_length=160)
    source_system: SourceSystem
    change_kind: ChangeKind

    # Deterministically-known related refs, taken from the mutation result
    # only. V2.9.1 never expands the Context Graph and never asks the AI what
    # else might be affected — that is V2.9.2's job.
    affected_refs: List[str] = Field(default_factory=list, max_length=_MAX_AFFECTED_REFS)

    # Entity revision at mutation time when the owning subsystem tracks one
    # (Situation and Context Graph do). Lets a future consumer detect that it
    # is reasoning about a stale version without re-reading first.
    revision: Optional[int] = None

    # The source subsystem's own authority for this change, when it records
    # one (Memory and Context Graph do). Never re-derived or upgraded here.
    authority: Optional[str] = Field(default=None, max_length=40)

    # The source subsystem's own status word for the mutation. Carries the
    # V2.8.6b Calendar distinction: "partial" means ORA's local state really
    # changed while the Google-side sync stayed unconfirmed, so the signal is
    # legitimate but a future reasoner must not assume the external calendar
    # agrees.
    source_status: Optional[str] = Field(default=None, max_length=32)

    provenance: SignalProvenance = "ai_core_conversation"
    occurred_at: str = Field(default_factory=now_iso)

    # Stable identity of the mutation; a unique sparse index on
    # (user_id, dedupe_key) makes replay idempotent at the storage layer.
    dedupe_key: str = Field(max_length=180)

    # Correlation only — bounded ids, never content.
    session_id: Optional[str] = Field(default=None, max_length=80)
    reasoning_epoch: Optional[str] = Field(default=None, max_length=80)

    status: SignalStatus = "pending"
    attempts: int = 0
    last_error_code: Optional[str] = Field(default=None, max_length=80)

    created_at: str = Field(default_factory=now_iso)
    processed_at: Optional[str] = None

    def public(self) -> Dict[str, Any]:
        """Bounded projection for a future consumer. Deliberately identical to
        the stored shape minus retry bookkeeping — there is no hidden field
        carrying content."""
        return {
            "id": self.id,
            "source_ref": self.source_ref,
            "source_system": self.source_system,
            "change_kind": self.change_kind,
            "affected_refs": list(self.affected_refs),
            "revision": self.revision,
            "authority": self.authority,
            "source_status": self.source_status,
            "provenance": self.provenance,
            "occurred_at": self.occurred_at,
            "status": self.status,
        }


def sanitize_refs(refs: Optional[List[str]], *, exclude: Optional[str] = None) -> List[str]:
    """Keep only structurally valid canonical refs, deduped and bounded. An
    unrecognized ref is dropped rather than stored, so the event store can
    never accumulate a parallel ad-hoc namespace."""
    out: List[str] = []
    for raw in list(refs or []):
        ref = str(raw or "").strip()
        if not ref or ref == exclude or ref in out:
            continue
        if not is_recognized_ref(ref):
            continue
        out.append(ref)
        if len(out) >= _MAX_AFFECTED_REFS:
            break
    return out
