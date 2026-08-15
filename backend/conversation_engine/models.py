"""Conversation Engine session model — orchestration state only (no domain logic)."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

ENGINE_VERSION = "conversation-engine-1.0"

Origin = Literal[
    "home",
    "voice",
    "text",
    "documents",
    "notifications",
    "proactive",
    "life_setup",
    "memoria",
    # Future stubs — accepted but not simulated
    "email",
    "whatsapp",
    "open_banking",
]

SessionStatus = Literal[
    "active",
    "waiting_user",
    "running_action",
    "completed",
    "cancelled",
    "paused",
]

STUB_ORIGINS = frozenset({"email", "whatsapp", "open_banking"})


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_session_id() -> str:
    return f"ces_{uuid.uuid4().hex[:14]}"


def new_resume_token() -> str:
    return f"crt_{secrets.token_urlsafe(18)}"


class HistoryEntry(BaseModel):
    """Compact collaboration step — not a chat bubble transcript."""

    at: str = Field(default_factory=now_iso)
    role: Literal["user", "ora", "system"] = "system"
    kind: str  # start|intent|goal|question|answer|artifact|status|resume|cancel
    text: Optional[str] = None
    step_id: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ArtifactRef(BaseModel):
    kind: str  # goal|project|action_session|study_plan|travel_project|calendar|brain|suggestion
    id: str
    label: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ConversationSession(BaseModel):
    id: str = Field(default_factory=new_session_id)
    user_id: str
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    status: SessionStatus = "active"
    origin: Origin = "text"
    input: Optional[str] = None
    intent: Optional[Dict[str, Any]] = None
    goal_id: Optional[str] = None
    project_id: Optional[str] = None
    action_session_id: Optional[str] = None
    current_step: Optional[str] = None
    history: List[HistoryEntry] = Field(default_factory=list)
    artifacts: List[ArtifactRef] = Field(default_factory=list)
    summary: Optional[str] = None
    resume_token: str = Field(default_factory=new_resume_token)
    engine_version: str = ENGINE_VERSION
    voice_meta: Optional[Dict[str, Any]] = None
    suggestion_id: Optional[str] = None
    known_slots: Dict[str, Any] = Field(default_factory=dict)
    extracted_entities: Dict[str, Any] = Field(default_factory=dict)
    confirmed_entities: Dict[str, Any] = Field(default_factory=dict)
    missing_slots: List[str] = Field(default_factory=list)
    ambiguous_slots: List[str] = Field(default_factory=list)
    extraction_version: Optional[str] = None
    last_extraction_at: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def append_history(
        self,
        *,
        role: str,
        kind: str,
        text: Optional[str] = None,
        step_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.history.append(
            HistoryEntry(
                role=role,  # type: ignore[arg-type]
                kind=kind,
                text=text,
                step_id=step_id,
                meta=meta or {},
            )
        )
        self.touch()

    def add_artifact(self, kind: str, aid: str, label: Optional[str] = None, **meta: Any) -> None:
        if any(a.kind == kind and a.id == aid for a in self.artifacts):
            return
        self.artifacts.append(ArtifactRef(kind=kind, id=aid, label=label, meta=meta))
        self.touch()

    def understood_summary(self) -> Dict[str, str]:
        """Compact human labels — no technical field names for UI."""
        labels = {
            "departure_date": "Partenza",
            "return_date": "Ritorno",
            "destination": "Destinazione",
            "transport": "Trasporto",
            "lodging": "Alloggio",
            "subject": "Materia",
            "exam_date": "Data esame",
            "appointment_type": "Visita",
            "appointment_date": "Data",
            "appointment_time": "Ora",
            "payee": "Beneficiario",
            "amount": "Importo",
        }
        out: Dict[str, str] = {}
        src = {**(self.known_slots or {}), **{
            k: (v.get("normalized") if isinstance(v, dict) else v)
            for k, v in (self.extracted_entities or {}).items()
        }}
        for key, label in labels.items():
            v = src.get(key)
            if v in (None, "", []):
                continue
            if isinstance(v, dict):
                v = v.get("label") or v.get("normalized") or v.get("start_date") or v
            out[label] = str(v)
        return out

    def public(self, *, include_history: bool = False) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "status": self.status,
            "origin": self.origin,
            "input": self.input,
            "intent": self.intent,
            "goal_id": self.goal_id,
            "project_id": self.project_id,
            "action_session_id": self.action_session_id,
            "current_step": self.current_step,
            "artifacts": [a.model_dump() for a in self.artifacts],
            "summary": self.summary,
            "resume_token": self.resume_token,
            "engine_version": self.engine_version,
            "voice_meta": self.voice_meta,
            "suggestion_id": self.suggestion_id,
            "known_slots": self.known_slots,
            "extracted_entities": self.extracted_entities,
            "confirmed_entities": self.confirmed_entities,
            "missing_slots": self.missing_slots,
            "ambiguous_slots": self.ambiguous_slots,
            "extraction_version": self.extraction_version,
            "last_extraction_at": self.last_extraction_at,
            "understood_summary": self.understood_summary(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "meta": {
                k: v
                for k, v in self.meta.items()
                if k
                in (
                    "first_question",
                    "action_flow",
                    "route",
                    "ui_mode",
                    "stub_origin",
                    "proactive_context",
                    "synthetic_prompt",
                    "gap",
                    "reason_summary",
                )
            },
        }
        if include_history:
            d["history"] = [h.model_dump() for h in self.history]
        else:
            d["history_len"] = len(self.history)
        return d


class StartBody(BaseModel):
    text: Optional[str] = None
    origin: Origin = "text"
    voice_meta: Optional[Dict[str, Any]] = None
    suggestion_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    force_new: bool = False
    # V2.5 production entry metadata (opaque refs only — not cognition)
    entry_point: Optional[str] = None
    plan_id: Optional[str] = None
    object_id: Optional[str] = None
    # V2.6 attachments
    attachments: Optional[List[Dict[str, Any]]] = None


class MessageBody(BaseModel):
    text: Optional[str] = None
    option_id: Optional[str] = None
    value: Any = None
    skip: bool = False
    # V2.6 — opaque ContextFile / document refs (not binary)
    attachments: Optional[List[Dict[str, Any]]] = None


class AttachmentRef(BaseModel):
    file_id: Optional[str] = None
    document_id: Optional[str] = None
    display_name: Optional[str] = None
    mime_type: Optional[str] = None


class ContinueBody(BaseModel):
    note: Optional[str] = None


class ResumeBody(BaseModel):
    session_id: Optional[str] = None
    resume_token: Optional[str] = None


class CancelBody(BaseModel):
    reason: Optional[str] = None
