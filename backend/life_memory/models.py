"""Life Memory models — durable learned facts + clarification contract (Prompt 6.1)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

LIFE_MEMORY_VERSION = "life-memory-1.1"

MemoryStatus = Literal["known", "likely", "ambiguous", "superseded"]
MemoryKind = Literal["fact", "note", "study_subject"]
AiEnrichmentStatus = Literal["off", "cached", "fresh", "failed", "skipped"]
ClarifyResolution = Literal["confirmed", "corrected", "still_ambiguous", "failed"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceRef(BaseModel):
    id: str
    kind: str
    label: str = ""
    summary: str = ""


class ProfileWriteTarget(BaseModel):
    """Where governance may write — never a UI taxonomy."""

    domain: str
    key: str


class MemoryItem(BaseModel):
    """Canonical human memory — DATABASE RECORD ≠ MEMORY."""

    id: str
    kind: MemoryKind = "fact"
    statement: str
    belief_statement: Optional[str] = None
    domain: Optional[str] = None
    group_label: Optional[str] = None
    status: MemoryStatus = "known"
    evidence_refs: List[str] = Field(default_factory=list)
    source_refs: List[str] = Field(default_factory=list)
    provenance_label: Optional[str] = None
    learned_at: Optional[str] = None
    updated_at: Optional[str] = None
    editable: bool = False
    sensitivity: Literal["normal", "sensitive"] = "normal"
    # Clarification contract (generic — no city/job UI knowledge)
    slot: Optional[str] = None
    candidate_values: List[str] = Field(default_factory=list)
    profile_targets: List[ProfileWriteTarget] = Field(default_factory=list)
    clarification_goal: Optional[str] = None
    clarifiable: bool = False
    # Debug-only unless MEMORY_DEBUG
    resolution_source: Optional[str] = None
    member_ids: List[str] = Field(default_factory=list)


class MemoryGroup(BaseModel):
    id: str
    label: str
    domain: Optional[str] = None
    memory_ids: List[str] = Field(default_factory=list)


class LifeMemoryResponse(BaseModel):
    ok: bool = True
    version: str = LIFE_MEMORY_VERSION
    memories: List[MemoryItem] = Field(default_factory=list)
    groups: List[MemoryGroup] = Field(default_factory=list)
    evidence: List[EvidenceRef] = Field(default_factory=list)
    fingerprint: str = ""
    deterministic: bool = True
    ai_enrichment: AiEnrichmentStatus = "off"
    partial: bool = False
    partial_sources: List[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=now_iso)
    controls: Dict[str, Any] = Field(
        default_factory=lambda: {
            "correct": False,
            "forget": False,
            "confirm": False,
            "clarify": True,
            "note": (
                "Ambiguous memories open an AI clarification loop. "
                "Canonical writes go through Life Profile governance."
            ),
        }
    )


class GeminiMemoryWording(BaseModel):
    memory_id: str
    statement: Optional[str] = None


class GeminiMemoryPayload(BaseModel):
    wordings: List[GeminiMemoryWording] = Field(default_factory=list)


# --- Clarification (Prompt 6.1) ---


class ClarifyStartBody(BaseModel):
    memory_id: str


class ClarifyAnswerBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class ProposedFact(BaseModel):
    domain: str
    key: str
    value: Any
    action: Literal["confirm", "correct", "suggest"] = "correct"
    confidence: float = 0.8


class GeminiClarifyQuestion(BaseModel):
    question: str
    clarification_goal: Optional[str] = None


class GeminiClarifyResolution(BaseModel):
    resolution: ClarifyResolution = "still_ambiguous"
    target_memory_id: str = ""
    proposed_facts: List[ProposedFact] = Field(default_factory=list)
    additional_facts: List[ProposedFact] = Field(default_factory=list)
    superseded_keys: List[str] = Field(default_factory=list)
    evidence_interpretation: Optional[str] = None
    confidence: float = 0.5
    needs_followup: bool = False
    followup_question: Optional[str] = None


class ClarificationSession(BaseModel):
    id: str
    user_id: str
    memory_id: str
    slot: Optional[str] = None
    belief_statement: str = ""
    status_before: str = "ambiguous"
    candidate_values: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    source_refs: List[str] = Field(default_factory=list)
    provenance_label: Optional[str] = None
    profile_targets: List[ProfileWriteTarget] = Field(default_factory=list)
    clarification_goal: str = (
        "Determine whether this belief about the user is accurate "
        "and what the durable fact should be."
    )
    question: str = ""
    conversation_session_id: Optional[str] = None
    state: Literal["awaiting_answer", "completed", "failed"] = "awaiting_answer"
    resolution: Optional[ClarifyResolution] = None
    user_answer: Optional[str] = None
    applied: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "memory_id": self.memory_id,
            "belief_statement": self.belief_statement,
            "status_before": self.status_before,
            "question": self.question,
            "clarification_goal": self.clarification_goal,
            "candidate_values": self.candidate_values,
            "provenance_label": self.provenance_label,
            "state": self.state,
            "resolution": self.resolution,
            "conversation_session_id": self.conversation_session_id,
            "needs_followup": False,
            "followup_question": None,
            "route": f"/memory-clarify/{self.id}",
        }
