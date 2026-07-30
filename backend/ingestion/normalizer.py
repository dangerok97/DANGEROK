"""Normalizer — turns raw Google Calendar event dicts into the canonical
`CalendarEventNormalized` model. Fails soft with a clean error string
that the pipeline turns into `quarantined`.

We intentionally accept only a small, well-known subset of fields to
prevent stray data from entering ORA. Anything unknown is dropped.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .provenance import build_provenance
from .types import (
    SENSITIVITY_PERSONAL,
    SENSITIVITY_PUBLIC,
    CalendarEventNormalized,
    NormalizedField,
)


class NormalizationError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


_MAX_TITLE_LEN = 300
_MAX_DESC_LEN = 2000
_MAX_ATTENDEES = 50
_MAX_REMINDERS = 10


def _parse_google_time(field: Any) -> Optional[str]:
    """Return an ISO-8601 UTC string or None."""
    if not isinstance(field, dict):
        return None
    if "dateTime" in field and field["dateTime"]:
        try:
            dt = datetime.fromisoformat(field["dateTime"].replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            return None
    if "date" in field and field["date"]:
        return field["date"]  # YYYY-MM-DD for all-day events
    return None


def _is_all_day(start: Any, end: Any) -> bool:
    if isinstance(start, dict) and "date" in start and "dateTime" not in start:
        return True
    if isinstance(end, dict) and "date" in end and "dateTime" not in end:
        return True
    return False


def _compute_source_hash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _shrink(s: Optional[str], limit: int) -> Optional[str]:
    if s is None:
        return None
    if not isinstance(s, str):
        s = str(s)
    if len(s) > limit:
        return s[:limit] + "…"
    return s


class GoogleCalendarNormalizer:
    """Deterministic mapper Google Calendar JSON → CalendarEventNormalized."""

    def __init__(self, *, connector_id: str, connector_instance_id: str):
        self.connector_id = connector_id
        self.connector_instance_id = connector_instance_id

    def normalize(
        self,
        *,
        raw: Dict[str, Any],
        calendar_id: str,
        calendar_name: Optional[str] = None,
    ) -> CalendarEventNormalized:
        if not isinstance(raw, dict):
            raise NormalizationError("payload_not_object", "expected a JSON object")

        ext_id = raw.get("id")
        if not ext_id or not isinstance(ext_id, str):
            raise NormalizationError("missing_id")

        status = raw.get("status") or "confirmed"
        if status not in ("confirmed", "tentative", "cancelled"):
            status = "confirmed"

        start_field = raw.get("start")
        end_field = raw.get("end")

        starts_at_iso = _parse_google_time(start_field)
        ends_at_iso = _parse_google_time(end_field)

        if status != "cancelled" and not starts_at_iso and not ends_at_iso:
            # cancelled events may legitimately arrive without times
            raise NormalizationError("missing_start_end")

        tz = None
        if isinstance(start_field, dict):
            tz = start_field.get("timeZone")

        all_day = _is_all_day(start_field, end_field)

        source_updated_at = raw.get("updated") or raw.get("etag")

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

        title_val = _shrink(raw.get("summary"), _MAX_TITLE_LEN)
        title_field = NormalizedField(value=title_val, provenance=_prov("summary"), sensitivity=SENSITIVITY_PERSONAL) if title_val else None

        desc_val = _shrink(raw.get("description"), _MAX_DESC_LEN)
        desc_field = NormalizedField(value=desc_val, provenance=_prov("description"), sensitivity=SENSITIVITY_PERSONAL) if desc_val else None

        loc_val = _shrink(raw.get("location"), _MAX_TITLE_LEN)
        loc_field = NormalizedField(value=loc_val, provenance=_prov("location", SENSITIVITY_PERSONAL), sensitivity=SENSITIVITY_PERSONAL) if loc_val else None

        organizer_raw = raw.get("organizer") or {}
        organizer_val = organizer_raw.get("email") or organizer_raw.get("displayName")
        organizer_field = NormalizedField(value=organizer_val, provenance=_prov("organizer"), sensitivity=SENSITIVITY_PERSONAL) if organizer_val else None

        attendees_raw = raw.get("attendees") or []
        if not isinstance(attendees_raw, list):
            attendees_raw = []
        attendees_raw = attendees_raw[:_MAX_ATTENDEES]
        attendees: List[NormalizedField] = []
        for a in attendees_raw:
            if not isinstance(a, dict):
                continue
            v = a.get("email") or a.get("displayName")
            if v:
                attendees.append(NormalizedField(
                    value=v,
                    provenance=_prov("attendees[]"),
                    sensitivity=SENSITIVITY_PERSONAL,
                ))

        recurrence_rules = raw.get("recurrence") or []
        rrule = None
        if isinstance(recurrence_rules, list) and recurrence_rules:
            for r in recurrence_rules:
                if isinstance(r, str) and r.startswith("RRULE:"):
                    rrule = r
                    break

        starts_at_field = NormalizedField(value=starts_at_iso, provenance=_prov("start"), sensitivity=SENSITIVITY_PUBLIC) if starts_at_iso else None
        ends_at_field = NormalizedField(value=ends_at_iso, provenance=_prov("end"), sensitivity=SENSITIVITY_PUBLIC) if ends_at_iso else None

        reminders_out: List[Dict[str, Any]] = []
        rem = raw.get("reminders") or {}
        if isinstance(rem, dict):
            overrides = rem.get("overrides")
            if isinstance(overrides, list):
                for r in overrides[:_MAX_REMINDERS]:
                    if isinstance(r, dict):
                        reminders_out.append({
                            "method": r.get("method"),
                            "minutes": r.get("minutes"),
                        })

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
            calendar_id=calendar_id,
            calendar_name=calendar_name,
            title=title_field,
            description=desc_field,
            starts_at=starts_at_field,
            ends_at=ends_at_field,
            timezone=tz,
            all_day=all_day,
            location=loc_field,
            organizer=organizer_field,
            attendees=attendees,
            recurrence_rule=rrule,
            recurrence_instance_id=raw.get("recurringEventId"),
            status=status,
            visibility=raw.get("visibility"),
            reminders=reminders_out,
            source_updated_at=source_updated_at,
            source_hash=_compute_source_hash(payload_for_hash),
        )
