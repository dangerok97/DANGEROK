"""Life Profile + Life Setup session models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

SetupStatus = Literal[
    "not_started",
    "active",
    "skipped",
    "interrupted",
    "completed",
    "cancelled",
]

FactSource = Literal[
    "user_said",
    "user_confirmed",
    "document_extract",
    "semantic_extract",
    "inferred",
    "system",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_setup_id() -> str:
    return f"lsu_{uuid.uuid4().hex[:14]}"


FieldStatus = Literal["extracted", "suggested", "confirmed", "corrected", "rejected"]


class ProfileObject(BaseModel):
    key: str
    value: Any = None
    raw_value: Any = None
    confidence: float = 0.5
    source: FactSource = "user_said"
    status: FieldStatus = "extracted"
    updated_at: str = Field(default_factory=now_iso)
    linked_doc_ids: List[str] = Field(default_factory=list)
    confirmed: bool = False
    source_document_id: Optional[str] = None
    source_page: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    # Integer revision preferred; legacy semantic strings accepted & coerced upstream
    analysis_version: Optional[Any] = None
    confirmed_at: Optional[str] = None


class DomainProfile(BaseModel):
    domain: str
    objects: Dict[str, ProfileObject] = Field(default_factory=dict)
    confidence: float = 0.0
    source: FactSource = "system"
    updated_at: str = Field(default_factory=now_iso)
    benefits_available: List[str] = Field(default_factory=list)
    benefits_active: List[str] = Field(default_factory=list)
    missing_info: List[str] = Field(default_factory=list)
    linked_docs: List[str] = Field(default_factory=list)
    goal_id: Optional[str] = None
    life_node_id: Optional[str] = None
    pending_confirmations: List[Dict[str, Any]] = Field(default_factory=list)
    related_documents: List[Dict[str, Any]] = Field(default_factory=list)

    def known_keys(self) -> List[str]:
        return [k for k, o in self.objects.items() if o.value not in (None, "", [], False)]


class LifeProfile(BaseModel):
    user_id: str
    domains: Dict[str, DomainProfile] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    version: str = "life-profile-1.0"

    def public(self) -> Dict[str, Any]:
        return self.model_dump()


class LifeSetupSession(BaseModel):
    id: str = Field(default_factory=new_setup_id)
    user_id: str
    status: SetupStatus = "not_started"
    conversation_session_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    completed_at: Optional[str] = None
    interrupted_at: Optional[str] = None
    domains_touched: List[str] = Field(default_factory=list)
    asked_questions: List[str] = Field(default_factory=list)
    asked_keys: List[str] = Field(default_factory=list)
    refused_keys: List[str] = Field(default_factory=list)
    postponed_keys: List[str] = Field(default_factory=list)
    known_facts: Dict[str, Any] = Field(default_factory=dict)
    benefits_active: List[str] = Field(default_factory=list)
    linked_doc_types: List[str] = Field(default_factory=list)
    linked_doc_ids: List[str] = Field(default_factory=list)
    last_plan: Optional[Dict[str, Any]] = None
    last_turn: Optional[Dict[str, Any]] = None
    phase: str = "greeting"
    show_wizard_later: bool = False  # ALWAYS false — module becomes invisible
    resume_suggestion_emitted: bool = False
    pending_document_id: Optional[str] = None
    pending_document_type: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def public(self) -> Dict[str, Any]:
        d = self.model_dump()
        # Never expose a permanent Life Setup nav flag
        d["module_visible"] = False
        d["ui_mode"] = "natural_conversation"
        return d


class StartBody(BaseModel):
    force: bool = False


class AnswerBody(BaseModel):
    text: str
    skip_domain: bool = False


class SkipBody(BaseModel):
    domain: Optional[str] = None
    postpone_all: bool = False


class UploadDocBody(BaseModel):
    document_id: Optional[str] = None
    doc_type: Optional[str] = None
    synthetic_text: Optional[str] = None  # local/e2e force path
    filename: Optional[str] = None


class ExplainBody(BaseModel):
    plan: Optional[Dict[str, Any]] = None


class AttachDocumentBody(BaseModel):
    """Attach a REAL Documents V2 document (already uploaded) to the
    Life Experience conversation. No file bytes travel through this body —
    upload always goes through `POST /api/documents/upload` first."""
    document_id: str
    doc_type: Optional[str] = None


class ConfirmFieldBody(BaseModel):
    domain: str
    key: str


class CorrectFieldBody(BaseModel):
    domain: str
    key: str
    value: Any


class RejectFieldBody(BaseModel):
    domain: str
    key: str


class ResolveConfirmationBody(BaseModel):
    domain: str
    key: str
    resolution: Literal["keep_existing", "use_new", "dismiss"]
