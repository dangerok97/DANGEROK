"""AI Core capabilities wrapping Calendar (V2.8.6b).

Calendar is a capability, not a second brain: this module wraps the
V2.8.6a-hardened services (`CalendarGateway`/`InternalCalendarProvider`,
`GoogleCalendarSyncService`, `timezone_service`, `connectors.google_calendar
.consent`) — nothing here talks to Google directly, and nothing here decides
whether a user statement "means" a calendar event. That decision stays with
the AI; this module only guarantees ownership, consent, idempotency, bounded
output and failure honesty once the AI has decided to read or write.

Canonical ref: an AI-managed calendar item is always `calendar:{draft_id}`
(draft_id prefixed `ced_`) — the same ref shape already emitted by the
Context Broker's `_calendar` source and already a recognized Context Graph
prefix. Read-only ingested Google events (`ingestion_events`, items the user
already had in Google before ORA touched anything) are surfaced for
conflict-awareness only, with no canonical ref — they are not directly
actionable via these capabilities (V2.8.6b canonical-ref policy, see
docs/ARCHITECTURE.md).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from conversation_engine.ai_core.models import Observation
from connectors.google_calendar.consent import (
    CapabilityDisabled,
    CapabilityUnknown,
    ConsentDenied,
    calendar_consent_granted,
    require_calendar_consent,
)
from documents.intelligence.calendar_adapter import CalendarGateway
from documents.intelligence.google_sync import (
    GoogleCalendarAPIError,
    GoogleCalendarSyncService,
)
from timezone_service import is_valid_iana_timezone, resolve_user_timezone

logger = logging.getLogger("ora.ai_core.calendar_caps")

_MAX_TITLE = 200
_MAX_LOCATION = 300
_MAX_DESCRIPTION = 800
_MAX_WINDOW_DAYS = 60
_DEFAULT_WINDOW_DAYS = 7
_MAX_EVENTS_RETURNED = 20


def _fail(name: str, code: str, detail: str = "") -> Observation:
    return Observation(
        kind="tool",
        name=name,
        status="error",
        payload={"status": "error", "failure_kind": code, "detail": detail[:200]},
    )


def _ref(draft_id: str) -> str:
    return f"calendar:{draft_id}"


def _strip_ref(value: Optional[str]) -> str:
    v = str(value or "").strip()
    return v[len("calendar:") :] if v.startswith("calendar:") else v


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def _sync_service(db) -> GoogleCalendarSyncService:
    # `deps` pulls in full app wiring — imported lazily here, same pattern
    # already used at the other GoogleCalendarSyncService call site
    # (documents/intelligence/service.py).
    from deps import get_google_calendar_service

    return GoogleCalendarSyncService(db=db, google_calendar_service=get_google_calendar_service())


async def _active_instance_id(sync: GoogleCalendarSyncService, uid: str) -> str:
    """Consent is granted per connector-instance (multi-account support),
    not just a wildcard — resolve the user's active instance so the consent
    check matches what OAuth actually granted, falling back to the wildcard
    default when no instance is connected yet (is_granted() still checks the
    wildcard tier too, so a generic grant is not lost by passing this)."""
    from permissions.models import INSTANCE_WILDCARD

    try:
        inst = await sync._instance_for_user(uid)
    except Exception:
        inst = None
    return str(inst["id"]) if inst else INSTANCE_WILDCARD


async def get_calendar_events(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """READ_ONLY. Local storage only — never a live Google call per turn."""
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("get_calendar_events", "NOT_CONFIGURED")

    time_min = _parse_dt(arguments.get("time_min"))
    time_max = _parse_dt(arguments.get("time_max"))
    if not time_min:
        # Default to a UTC-aware "now" — a naive local "now" would silently
        # break the lexicographic string-range comparison below against
        # stored ISO strings that (like every event this module writes)
        # carry an explicit UTC offset, hiding real events whenever the
        # server's local timezone offset isn't exactly zero.
        time_min = datetime.now(time_max.tzinfo if time_max and time_max.tzinfo else timezone.utc)
    if not time_max:
        from datetime import timedelta

        time_max = time_min + timedelta(days=_DEFAULT_WINDOW_DAYS)
    if (time_max - time_min).days > _MAX_WINDOW_DAYS:
        from datetime import timedelta

        time_max = time_min + timedelta(days=_MAX_WINDOW_DAYS)
    if time_max <= time_min:
        return _fail("get_calendar_events", "INVALID_WINDOW", "time_max must be after time_min")

    tmin_iso, tmax_iso = time_min.isoformat(), time_max.isoformat()

    drafts_cur = db.calendar_event_drafts.find(
        {
            "user_id": uid,
            "status": {"$ne": "cancelled"},
            "start_datetime": {"$gte": tmin_iso, "$lt": tmax_iso},
        },
        {
            "_id": 0, "id": 1, "title": 1, "start_datetime": 1, "end_datetime": 1,
            "timezone": 1, "all_day": 1, "location": 1, "status": 1,
            "sync_status": 1, "provider": 1,
        },
    ).sort("start_datetime", 1).limit(_MAX_EVENTS_RETURNED)
    drafts = await drafts_cur.to_list(_MAX_EVENTS_RETURNED)

    items = [
        {
            "calendar_ref": _ref(d["id"]),
            "source": "ora_managed",
            "title": d.get("title"),
            "start_datetime": d.get("start_datetime"),
            "end_datetime": d.get("end_datetime"),
            "timezone": d.get("timezone"),
            "all_day": bool(d.get("all_day")),
            "location": d.get("location"),
            "status": d.get("status"),
            "sync_status": d.get("sync_status"),
        }
        for d in drafts
    ]

    # Google-imported events are gated on calendar.read consent — a local
    # cache/mirror must never become a bypass of a revoked connector. This
    # never blocks the read as a whole: ORA-managed events above are the
    # user's own local record and stay visible regardless of Google
    # connection state (their provenance is already explicit as
    # "ora_managed", never presented as current Google state).
    sync = await _sync_service(db)
    instance_id = await _active_instance_id(sync, uid)
    google_read_granted = await calendar_consent_granted(
        db, user_id=uid, write=False, connector_instance_id=instance_id,
    )

    remaining = max(0, _MAX_EVENTS_RETURNED - len(items))
    if remaining and google_read_granted:
        ingested_cur = db.ingestion_events.find(
            {
                "user_id": uid,
                "connector_id": "calendar_google",
                "source_status": {"$ne": "detached"},
                "normalized_payload.starts_at": {"$gte": tmin_iso, "$lt": tmax_iso},
            },
            {
                "_id": 0,
                "normalized_payload.title": 1,
                "normalized_payload.starts_at": 1,
                "normalized_payload.ends_at": 1,
                "normalized_payload.timezone": 1,
                "normalized_payload.all_day": 1,
                "normalized_payload.location": 1,
            },
        ).sort("normalized_payload.starts_at", 1).limit(remaining)
        for e in await ingested_cur.to_list(remaining):
            p = e.get("normalized_payload") or {}
            items.append({
                "calendar_ref": None,  # read-only external mirror, not actionable
                "source": "google_external",
                "title": p.get("title"),
                "start_datetime": p.get("starts_at"),
                "end_datetime": p.get("ends_at"),
                "timezone": p.get("timezone"),
                "all_day": bool(p.get("all_day")),
                "location": p.get("location"),
                "status": "confirmed",
                "sync_status": "synced",
            })

    items.sort(key=lambda x: x.get("start_datetime") or "")

    # Bounded, deterministic overlap detection — evidence only; the AI
    # decides whether a conflict matters, this never blocks/asks by itself.
    conflicts: List[List[int]] = []
    for i in range(len(items)):
        a_start, a_end = _parse_dt(items[i]["start_datetime"]), _parse_dt(items[i]["end_datetime"])
        if not a_start or not a_end:
            continue
        for j in range(i + 1, len(items)):
            b_start, b_end = _parse_dt(items[j]["start_datetime"]), _parse_dt(items[j]["end_datetime"])
            if not b_start or not b_end:
                continue
            if a_start < b_end and b_start < a_end:
                conflicts.append([i, j])

    return Observation(
        kind="tool",
        name="get_calendar_events",
        status="ok",
        payload={
            "status": "ok",
            "window": {"time_min": tmin_iso, "time_max": tmax_iso},
            "events": items,
            "conflict_index_pairs": conflicts[:10],
            "truncated": len(items) >= _MAX_EVENTS_RETURNED,
            "google_events_included": google_read_granted,
            "google_events_note": (
                None if google_read_granted else
                "Google Calendar read access is not authorized, so previously "
                "imported Google events are not included here — only ORA's own "
                "locally-managed events. Do not claim the calendar is empty of "
                "Google commitments; explain honestly that Google read access "
                "would need to be reauthorized to see them again."
            ),
        },
        provenance=[it["calendar_ref"] for it in items if it.get("calendar_ref")],
    )


async def create_calendar_event(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """REVERSIBLE_WRITE. The AI is expected to have already proposed this via
    response_mode=act and received explicit user confirmation before calling
    this — the runtime does not re-litigate that; it only guarantees consent,
    idempotency and failure honesty."""
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    epoch = runtime.get("reasoning_epoch") or ""
    if not uid or db is None:
        return _fail("create_calendar_event", "NOT_CONFIGURED")

    title = str(arguments.get("title") or "").strip()[:_MAX_TITLE]
    start = arguments.get("start_datetime")
    if not title or not start or not _parse_dt(start):
        return _fail("create_calendar_event", "INVALID_INPUT", "title/start_datetime required")
    end = arguments.get("end_datetime")
    duration_minutes = arguments.get("duration_minutes")
    if not end and duration_minutes:
        from datetime import timedelta

        start_dt = _parse_dt(start)
        try:
            end = (start_dt + timedelta(minutes=float(duration_minutes))).isoformat()
        except (TypeError, ValueError):
            end = None
    if end and _parse_dt(end) and _parse_dt(start) and _parse_dt(end) <= _parse_dt(start):
        return _fail("create_calendar_event", "INVALID_INPUT", "end_datetime must be after start")

    tz = arguments.get("timezone")
    if tz and not is_valid_iana_timezone(str(tz)):
        tz = None
    tz_authority = "user_stated"
    if not tz:
        resolved = await resolve_user_timezone(db, uid)
        tz = resolved.tz_name
        tz_authority = resolved.authority

    sync = await _sync_service(db)
    instance_id = await _active_instance_id(sync, uid)
    try:
        await require_calendar_consent(db, user_id=uid, write=True, connector_instance_id=instance_id)
    except ConsentDenied:
        return Observation(
            kind="tool", name="create_calendar_event", status="consent_required",
            payload={
                "status": "consent_required",
                "reason": (
                    "Calendar write consent is not granted. Explain honestly that "
                    "the user needs to connect/authorize Calendar before ORA can "
                    "create this on Google — never claim it was created."
                ),
            },
        )
    except (CapabilityDisabled, CapabilityUnknown):
        return _fail("create_calendar_event", "CAPABILITY_UNAVAILABLE")

    candidate = {
        "id": f"epoch:{epoch}" if epoch else f"noepoch:{title[:40]}:{start}",
        "source_document_id": "ai_core_conversation",
        "title": title,
        "description": str(arguments.get("description") or "")[:_MAX_DESCRIPTION],
        "start_datetime": start,
        "end_datetime": end,
        "timezone": tz,
        "all_day": bool(arguments.get("all_day", False)),
    }
    location = arguments.get("location")
    if location:
        candidate["venue_name"] = str(location)[:_MAX_LOCATION]

    gateway = CalendarGateway(db)
    draft = await gateway.get("internal").create_from_candidate(
        user_id=uid, candidate=candidate,
    )
    draft_id = draft["id"]

    try:
        synced = await sync.sync_draft(user_id=uid, draft_id=draft_id)
    except GoogleCalendarAPIError as e:
        return Observation(
            kind="tool", name="create_calendar_event", status="partial",
            payload={
                "status": "partial",
                "calendar_ref": _ref(draft_id),
                "reason": (
                    "Saved locally as ORA's own record of the commitment, but Google "
                    "Calendar sync failed. Do not claim it is on the user's Google "
                    "Calendar — only that it is recorded and can be retried."
                ),
                "failure_kind": f"google_http_{e.status_code}",
                "timezone": {"tz_name": tz, "authority": tz_authority},
            },
            provenance=[_ref(draft_id)],
        )
    except RuntimeError as e:
        return Observation(
            kind="tool", name="create_calendar_event", status="partial",
            payload={
                "status": "partial",
                "calendar_ref": _ref(draft_id),
                "reason": (
                    "Saved locally; Google Calendar is not connected, so it is not "
                    "yet on the user's Google Calendar. Never claim otherwise."
                ),
                "failure_kind": type(e).__name__,
                "timezone": {"tz_name": tz, "authority": tz_authority},
            },
            provenance=[_ref(draft_id)],
        )

    return Observation(
        kind="tool", name="create_calendar_event", status="ok",
        payload={
            "status": "ok",
            "operation": "created",
            "calendar_ref": _ref(draft_id),
            "google_event_id": synced.get("google_event_id"),
            "sync_status": synced.get("sync_status"),
            "timezone": {"tz_name": tz, "authority": tz_authority},
        },
        provenance=[_ref(draft_id)],
    )


async def update_calendar_event(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """REVERSIBLE_WRITE. Requires an explicit canonical ref — never fuzzy
    title-based selection. If the AI is unsure which event, it must ask
    rather than guess (governed at the prompt/reasoning level, not here)."""
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("update_calendar_event", "NOT_CONFIGURED")

    draft_id = _strip_ref(arguments.get("calendar_ref"))
    if not draft_id:
        return _fail("update_calendar_event", "INVALID_INPUT", "calendar_ref required")

    existing = await db.calendar_event_drafts.find_one(
        {"id": draft_id, "user_id": uid}, {"_id": 0, "id": 1, "status": 1},
    )
    if not existing:
        return Observation(
            kind="tool", name="update_calendar_event", status="not_found",
            payload={
                "status": "not_found",
                "reason": "No owned calendar event matches this ref. Ask, do not guess.",
            },
        )
    if existing.get("status") == "cancelled":
        # reschedule_draft() itself refuses a cancelled draft (raises before
        # any DB write), but that refusal isn't a type the AI can act on
        # honestly — reject explicitly here, before touching consent or
        # Google, so the AI gets a clear reason instead of a generic
        # failure. Never reactivate, never recreate, never pick another
        # event — the AI must ask the user what they actually want.
        return Observation(
            kind="tool", name="update_calendar_event", status="rejected",
            payload={
                "status": "rejected",
                "calendar_ref": _ref(draft_id),
                "failure_kind": "event_cancelled",
                "reason": (
                    "This calendar event is cancelled and cannot be rescheduled. "
                    "Do not claim it was moved. Do not silently reactivate or "
                    "recreate it — if the user wants this commitment back, ask "
                    "them or propose creating a new event instead."
                ),
            },
        )

    sync = await _sync_service(db)
    instance_id = await _active_instance_id(sync, uid)
    try:
        await require_calendar_consent(db, user_id=uid, write=True, connector_instance_id=instance_id)
    except ConsentDenied:
        return Observation(
            kind="tool", name="update_calendar_event", status="consent_required",
            payload={"status": "consent_required", "calendar_ref": _ref(draft_id)},
        )
    except (CapabilityDisabled, CapabilityUnknown):
        return _fail("update_calendar_event", "CAPABILITY_UNAVAILABLE")

    fields: Dict[str, Any] = {}
    for key in ("title", "start_datetime", "end_datetime", "location", "description"):
        if arguments.get(key) is not None:
            fields[key] = arguments[key]
    tz = arguments.get("timezone")
    if tz and is_valid_iana_timezone(str(tz)):
        fields["timezone"] = tz
    if not fields:
        return _fail("update_calendar_event", "INVALID_INPUT", "no supported field to update")

    try:
        updated = await sync.reschedule_draft(
            user_id=uid, draft_id=draft_id, fields=fields,
        )
    except (GoogleCalendarAPIError, RuntimeError) as e:
        # reschedule_draft() commits the local field patch unconditionally
        # before any Google-side step can raise — the new details are
        # already saved locally even though the Google push failed. Report
        # that honestly (partial, like create_calendar_event) rather than
        # implying nothing happened, which would be just as false a claim
        # in the other direction.
        return Observation(
            kind="tool", name="update_calendar_event", status="partial",
            payload={
                "status": "partial",
                "calendar_ref": _ref(draft_id),
                "reason": (
                    "The new details were saved locally, but the change was not "
                    "confirmed on Google Calendar. Only claim the local update — "
                    "never that Google Calendar itself was updated."
                ),
                "failure_kind": type(e).__name__,
            },
        )

    if updated.get("sync_status") not in ("synced", None):
        return Observation(
            kind="tool", name="update_calendar_event", status="partial",
            payload={
                "status": "partial",
                "calendar_ref": _ref(draft_id),
                "reason": (
                    "The new details were saved locally, but sync with Google "
                    "Calendar is not confirmed. Only claim the local update — "
                    "never that Google Calendar itself was updated."
                ),
            },
        )

    return Observation(
        kind="tool", name="update_calendar_event", status="ok",
        payload={
            "status": "ok",
            "operation": "updated",
            "calendar_ref": _ref(draft_id),
            "google_event_id": updated.get("google_event_id"),
            "sync_status": updated.get("sync_status"),
        },
        provenance=[_ref(draft_id)],
    )


async def cancel_calendar_event(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """REVERSIBLE_WRITE (local cancel is a status flip; Google-side deletion
    is best-effort). Always requires an explicit ref and consent."""
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("cancel_calendar_event", "NOT_CONFIGURED")

    draft_id = _strip_ref(arguments.get("calendar_ref"))
    if not draft_id:
        return _fail("cancel_calendar_event", "INVALID_INPUT", "calendar_ref required")

    existing = await db.calendar_event_drafts.find_one(
        {"id": draft_id, "user_id": uid}, {"_id": 0, "id": 1, "status": 1},
    )
    if not existing:
        return Observation(
            kind="tool", name="cancel_calendar_event", status="not_found",
            payload={"status": "not_found", "reason": "No owned calendar event matches this ref."},
        )
    if existing.get("status") == "cancelled":
        return Observation(
            kind="tool", name="cancel_calendar_event", status="ok",
            payload={"status": "ok", "operation": "already_cancelled", "calendar_ref": _ref(draft_id)},
            provenance=[_ref(draft_id)],
        )

    sync = await _sync_service(db)
    instance_id = await _active_instance_id(sync, uid)
    try:
        await require_calendar_consent(db, user_id=uid, write=True, connector_instance_id=instance_id)
    except ConsentDenied:
        return Observation(
            kind="tool", name="cancel_calendar_event", status="consent_required",
            payload={"status": "consent_required", "calendar_ref": _ref(draft_id)},
        )
    except (CapabilityDisabled, CapabilityUnknown):
        return _fail("cancel_calendar_event", "CAPABILITY_UNAVAILABLE")

    result = await sync.delete_remote(
        user_id=uid, draft_id=draft_id, also_delete_google=True,
    )
    if not result.get("ok"):
        return Observation(
            kind="tool", name="cancel_calendar_event", status="failed",
            payload={
                "status": "failed", "calendar_ref": _ref(draft_id),
                "reason": "Cancellation was not confirmed. Do not claim it was cancelled.",
            },
        )
    return Observation(
        kind="tool", name="cancel_calendar_event", status="ok",
        payload={
            "status": "ok", "operation": "cancelled", "calendar_ref": _ref(draft_id),
            "deleted_on_google": bool(result.get("deleted_google")),
        },
        provenance=[_ref(draft_id)],
    )
