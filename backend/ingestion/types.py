"""Enums, constants, canonical dataclasses used across ingestion."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------
# Ingestion statuses
# --------------------------------------------------------------------
INGESTION_STATUS_RECEIVED = "received"
INGESTION_STATUS_NORMALIZED = "normalized"
INGESTION_STATUS_DEDUPLICATED = "deduplicated"
INGESTION_STATUS_PROCESSED = "processed"
INGESTION_STATUS_SKIPPED = "skipped"
INGESTION_STATUS_FAILED = "failed"
INGESTION_STATUS_QUARANTINED = "quarantined"
INGESTION_STATUS_SUPERSEDED = "superseded"

INGESTION_STATUSES = frozenset({
    INGESTION_STATUS_RECEIVED,
    INGESTION_STATUS_NORMALIZED,
    INGESTION_STATUS_DEDUPLICATED,
    INGESTION_STATUS_PROCESSED,
    INGESTION_STATUS_SKIPPED,
    INGESTION_STATUS_FAILED,
    INGESTION_STATUS_QUARANTINED,
    INGESTION_STATUS_SUPERSEDED,
})


# --------------------------------------------------------------------
# Sensitivity classes
# --------------------------------------------------------------------
SENSITIVITY_PUBLIC = "public"
SENSITIVITY_PERSONAL = "personal"
SENSITIVITY_SENSITIVE = "sensitive"
SENSITIVITY_HIGHLY_SENSITIVE = "highly_sensitive"


# --------------------------------------------------------------------
# Canonical CalendarEventNormalized (calendar-specific but lives here
# so `ingestion` is the single owner of canonical data models).
# --------------------------------------------------------------------
@dataclass
class NormalizedField:
    """A single field with its own provenance + sensitivity."""
    value: Any
    provenance: Dict[str, Any] = field(default_factory=dict)
    sensitivity: str = SENSITIVITY_PERSONAL


@dataclass
class CalendarEventNormalized:
    external_event_id: str
    calendar_id: str
    calendar_name: Optional[str]
    title: Optional[NormalizedField]
    description: Optional[NormalizedField]
    starts_at: Optional[NormalizedField]
    ends_at: Optional[NormalizedField]
    timezone: Optional[str]
    all_day: bool
    location: Optional[NormalizedField]
    organizer: Optional[NormalizedField]
    attendees: List[NormalizedField]
    recurrence_rule: Optional[str]
    recurrence_instance_id: Optional[str]
    status: str  # confirmed | tentative | cancelled
    visibility: Optional[str]
    reminders: List[Dict[str, Any]]
    source_updated_at: Optional[str]
    source_hash: str

    def to_dict(self) -> Dict[str, Any]:
        def _f(nf: Optional[NormalizedField]) -> Optional[Dict[str, Any]]:
            if nf is None:
                return None
            return {"value": nf.value, "provenance": nf.provenance, "sensitivity": nf.sensitivity}

        return {
            "external_event_id": self.external_event_id,
            "calendar_id": self.calendar_id,
            "calendar_name": self.calendar_name,
            "title": _f(self.title),
            "description": _f(self.description),
            "starts_at": _f(self.starts_at),
            "ends_at": _f(self.ends_at),
            "timezone": self.timezone,
            "all_day": self.all_day,
            "location": _f(self.location),
            "organizer": _f(self.organizer),
            "attendees": [_f(a) for a in self.attendees],
            "recurrence_rule": self.recurrence_rule,
            "recurrence_instance_id": self.recurrence_instance_id,
            "status": self.status,
            "visibility": self.visibility,
            "reminders": self.reminders,
            "source_updated_at": self.source_updated_at,
            "source_hash": self.source_hash,
        }


# --------------------------------------------------------------------
# Pipeline output types
# --------------------------------------------------------------------
@dataclass
class RoutedEntity:
    kind: str  # "node" | "knowledge" | "decision" | "auto_link"
    id: str
    action: str  # "created" | "updated" | "unchanged"


@dataclass
class RoutingActions:
    entities: List[RoutedEntity] = field(default_factory=list)
    skipped_reasons: List[str] = field(default_factory=list)

    def add(self, kind: str, id: str, action: str) -> None:
        self.entities.append(RoutedEntity(kind=kind, id=id, action=action))


@dataclass
class IngestionOutcome:
    event_id: str
    status: str
    external_id: str
    external_version: Optional[str]
    routing: RoutingActions = field(default_factory=RoutingActions)
    error_code: Optional[str] = None
    superseded_event_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "status": self.status,
            "external_id": self.external_id,
            "external_version": self.external_version,
            "error_code": self.error_code,
            "superseded_event_id": self.superseded_event_id,
            "routing": {
                "entities": [e.__dict__ for e in self.routing.entities],
                "skipped_reasons": list(self.routing.skipped_reasons),
            },
        }
