"""Generic Life OS plans & artifacts — domain-neutral execution state."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

PlanStatus = Literal["active", "paused", "completed", "cancelled"]
ItemStatus = Literal["not_started", "in_progress", "completed", "skipped"]
# DEPRECATED (V2.4): closed artifact catalog — AI Core uses GenerativeObject instead.
# Kept only for read-compat with legacy life_os_artifacts documents.
ArtifactType = Literal[
    "summary",
    "concept_map",
    "flashcards",
    "quiz",
    "checklist",
    "notes",
    "guide",
]
ArtifactStatus = Literal["ready", "failed", "pending"]
EvidenceKind = Literal[
    "USER_PROVIDED_CONTENT",
    "PERSONAL_CONTEXT",
    "TARGET_SPECIFIC_EVIDENCE",
    "GENERAL_EXTERNAL_EVIDENCE",
    "MODEL_KNOWLEDGE",
    "INFERENCE",
]
EvidenceStatus = Literal["active", "superseded", "historical"]
ItemOrigin = Literal[
    "user_stated",
    "user_file",
    "external_evidence",
    "model_assumption",
    "inherited",
    "generated",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_plan_id() -> str:
    return f"lop_{uuid.uuid4().hex[:14]}"


def new_item_id() -> str:
    return f"lpi_{uuid.uuid4().hex[:12]}"


def new_artifact_id() -> str:
    return f"loa_{uuid.uuid4().hex[:14]}"


class EvidenceRef(BaseModel):
    ref: str
    kind: EvidenceKind = "GENERAL_EXTERNAL_EVIDENCE"
    label: str = ""
    url: Optional[str] = None
    # V2.6.1 — public presentation + currentness (optional, backward compatible)
    display_name: str = ""
    status: EvidenceStatus = "active"
    source_type: str = ""  # e.g. user_file — descriptive, not a domain router
    source_id: str = ""


class PlanItem(BaseModel):
    id: str = Field(default_factory=new_item_id)
    title: str
    description: str = ""
    due_date: Optional[str] = None  # YYYY-MM-DD
    order: int = 0
    status: ItemStatus = "not_started"
    artifact_refs: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    # Lightweight assumption provenance — NOT a cognitive graph
    origin: ItemOrigin = "generated"
    meta: Dict[str, Any] = Field(default_factory=dict)


# How precisely somebody actually said when.
#
#   exact     a day they gave: "entro il 20 novembre"
#   window    a period with an end: "quest'anno", "prima dell'estate"
#   horizon   a distance without edges: "nei prossimi mesi"
#   none      they did not say
TargetPrecision = Literal["exact", "window", "horizon", "none"]


class TemporalTarget(BaseModel):
    """
    When something is meant to happen, at the precision it was said.

    The model used to have two grades: a day, or silence. Somebody said "vorrei
    prendere la patente quest'anno" and, with nowhere to put a period, the
    reasoning wrote a day — 24 June 2027, six months past the year they had
    named. Home then counted down to it: "tra 299g". Nobody had said June, and
    nobody had said 2027.

    So the grades exist now, and the one thing the code guarantees is that they
    never silently improve: a window keeps its own words and its own end, and
    `target_date` — which everything downstream reads as a deadline — is filled
    only when somebody actually gave a day.
    """

    precision: TargetPrecision = "none"
    # Their words, kept as said. This is what a person should read back.
    as_said: str = Field(default="", max_length=120)
    # The edges, when there are any. For "quest'anno" the far edge is the last
    # day of this year: derived, not invented, and never presented as the day
    # the thing will happen.
    earliest: Optional[str] = None
    latest: Optional[str] = None

    @model_validator(mode="after")
    def _coherent(self) -> "TemporalTarget":
        """
        The grades have to mean what they say.

        Not stopping the invention of a date was only half the job: the first
        real run came back `precision: none` for somebody who had said
        "quest'anno". No date, which was the point — and no constraint either,
        which was not. They had given real temporal information and ORA had
        dropped it.

        `none` is the claim that nothing was said. It cannot be made while
        holding an edge or their words, and a grade that carries edges cannot
        call itself nothing. Nothing here reads what those words *mean*: it
        only refuses the two combinations that contradict themselves.
        """
        has_edges = bool(self.earliest or self.latest)
        has_words = bool((self.as_said or "").strip())

        if self.precision == "none" and (has_edges or has_words):
            # Something was said after all. Which grade it is depends on
            # whether it has a boundary, and that much is structural.
            self.precision = "window" if has_edges else "horizon"
        elif self.precision == "exact" and not self.earliest:
            # A day, without a day.
            self.precision = "window" if self.latest else "horizon"
        elif self.precision == "window" and not has_edges:
            # A period with no boundary is a distance.
            self.precision = "horizon"
        return self

    @property
    def exact_day(self) -> Optional[str]:
        """The only case where a single date is a truthful answer."""
        return self.earliest if self.precision == "exact" else None

    @property
    def is_stated(self) -> bool:
        """Whether the person said anything about when at all."""
        return self.precision != "none"


class LifeOsPlan(BaseModel):
    """Generic plan — no domain fields (no exam_subject, dog_breed, …)."""

    id: str = Field(default_factory=new_plan_id)
    user_id: str
    goal_id: Optional[str] = None
    summary: str
    desired_outcome: str = ""
    # An exact day, and nothing else. Everything downstream treats this as a
    # deadline — ranking, countdowns, the calendar — so anything vaguer than a
    # day belongs in `target` and is kept out of here.
    target_date: Optional[str] = None
    target: TemporalTarget = Field(default_factory=TemporalTarget)
    status: PlanStatus = "active"
    strategy: str = ""
    constraints: List[str] = Field(default_factory=list)
    items: List[PlanItem] = Field(default_factory=list)
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    conversation_session_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    meta: Dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def public(self) -> Dict[str, Any]:
        return self.model_dump()

    def progress_ratio(self) -> float:
        if not self.items:
            return 0.0
        done = sum(1 for i in self.items if i.status == "completed")
        return round(done / max(1, len(self.items)), 3)

    def next_open_item(self) -> Optional[PlanItem]:
        ordered = sorted(self.items, key=lambda x: (x.order, x.due_date or ""))
        for it in ordered:
            if it.status in ("not_started", "in_progress"):
                return it
        return None

    def today_items(self, today: Optional[str] = None) -> List[PlanItem]:
        day = today or datetime.now(timezone.utc).date().isoformat()
        return [
            i
            for i in self.items
            if (i.due_date or "")[:10] == day
            and i.status in ("not_started", "in_progress")
        ]


class LifeOsArtifact(BaseModel):
    id: str = Field(default_factory=new_artifact_id)
    user_id: str
    type: ArtifactType
    title: str
    goal_id: Optional[str] = None
    plan_id: Optional[str] = None
    plan_item_id: Optional[str] = None
    content: Dict[str, Any] = Field(default_factory=dict)
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    evidence_quality: Dict[str, Any] = Field(default_factory=dict)
    status: ArtifactStatus = "ready"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def public(self) -> Dict[str, Any]:
        return self.model_dump()
