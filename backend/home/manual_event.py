"""ORA-local commitments shared by Home, agenda and conversation tools."""
import hashlib
import json
import logging
import uuid
from pymongo.errors import DuplicateKeyError
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def home_event_times(day: str, clock: str, tz_name: str, duration_minutes: int = 60) -> tuple[str, str]:
    if len(day) != 10 or len(clock) != 5:
        raise ValueError("invalid format")
    date = datetime.strptime(day, "%Y-%m-%d").date()
    hour, minute = map(int, clock.split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("invalid clock")
    if not 5 <= duration_minutes <= 1440:
        raise ValueError("invalid duration")
    zone = ZoneInfo(tz_name)
    start = datetime(date.year, date.month, date.day, hour, minute, tzinfo=zone)
    utc = start.astimezone(timezone.utc)
    if utc.astimezone(zone).replace(tzinfo=None) != start.replace(tzinfo=None):
        raise ValueError("nonexistent local time")
    end = (utc + timedelta(minutes=duration_minutes)).astimezone(zone)
    return start.isoformat(), end.isoformat()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _moment(raw, zone):
    value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone)
    local = value.astimezone(timezone.utc).astimezone(zone)
    if local.replace(tzinfo=None) != value.replace(tzinfo=None) or local.utcoffset() != value.utcoffset():
        raise ValueError("timezone_mismatch")
    return value


async def get_manual_event(db, user_id, event_id):
    return await db.life_nodes.find_one(
        {"id": event_id, "user_id": user_id, "type": "event", "attributes.kind": "home_manual"},
        {"_id": 0},
    )


def manual_event_public(node):
    attrs = node.get("attributes") or {}
    return {"id": node["id"], "title": node["label"], "starts_at": attrs.get("starts_at"),
            "ends_at": attrs.get("ends_at"), "timezone": attrs.get("timezone"),
            "location": attrs.get("location") or "", "description": node.get("description") or "",
            "source": "ora", "status": node.get("status"), "updated_at": node.get("updated_at")}


async def _wake(db, user_id, event_id, kind, revision):
    """Re-use the durable worker. A saved event is not a promise to notify."""
    try:
        from opportunities.discovery import OpportunityDiscovery
        await OpportunityDiscovery(db).note(
            user_id, source="calendar", kind=kind, entity_ref=f"calendar:{event_id}",
            entity_kind="event", after=revision, wake=False,
        )
        from ambient.service import AmbientService
        await AmbientService(db).schedule(
            user_id, reason="state_changed", when=datetime.now(timezone.utc),
            source_ref=f"calendar:{event_id}",
        )
    except Exception as exc:
        logger.warning("manual calendar review not scheduled: %s", type(exc).__name__)


async def create_manual_event(db, user_id, *, title, start, end, tz_name,
                              request_id=None, location="", description=""):
    title = title.strip()
    if not title:
        raise ValueError("title_required")
    # Mongo's unique _id makes concurrent submissions of the same request atomic.
    key = hashlib.sha256(f"{user_id}|{request_id or uuid.uuid4().hex}".encode()).hexdigest()
    event_id = "node_home_" + key[:24]
    attrs = {"starts_at": start, "ends_at": end, "timezone": tz_name,
             "kind": "home_manual", "location": location.strip()}
    fingerprint = hashlib.sha256(json.dumps([title, attrs, description.strip()], sort_keys=True).encode()).hexdigest()
    now = _now()
    try:
        await db.life_nodes.update_one(
            {"_id": "home_event:" + key},
            {"$setOnInsert": {"id": event_id, "user_id": user_id, "type": "event",
                              "label": title, "description": description.strip(), "attributes": attrs,
                              "status": "active", "origin": "home_calendar", "created_at": now,
                              "updated_at": now, "request_fingerprint": fingerprint}}, upsert=True,
        )
    except DuplicateKeyError:
        pass  # Another concurrent submission inserted this exact unique key.
    node = await get_manual_event(db, user_id, event_id)
    if not node or node.get("request_fingerprint") != fingerprint:
        raise ValueError("request_conflict")
    if node["status"] != "active":
        raise ValueError("event_cancelled")
    await _wake(db, user_id, event_id, "event.added", node["created_at"])
    return manual_event_public(node)


async def manual_events_between(db, user_id, start, end, *, limit=500):
    # ISO strings can have different offsets. Use a broad date window, then
    # compare actual instants; lexical offset ordering is not chronological.
    rows = await db.life_nodes.find(
        {"user_id": user_id, "type": "event", "status": "active", "attributes.kind": "home_manual",
         "attributes.starts_at": {"$gte": (start - timedelta(days=1)).date().isoformat(),
                                  "$lt": (end + timedelta(days=1)).date().isoformat()}},
        {"_id": 0},
    ).to_list(length=2000)
    result = []
    for row in rows:
        try:
            at = datetime.fromisoformat(row["attributes"]["starts_at"].replace("Z", "+00:00"))
            if at.tzinfo is None:
                at = at.replace(tzinfo=ZoneInfo(row["attributes"].get("timezone") or "Europe/Rome"))
            if start <= at < end:
                result.append((at, manual_event_public(row)))
        except (ValueError, KeyError, TypeError):
            continue
    return [item for _, item in sorted(result, key=lambda pair: pair[0])][:limit]


async def update_manual_event(db, user_id, event_id, fields, *, expected_updated_at=None):
    node = await get_manual_event(db, user_id, event_id)
    if not node:
        raise ValueError("event_not_found")
    if node.get("status") != "active":
        raise ValueError("event_cancelled")
    attrs = dict(node["attributes"])
    zone = ZoneInfo(str(fields.get("timezone") or attrs.get("timezone") or "Europe/Rome"))
    old_start = datetime.fromisoformat(attrs["starts_at"])
    old_end = datetime.fromisoformat(attrs["ends_at"])
    start = _moment(fields.get("start_datetime") or attrs["starts_at"], zone)
    if fields.get("end_datetime"):
        end = _moment(fields["end_datetime"], zone)
    elif fields.get("start_datetime"):
        end = (start.astimezone(timezone.utc) + (old_end.astimezone(timezone.utc) - old_start.astimezone(timezone.utc))).astimezone(zone)
    else:
        end = _moment(attrs["ends_at"], zone)
    if end.astimezone(timezone.utc) <= start.astimezone(timezone.utc):
        raise ValueError("end_before_start")
    title = str(fields.get("title", node["label"])).strip()
    if not title or len(title) > 200:
        raise ValueError("invalid_title")
    location = str(fields.get("location", attrs.get("location") or "")).strip()
    description = str(fields.get("description", node.get("description") or "")).strip()
    if len(location) > 300 or len(description) > 800:
        raise ValueError("invalid_input")
    attrs.update(starts_at=start.isoformat(), ends_at=end.isoformat(), timezone=str(zone), location=location)
    if expected_updated_at and expected_updated_at != node.get("updated_at"):
        if title == node["label"] and description == (node.get("description") or "") and attrs == node["attributes"]:
            return manual_event_public(node)  # Retry after a lost success response.
        raise ValueError("event_changed")
    result = await db.life_nodes.update_one(
        {"id": event_id, "user_id": user_id, "status": "active", "updated_at": node.get("updated_at")},
        {"$set": {"label": title, "description": description, "attributes": attrs, "updated_at": _now()}},
    )
    if not result.matched_count:
        raise ValueError("event_changed")
    observed = await get_manual_event(db, user_id, event_id)
    if not observed or observed.get("status") != "active" or observed["attributes"] != attrs or observed["label"] != title or (observed.get("description") or "") != description:
        raise ValueError("event_changed")
    await _wake(db, user_id, event_id, "event.updated", observed["updated_at"])
    return manual_event_public(observed)


async def archive_manual_event(db, user_id, event_id):
    node = await get_manual_event(db, user_id, event_id)
    if not node:
        return False
    from life_graph.service import LifeGraphService
    await LifeGraphService(db).archive_node(user_id, event_id)
    seen = await get_manual_event(db, user_id, event_id)
    if seen:
        await _wake(db, user_id, event_id, "event.removed", seen["updated_at"])
    return bool(seen and seen.get("status") == "archived")
