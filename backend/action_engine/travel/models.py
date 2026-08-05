"""Travel Project models — period, destination, transport, bookings, calendar, maps."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

DEFAULT_TZ = "Europe/Rome"

ProjectStatus = Literal[
    "draft",
    "awaiting_confirmation",
    "active",
    "paused",
    "completed",
    "cancelled",
]

Transport = Literal["train", "plane", "car", "other"]
BookingStatus = Literal["all", "partial", "none"]
CalendarEventKind = Literal["vacation_block", "outbound", "return"]
TravelPhase = Literal[
    "upcoming",
    "days_until",
    "departure_day",
    "during",
    "welcome_back",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def make_idempotency_key(
    user_id: str,
    source_priority_id: Optional[str],
    destination: str,
    start_date: str,
    end_date: str,
) -> str:
    raw = (
        f"{user_id}|{source_priority_id or ''}|"
        f"{destination.strip().lower()}|{start_date[:10]}|{end_date[:10]}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class TravelCalendarEvent(BaseModel):
    id: str = Field(default_factory=lambda: _uid("tce"))
    kind: CalendarEventKind
    title: str = ""
    starts_at: str  # UTC ISO (date or datetime)
    ends_at: str
    all_day: bool = False
    google_event_id: Optional[str] = None
    google_calendar_id: Optional[str] = None
    google_sync_status: Optional[str] = None
    life_node_id: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class MapsInfo(BaseModel):
    deep_link: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    distance_km: Optional[float] = None
    duration_minutes: Optional[int] = None
    duration_label: Optional[str] = None
    estimate_source: str = "unavailable"  # haversine|unavailable|heuristic
    suggested_stops: List[Dict[str, Any]] = Field(default_factory=list)
    tolls_note: Optional[str] = None
    honesty: str = ""


class PrepItem(BaseModel):
    id: str
    label: str
    category: str  # luggage|docs|car|fuel|pets|medicine|charger|other
    optional: bool = True


class TravelProject(BaseModel):
    id: str = Field(default_factory=lambda: _uid("trp"))
    user_id: str
    status: ProjectStatus = "draft"
    title: str = ""
    destination: Optional[str] = None
    departure_place: Optional[str] = None
    start_date: Optional[str] = None  # local YYYY-MM-DD or UTC ISO
    end_date: Optional[str] = None
    timezone: str = DEFAULT_TZ
    transport: Optional[Transport] = None
    bookings: Optional[BookingStatus] = None
    companions: Optional[int] = None  # 1 = solo
    companion_names: List[str] = Field(default_factory=list)
    calendar_sync: bool = False
    calendar_events: List[TravelCalendarEvent] = Field(default_factory=list)
    maps: MapsInfo = Field(default_factory=MapsInfo)
    prep_items: List[PrepItem] = Field(default_factory=list)
    document_ids: List[str] = Field(default_factory=list)
    # Future modules — structure only, no fake UI
    photo_ids: List[str] = Field(default_factory=list)
    expense_ids: List[str] = Field(default_factory=list)
    email_search: Dict[str, Any] = Field(
        default_factory=lambda: {"status": "not_implemented", "hook": "email_auto_find"}
    )
    weather: Dict[str, Any] = Field(
        default_factory=lambda: {"status": "unavailable", "reason": "no_weather_api"}
    )
    departure_advice: Dict[str, Any] = Field(default_factory=dict)
    source_priority_id: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    action_session_id: Optional[str] = None
    project_id: Optional[str] = None
    brain_node_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    google_sync: Dict[str, Any] = Field(default_factory=dict)
    preview: Dict[str, Any] = Field(default_factory=dict)
    answers: Dict[str, Any] = Field(default_factory=dict)
    phase: TravelPhase = "upcoming"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    confirmed_at: Optional[str] = None
    cancelled_at: Optional[str] = None

    def compute_phase(self, today: Optional[str] = None) -> TravelPhase:
        from datetime import date as date_cls

        t = today or datetime.now(timezone.utc).date().isoformat()
        try:
            td = date_cls.fromisoformat(t[:10])
            sd = date_cls.fromisoformat((self.start_date or "")[:10]) if self.start_date else None
            ed = date_cls.fromisoformat((self.end_date or "")[:10]) if self.end_date else None
        except Exception:
            return "upcoming"
        if not sd:
            return "upcoming"
        if ed and td > ed:
            return "welcome_back"
        if ed and sd <= td <= ed:
            if td == sd:
                return "departure_day"
            return "during"
        if td == sd:
            return "departure_day"
        days = (sd - td).days
        if 0 < days <= 14:
            return "days_until"
        return "upcoming"

    def public(self) -> Dict[str, Any]:
        phase = self.compute_phase()
        days_until = None
        if self.start_date:
            try:
                from datetime import date as date_cls

                sd = date_cls.fromisoformat(self.start_date[:10])
                days_until = (sd - datetime.now(timezone.utc).date()).days
            except Exception:
                pass
        return {
            "id": self.id,
            "user_id": self.user_id,
            "status": self.status,
            "title": self.title or f"Vacanza: {self.destination or 'viaggio'}",
            "destination": self.destination,
            "departure_place": self.departure_place,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "timezone": self.timezone,
            "transport": self.transport,
            "bookings": self.bookings,
            "companions": self.companions,
            "companion_names": self.companion_names,
            "calendar_sync": self.calendar_sync,
            "calendar_events": [e.model_dump() for e in self.calendar_events],
            "maps": self.maps.model_dump(),
            "prep_items": [p.model_dump() for p in self.prep_items],
            "document_ids": self.document_ids,
            "photo_ids": self.photo_ids,
            "expense_ids": self.expense_ids,
            "email_search": self.email_search,
            "weather": self.weather,
            "departure_advice": self.departure_advice,
            "source_priority_id": self.source_priority_id,
            "action_session_id": self.action_session_id,
            "project_id": self.project_id,
            "brain_node_id": self.brain_node_id,
            "idempotency_key": self.idempotency_key,
            "google_sync": self.google_sync,
            "preview": self.preview,
            "phase": phase,
            "days_until": days_until,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "confirmed_at": self.confirmed_at,
        }


class TravelModifyBody(BaseModel):
    destination: Optional[str] = None
    departure_place: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    transport: Optional[Transport] = None
    bookings: Optional[BookingStatus] = None
    companions: Optional[int] = None
    calendar_sync: Optional[bool] = None
    document_ids: Optional[List[str]] = None


class ConfirmTravelBody(BaseModel):
    force: bool = False
