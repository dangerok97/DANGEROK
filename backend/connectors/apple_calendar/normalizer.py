"""AppleCalendarNormalizer — turns raw EventKit event dicts (as posted
by the mobile client) into the canonical `CalendarEventNormalized`
model shared with the Google Calendar connector.

Input contract (expected from the iOS client via expo-calendar):
    {
      "id": "<EKEvent.eventIdentifier>",     # REQUIRED, stable per-device
      "calendarId": "<EKCalendar.identifier>",
      "calendarTitle": "Personal",
      "title": "Standup",
      "notes": "…",                           # description
      "startDate": "2026-06-01T09:00:00Z",    # ISO 8601
      "endDate":   "2026-06-01T09:30:00Z",
      "allDay":    false,
      "location":  "…",
      "timeZone":  "Europe/Rome",
      "status":    "confirmed" | "tentative" | "cancelled" | "none",
      "organizer": "…",
      "attendees": ["a@x", "b@x"],            # emails or display names
      "recurrenceRule": "FREQ=WEEKLY;…",
      "lastModified": "2026-05-30T…Z"         # optional, for versioning
    }

We reuse the SAME `CalendarEventNormalized` dataclass that the Google
normalizer produces so downstream routing is 100% agnostic of the
provider. This is critical for cross-provider deduplication.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ingestion.normalizer import NormalizationError
from ingestion.provenance import build_provenance
from ingestion.types import (
    SENSITIVITY_PERSONAL,
    SENSITIVITY_PUBLIC,
    CalendarEventNormalized,
    NormalizedField,
)

_MAX_TITLE_LEN = 300
_MAX_DESC_LEN = 2000
_MAX_ATTENDEES = 50


_APPLE_STATUS_MAP = {
    "confirmed": "confirmed",
    "tentative": "tentative",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "none": "confirmed",
    None: "confirmed",
    "": "confirmed",
}


def _parse_apple_time(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, str):
        v = value.strip()
        # date-only "YYYY-MM-DD" is used for all-day events on iOS
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return v
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            return None
    return None


def _shrink(s: Optional[str], limit: int) -> Optional[str]:
    if s is None:
        return None
    if not isinstance(s, str):
        s = str(s)
        # Coerce non-strings defensively.
    if len(s) > limit:
        return s[:limit] + "…"
    return s


def _hash_payload(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class AppleCalendarNormalizer:
    """Deterministic mapper EventKit JSON → CalendarEventNormalized."""

    def __init__(self, *, connector_id: str, connector_instance_id: str):
        self.connector_id = connector_id
        self.connector_instance_id = connector_instance_id

    def normalize(
        self,
        *,
        raw: Dict[str, Any],
        default_calendar_id: Optional[str] = None,
        default_calendar_name: Optional[str] = None,
    ) -> CalendarEventNormalized:
        if not isinstance(raw, dict):
            raise NormalizationError("payload_not_object", "expected a JSON object")

        ext_id = raw.get("id") or raw.get("eventIdentifier")
        if not ext_id or not isinstance(ext_id, str):
            raise NormalizationError("missing_id")

        status = _APPLE_STATUS_MAP.get((raw.get("status") or "").lower() if isinstance(raw.get("status"), str) else raw.get("status"), "confirmed")

        starts_at_iso = _parse_apple_time(raw.get("startDate") or raw.get("start"))
        ends_at_iso = _parse_apple_time(raw.get("endDate") or raw.get("end"))

        if status != "cancelled" and not starts_at_iso and not ends_at_iso:
            raise NormalizationError("missing_start_end")

        tz = raw.get("timeZone") or raw.get("timezone")
        all_day = bool(raw.get("allDay") or raw.get("all_day"))
        # If startDate is a bare "YYYY-MM-DD" we treat it as all-day too.
        if not all_day and starts_at_iso and re.fullmatch(r"\d{4}-\d{2}-\d{2}", starts_at_iso):
            all_day = True

        source_updated_at = raw.get("lastModified") or raw.get("last_modified")

        calendar_id = raw.get("calendarId") or raw.get("calendar_id") or default_calendar_id or "apple:default"
        calendar_name = raw.get("calendarTitle") or raw.get("calendar_name") or default_calendar_name

        def _prov(field_path: str, sensitivity: str = SENSITIVITY_PERSONAL) -> Dict[str, Any]:
            return build_provenance(
                connector_id=self.connector_id,
                connector_instance_id=self.connector_instance_id,
                source_type=self.connector_id,
                source_id=ext_id,
                field_path=field_path,
                source_updated_at=source_updated_at,
                confidence=1.0,
                reliability_tier="official",
            )

        title_val = _shrink(raw.get("title"), _MAX_TITLE_LEN)
        title_field = NormalizedField(value=title_val, provenance=_prov("title"), sensitivity=SENSITIVITY_PERSONAL) if title_val else None

        desc_val = _shrink(raw.get("notes") or raw.get("description"), _MAX_DESC_LEN)
        desc_field = NormalizedField(value=desc_val, provenance=_prov("notes"), sensitivity=SENSITIVITY_PERSONAL) if desc_val else None

        loc_val = _shrink(raw.get("location"), _MAX_TITLE_LEN)
        loc_field = NormalizedField(value=loc_val, provenance=_prov("location"), sensitivity=SENSITIVITY_PERSONAL) if loc_val else None

        organizer_val = raw.get("organizer")
        if isinstance(organizer_val, dict):
            organizer_val = organizer_val.get("email") or organizer_val.get("name")
        organizer_field = NormalizedField(value=organizer_val, provenance=_prov("organizer"), sensitivity=SENSITIVITY_PERSONAL) if organizer_val else None

        attendees_raw = raw.get("attendees") or []
        if not isinstance(attendees_raw, list):
            attendees_raw = []
        attendees_raw = attendees_raw[:_MAX_ATTENDEES]
        attendees: List[NormalizedField] = []
        for a in attendees_raw:
            v = None
            if isinstance(a, str):
                v = a
            elif isinstance(a, dict):
                v = a.get("email") or a.get("name") or a.get("displayName")
            if v:
                attendees.append(NormalizedField(
                    value=str(v),
                    provenance=_prov("attendees[]"),
                    sensitivity=SENSITIVITY_PERSONAL,
                ))

        rrule = raw.get("recurrenceRule") or raw.get("recurrence_rule")
        if rrule and isinstance(rrule, list):
            rrule = next((r for r in rrule if isinstance(r, str)), None)
        if rrule and isinstance(rrule, str) and not rrule.startswith("RRULE:") and rrule.startswith("FREQ"):
            rrule = f"RRULE:{rrule}"

        starts_at_field = NormalizedField(value=starts_at_iso, provenance=_prov("startDate"), sensitivity=SENSITIVITY_PUBLIC) if starts_at_iso else None
        ends_at_field = NormalizedField(value=ends_at_iso, provenance=_prov("endDate"), sensitivity=SENSITIVITY_PUBLIC) if ends_at_iso else None

        payload_for_hash = {
            "id": ext_id,
            "status": status,
            "title": title_val,
            "starts_at": starts_at_iso,
            "ends_at": ends_at_iso,
            "location": loc_val,
            "description": desc_val,
            "attendees": [a.value for a in attendees],
            "recurrence_rule": rrule,
            "all_day": all_day,
            "timezone": tz,
            "source_updated_at": source_updated_at,
        }

        return CalendarEventNormalized(
            external_event_id=ext_id,
            calendar_id=str(calendar_id),
            calendar_name=str(calendar_name) if calendar_name else None,
            title=title_field,
            description=desc_field,
            starts_at=starts_at_field,
            ends_at=ends_at_field,
            timezone=tz,
            all_day=all_day,
            location=loc_field,
            organizer=organizer_field,
            attendees=attendees,
            recurrence_rule=rrule if isinstance(rrule, str) else None,
            recurrence_instance_id=raw.get("recurrenceInstanceId") or raw.get("recurring_event_id"),
            status=status,
            visibility=raw.get("availability") or raw.get("visibility"),
            reminders=[],
            source_updated_at=source_updated_at,
            source_hash=_hash_payload(payload_for_hash),
        )
