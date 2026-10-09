"""Source-backed life-cycle rules for perishable update cards.

Never infer a deadline from the words "viaggio", from a title or from the
creation time of the alert. Only the user's actual dated source can expire it.
All reads are owner-scoped and bounded. No database rows are deleted.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _instant(value, *, zone="UTC", end_of_day=False):
    if not value:
        return None
    try:
        raw = str(value).strip()
        if len(raw) == 10:
            day = datetime.fromisoformat(raw)
            local = day.replace(tzinfo=ZoneInfo(zone))
            if end_of_day:
                local = local + timedelta(days=1)
            return local.astimezone(timezone.utc)
        at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if at.tzinfo is None:
            at = at.replace(tzinfo=ZoneInfo(zone))
        return at.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError, KeyError):
        return None


async def source_event_expired(db, owner_id, source_refs, *, now=None):
    """True only when a *referenced*, owner-owned event has definitively ended.

    Missing, moved or ambiguous source: keep the concern for an actual review,
    rather than silently deleting an unverified event.
    """
    moment = now or datetime.now(timezone.utc)
    refs = list(dict.fromkeys(str(x or "").strip() for x in source_refs if x))[:8]
    if not refs or db is None:
        return False
    for ref in refs:
        event_id = ref.removeprefix("calendar:")
        if not event_id:
            continue
        # Personal calendar entered directly in ORA.
        if ref.startswith("calendar:"):
            from home.manual_event import get_manual_event
            node = await get_manual_event(db, owner_id, event_id)
            if node and node.get("status") == "active":
                attrs = node.get("attributes") or {}
                deadline = _instant(attrs.get("ends_at") or attrs.get("starts_at"),
                                    zone=str(attrs.get("timezone") or "UTC"),
                                    end_of_day=True)
                if deadline is not None:
                    return moment >= deadline
            # An unknown calendar: prefix is not proof the event was ORA-local.
            # Fall through to provider lookup rather than silently ignoring it.
        event = await db.calendar_events.find_one(
            {"user_id": owner_id, "id": event_id,
             "status": {"$nin": ["cancelled", "archived"]}},
            {"_id": 0, "start_at": 1, "end_at": 1, "timezone": 1})
        if event is not None:
            deadline = _instant(event.get("end_at") or event.get("start_at"),
                                zone=str(event.get("timezone") or "UTC"), end_of_day=True)
            if deadline is not None:
                return moment >= deadline
            continue
        # Linked Google calendar evidence retains the provider event identity.
        ingested = await db.ingestion_events.find_one(
            {"user_id": owner_id, "source_record_type": "calendar_event",
             "external_id": event_id, "ingestion_status": {"$ne": "superseded"}},
            {"_id": 0, "normalized_payload": 1, "source_status": 1},
            sort=[("ingested_at", -1)])
        if ingested and ingested.get("source_status") != "detached":
            from ingestion.reading import plain
            payload = plain(ingested.get("normalized_payload")) or {}
            if str(payload.get("status") or "").lower() == "cancelled":
                continue
            deadline = _instant(payload.get("ends_at") or payload.get("starts_at"),
                                zone=str(payload.get("timezone") or "UTC"), end_of_day=True)
            if deadline is not None:
                return moment >= deadline
    return False


async def perishable_opportunity_expired(db, owner_id, opportunity, *, now=None):
    """Legacy opportunity with missing valid_until can expire from real evidence.

    Only a time-perishable, event-sourced alert qualifies. Other follow-ups
    (refunds, bills, consequences after a trip) must not be thrown away.
    """
    refs = []
    disagreement_targets = []
    for evidence in getattr(opportunity, "evidence", None) or []:
        if evidence.kind in ("calendar_event", "linked_target"):
            refs.append(evidence.ref)
        if evidence.kind == "disagreement":
            # A calendar discrepancy is perishable because the underlying
            # appointment ends, regardless of how a historical AI scan
            # described time_sensitivity ("stable"/"changing"/"perishable").
            link = await db.connected_situation_links.find_one(
                {"owner_id": owner_id, "id": evidence.ref, "target_kind": "appointment"},
                {"_id": 0, "target_ref": 1})
            if link and link.get("target_ref"):
                disagreement_targets.append(link["target_ref"])
    if disagreement_targets:
        # One of several still-current appointments must not be discarded
        # because another ended. All cited appointment targets must be over.
        return all([
            await source_event_expired(db, owner_id, [ref], now=now)
            for ref in list(dict.fromkeys(disagreement_targets))[:8]
        ])
    if getattr(opportunity, "valid_until", None):
        return False  # canonical deadline governs other opportunity types
    if getattr(opportunity, "time_sensitivity", "") != "perishable":
        return False
    return await source_event_expired(db, owner_id, refs, now=now)
