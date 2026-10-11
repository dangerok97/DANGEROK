"""Shared source selection and date interpretation for local calendar reads."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


async def connected_calendar_instances(db, user_id: str) -> list[dict]:
    return await db.connector_instances.find({
        "user_id": user_id,
        "status": {"$in": ["connected", "syncing"]},
    }, {"_id": 0, "id": 1, "connector_id": 1, "selected_resource_ids": 1,
        "last_sync_at": 1, "metadata": 1}).to_list(length=200)


def selected_calendar_source(attrs: dict, instances: list[dict]) -> bool:
    """A connection to one account never admits another account's old mirror."""
    connector = str(attrs.get("connector_id") or "")
    if not connector or attrs.get("kind") == "home_manual":
        return True
    matches = [row for row in instances if row.get("connector_id") == connector]
    instance_id = str(attrs.get("connector_instance_id") or "")
    if instance_id:
        matches = [row for row in matches if str(row.get("id") or "") == instance_id]
    elif len(matches) != 1:
        # Historical rows without an instance handle are unambiguous only
        # while exactly one account for this provider is connected.
        return False
    if not matches:
        return False
    selected = set(matches[0].get("selected_resource_ids") or [])
    calendar_id = str(attrs.get("calendar_id") or "")
    if selected:
        return calendar_id in selected
    account = str((matches[0].get("metadata") or {}).get("account_email") or "")
    if connector == "calendar_google" and account and calendar_id:
        # Empty selection uses the primary calendar in the sync service.
        return calendar_id in {"primary", account}
    return True


def calendar_source_key(attrs: dict) -> tuple[str, str, str, str]:
    return tuple(str(attrs.get(key) or "") for key in (
        "connector_id", "connector_instance_id", "calendar_id", "external_event_id",
    ))


def calendar_times_in_window(attrs: dict, first: datetime, end: datetime) -> dict | None:
    """All-day dates stay dates; timed events move to the viewer's timezone."""
    all_day = bool(attrs.get("all_day"))

    def moment(value):
        raw = str(value)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if all_day:
            if len(raw) > 10 and parsed.tzinfo:
                source_zone = ZoneInfo(attrs.get("timezone") or str(first.tzinfo))
                parsed = parsed.astimezone(source_zone)
            return datetime.combine(parsed.date(), datetime.min.time(), tzinfo=first.tzinfo)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(attrs.get("timezone") or str(first.tzinfo)))
        return parsed.astimezone(first.tzinfo)

    try:
        start = moment(attrs.get("starts_at"))
        if not first <= start < end:
            return None
        finish = moment(attrs["ends_at"]) if attrs.get("ends_at") else None
        if all_day and finish is None:
            finish = start + timedelta(days=1)
    except (ValueError, TypeError, KeyError):
        return None
    return {**attrs, "starts_at": start.isoformat(),
            "ends_at": finish.isoformat() if finish else None}
