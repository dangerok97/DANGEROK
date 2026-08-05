"""Validated structured analysis schemas (Pydantic)."""
from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator  # noqa: F401 — field_validator used below


Priority = Literal["low", "medium", "high", "critical"]
Urgency = Literal["none", "upcoming", "soon", "urgent", "overdue"]


class EntityItem(BaseModel):
    type: str
    value: str
    confidence: float = Field(ge=0, le=1, default=0.5)


class DocumentAnalysis(BaseModel):
    document_id: str
    original_filename: str
    suggested_title: str
    short_description: str = ""
    macro_category: str
    subcategory: str
    confidence: float = Field(ge=0, le=1)
    language: Optional[str] = None
    summary: str = ""
    summary_detailed: str = ""
    keywords: List[str] = Field(default_factory=list)
    entities: List[EntityItem] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    monetary_values: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    requires_review: bool = False
    reasoning_summary: str = ""
    created_at: str
    model: str = "local-deterministic"
    prompt_version: str = "none"
    analysis_version: int = 1
    ai_used: bool = False
    local_only: bool = True


class EventCandidate(BaseModel):
    id: str
    title: str
    description: str = ""
    start_datetime: Optional[str] = None  # ISO UTC
    end_datetime: Optional[str] = None
    start_text_original: Optional[str] = None
    timezone: str = "Europe/Rome"
    all_day: bool = False
    venue_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    booking_reference: Optional[str] = None
    organizer: Optional[str] = None
    source_document_id: str
    category: str = "event"
    priority: Priority = "medium"
    urgency: Urgency = "none"
    confidence: float = Field(ge=0, le=1, default=0.5)
    missing_fields: List[str] = Field(default_factory=list)
    extraction_notes: str = ""
    status: Literal["proposed", "confirmed", "dismissed", "remind_later"] = "proposed"
    ambiguous_date: bool = False
    maps_query: Optional[str] = None
    user_overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def _c(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class EducationAnalysis(BaseModel):
    subject: Optional[str] = None
    topic: Optional[str] = None
    level: Optional[str] = None
    suggested_title: str = ""
    simple_explanation: str = ""
    summary_short: str = ""
    summary_detailed: str = ""
    outline: List[str] = Field(default_factory=list)
    key_concepts: List[str] = Field(default_factory=list)
    definitions: List[str] = Field(default_factory=list)
    important_people: List[str] = Field(default_factory=list)
    important_dates: List[str] = Field(default_factory=list)
    formulas: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
    questions_for_review: List[str] = Field(default_factory=list)
    exam_questions: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    estimated_read_minutes: Optional[int] = None
    difficulty: Optional[str] = None
    confidence: float = Field(ge=0, le=1, default=0.5)


class Flashcard(BaseModel):
    id: str
    question: str
    answer: str
    source_ref: Optional[str] = None
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    review_status: Literal["new", "learning", "known"] = "new"


class QuizTurn(BaseModel):
    question: str
    expected_points: List[str] = Field(default_factory=list)
    user_answer: Optional[str] = None
    feedback: Optional[str] = None
    covered: bool = False


class QuizSession(BaseModel):
    id: str
    document_id: str
    turns: List[QuizTurn] = Field(default_factory=list)
    current_index: int = 0
    status: Literal["active", "completed"] = "active"
    created_at: str
    updated_at: str


class AdminAnalysis(BaseModel):
    sender: Optional[str] = None
    recipient: Optional[str] = None
    subject: Optional[str] = None
    document_number: Optional[str] = None
    amount: Optional[str] = None
    currency: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    payment_method: Optional[str] = None
    required_actions: List[str] = Field(default_factory=list)
    duration: Optional[str] = None
    renewal: Optional[str] = None
    cancellation: Optional[str] = None
    contacts: List[str] = Field(default_factory=list)
    simple_explanation: str = ""
    completed: bool = False
    priority: Priority = "medium"
    urgency: Urgency = "none"
    confidence: float = Field(ge=0, le=1, default=0.5)


class FieldProvenance(BaseModel):
    field_key: str
    extracted: Optional[Any] = None
    suggested: Optional[Any] = None
    confirmed: Optional[Any] = None
    corrected: Optional[Any] = None
    status: Literal["extracted", "suggested", "confirmed", "corrected", "rejected"] = "extracted"
    confidence: Optional[float] = None
    source: Optional[str] = None


class GenericAction(BaseModel):
    action_type: str
    title: str
    description: str = ""
    due_datetime: Optional[str] = None
    amount: Optional[str] = None
    priority: Priority = "medium"
    urgency: Urgency = "none"
    confidence: float = Field(ge=0, le=1, default=0.5)
    requires_confirmation: bool = True
    completed: bool = False


SyncStatus = Literal[
    "local_only", "pending", "synced", "failed", "conflict", "revoked",
]


class CalendarEventDraft(BaseModel):
    id: str
    user_id: str
    provider: Literal["internal", "google", "apple"] = "internal"
    title: str
    description: str = ""
    start_datetime: Optional[str] = None
    end_datetime: Optional[str] = None
    timezone: str = "Europe/Rome"
    all_day: bool = False
    location: Optional[str] = None
    source_document_id: str
    source_event_candidate_id: str
    status: Literal["draft", "confirmed", "cancelled"] = "confirmed"
    created_at: str
    updated_at: str
    # Google sync linkage
    sync_provider: Optional[Literal["internal", "google", "apple"]] = "internal"
    sync_status: SyncStatus = "local_only"
    google_calendar_id: Optional[str] = None
    google_event_id: Optional[str] = None
    google_event_html_link: Optional[str] = None
    google_event_etag: Optional[str] = None
    last_synced_at: Optional[str] = None
    sync_error: Optional[str] = None
    sync_version: int = 0
    priority: Optional[str] = None
    urgency: Optional[str] = None


def _coerce_str_list(v: Any) -> List[str]:
    """Accept list[str] or dict[str,str] (common Gemini shape for definitions)."""
    if v is None:
        return []
    if isinstance(v, dict):
        out: List[str] = []
        for k, val in v.items():
            if val is None:
                out.append(str(k))
            else:
                out.append(f"{k}: {val}")
        return out
    if isinstance(v, list):
        return [str(x) for x in v if x is not None]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


class LLMEducationEnrichment(BaseModel):
    subject: Optional[str] = None
    topic: Optional[str] = None
    key_concepts: List[str] = Field(default_factory=list)
    definitions: List[str] = Field(default_factory=list)
    questions_for_review: List[str] = Field(default_factory=list)

    @field_validator("key_concepts", "definitions", "questions_for_review", mode="before")
    @classmethod
    def _lists(cls, v: Any) -> List[str]:
        return _coerce_str_list(v)


class LLMDocumentEnrichment(BaseModel):
    """Validated structured enrichment from providers — never free-form."""
    suggested_title: Optional[str] = None
    summary: Optional[str] = None
    summary_detailed: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    education: Optional[LLMEducationEnrichment] = None
    notes: Optional[str] = None

    @field_validator("keywords", mode="before")
    @classmethod
    def _kw(cls, v: Any) -> List[str]:
        return _coerce_str_list(v)
