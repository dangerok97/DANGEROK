"""Lazy-sync observers.

Each observer reads *existing* collections in the DB (produced by other
modules) and appends new behavioral events to the timeline. This module
NEVER writes to source collections and NEVER modifies other modules.

Observers are idempotent thanks to the unique index on
(user_id, source_type, source_ref) in ``behavioral_events``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from .storage import BehavioralStorage
from .timeline import BehavioralTimeline, _iso
from .types import BehavioralEventType


DECISION_ACTION_TO_EVENT: Dict[str, BehavioralEventType] = {
    "start": BehavioralEventType.DECISION_STARTED,
    "complete": BehavioralEventType.DECISION_COMPLETED,
    "partial": BehavioralEventType.DECISION_PARTIAL,
    "postpone": BehavioralEventType.DECISION_POSTPONED,
    "block": BehavioralEventType.DECISION_BLOCKED,
    "dismiss": BehavioralEventType.DECISION_DISMISSED,
}


def _mk_doc(
    *,
    user_id: str,
    event_type: BehavioralEventType,
    occurred_at: datetime,
    metadata: Optional[Dict[str, Any]] = None,
    source_type: Optional[str] = None,
    source_ref: Optional[str] = None,
    idem_suffix: str = "",
) -> Dict[str, Any]:
    import uuid
    return {
        "id": f"bhv_{uuid.uuid4().hex[:16]}",
        "user_id": user_id,
        "event_type": event_type.value,
        "occurred_at": _iso(occurred_at),
        "metadata": metadata or {},
        "source_type": source_type,
        "source_ref": (source_ref or "") + (f":{idem_suffix}" if idem_suffix else ""),
        "recorded_at": datetime.now(timezone.utc),
        "version": 1,
        "immutable": True,
    }


class Observers:
    """One-shot lazy syncers. Callable on demand or by the service."""

    def __init__(self, db: AsyncIOMotorDatabase, storage: BehavioralStorage, timeline: BehavioralTimeline):
        self.db = db
        self.store = storage
        self.timeline = timeline

    # ------------------------ Decision action history ------------------------
    async def sync_decisions(self, user_id: str, *, max_batch: int = 500) -> int:
        source = "decision_action_history"
        cursor = await self.store.get_cursor(user_id, source)
        since = cursor.get("last_processed_at") if cursor else None

        q: Dict[str, Any] = {"user_id": user_id}
        if since:
            q["timestamp"] = {"$gt": since}
        cur = self.db[source].find(q, {"_id": 0}).sort("timestamp", 1).limit(max_batch)
        rows = await cur.to_list(length=max_batch)
        if not rows:
            return 0

        docs: List[Dict[str, Any]] = []
        latest_ts: Optional[datetime] = None
        for r in rows:
            action = r.get("user_action")
            evt = DECISION_ACTION_TO_EVENT.get(action)
            if evt is None:
                continue
            occurred = r.get("timestamp")
            if isinstance(occurred, str):
                try:
                    occurred = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
                except Exception:
                    continue
            if not isinstance(occurred, datetime):
                continue
            occurred = _iso(occurred)
            latest_ts = max(latest_ts, occurred) if latest_ts else occurred

            docs.append(_mk_doc(
                user_id=user_id,
                event_type=evt,
                occurred_at=occurred,
                metadata={
                    "decision_id": r.get("decision_id"),
                    "old_status": r.get("old_status"),
                    "new_status": r.get("new_status"),
                    "completion_percentage": r.get("completion_percentage"),
                    "postponed_until": r.get("postponed_until"),
                },
                source_type=source,
                source_ref=r.get("id"),
            ))

        inserted = await self.timeline.append_events(docs)
        if latest_ts:
            await self.store.upsert_cursor(user_id, source, last_processed_at=latest_ts)
        return inserted

    # ------------------------ Ingestion events (calendar) ------------------------
    async def sync_calendar_events(self, user_id: str, *, max_batch: int = 500) -> int:
        source = "ingestion_events"
        cursor = await self.store.get_cursor(user_id, source)
        since = cursor.get("last_processed_at") if cursor else None

        q: Dict[str, Any] = {"user_id": user_id, "ingestion_status": "processed"}
        if since:
            q["processed_at"] = {"$gt": since}
        cur = self.db[source].find(q, {"_id": 0}).sort("processed_at", 1).limit(max_batch)
        rows = await cur.to_list(length=max_batch)
        if not rows:
            return 0

        docs: List[Dict[str, Any]] = []
        latest_ts: Optional[datetime] = None
        for r in rows:
            occurred = r.get("processed_at") or r.get("ingested_at") or r.get("created_at")
            if isinstance(occurred, str):
                try:
                    occurred = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
                except Exception:
                    continue
            if not isinstance(occurred, datetime):
                continue
            occurred = _iso(occurred)
            latest_ts = max(latest_ts, occurred) if latest_ts else occurred

            # We only categorize IMPORTED here; UPDATE/DELETE would require
            # ingestion_status='updated'/'deleted' which the ingestion core
            # does not currently emit — we leave the enum values reserved
            # for future use so no data is ever fabricated.
            evt = BehavioralEventType.CALENDAR_EVENT_IMPORTED
            if r.get("supersedes_event_id"):
                evt = BehavioralEventType.CALENDAR_EVENT_UPDATED

            docs.append(_mk_doc(
                user_id=user_id,
                event_type=evt,
                occurred_at=occurred,
                metadata={
                    "connector_id": r.get("connector_id"),
                    "connector_instance_id": r.get("connector_instance_id"),
                    "source_record_type": r.get("source_record_type"),
                },
                source_type=source,
                source_ref=r.get("id"),
            ))

        inserted = await self.timeline.append_events(docs)
        if latest_ts:
            await self.store.upsert_cursor(user_id, source, last_processed_at=latest_ts)
        return inserted

    # ------------------------ Connector instances (connect/sync/disconnect) ------------------------
    async def sync_connector_lifecycle(self, user_id: str) -> int:
        source = "connector_instances"
        cur = self.db[source].find({"user_id": user_id}, {"_id": 0})
        instances = await cur.to_list(length=100)
        if not instances:
            return 0

        docs: List[Dict[str, Any]] = []
        for inst in instances:
            iid = inst.get("id") or ""
            connector_id = inst.get("connector_id")
            created_at = inst.get("created_at")
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except Exception:
                    created_at = None
            if isinstance(created_at, datetime):
                docs.append(_mk_doc(
                    user_id=user_id,
                    event_type=BehavioralEventType.CALENDAR_CONNECTED,
                    occurred_at=_iso(created_at),
                    metadata={"connector_id": connector_id, "instance_id": iid},
                    source_type=source,
                    source_ref=iid,
                    idem_suffix="connected",
                ))

            last_sync = inst.get("last_sync_at")
            if isinstance(last_sync, str):
                try:
                    last_sync = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                except Exception:
                    last_sync = None
            if isinstance(last_sync, datetime):
                docs.append(_mk_doc(
                    user_id=user_id,
                    event_type=BehavioralEventType.CALENDAR_SYNC,
                    occurred_at=_iso(last_sync),
                    metadata={"connector_id": connector_id, "instance_id": iid},
                    source_type=source,
                    source_ref=iid,
                    # Uniqueness of "latest sync" event uses the last_sync
                    # timestamp as a stable idem suffix; a new sync produces
                    # a new occurred_at → new unique source_ref.
                    idem_suffix=f"sync-{int(last_sync.timestamp())}",
                ))

            status = inst.get("status")
            if status in ("revoked", "disconnected"):
                updated = inst.get("updated_at")
                if isinstance(updated, str):
                    try:
                        updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    except Exception:
                        updated = None
                if isinstance(updated, datetime):
                    docs.append(_mk_doc(
                        user_id=user_id,
                        event_type=BehavioralEventType.CALENDAR_DISCONNECTED,
                        occurred_at=_iso(updated),
                        metadata={"connector_id": connector_id, "instance_id": iid, "status": status},
                        source_type=source,
                        source_ref=iid,
                        idem_suffix="disconnected",
                    ))

        return await self.timeline.append_events(docs)

    # ------------------------ Daily summaries ------------------------
    async def sync_daily_summaries(self, user_id: str, *, max_batch: int = 200) -> int:
        source = "daily_summaries"
        cursor = await self.store.get_cursor(user_id, source)
        since = cursor.get("last_processed_at") if cursor else None
        q: Dict[str, Any] = {"user_id": user_id}
        if since:
            q["generated_at"] = {"$gt": since}
        cur = self.db[source].find(q, {"_id": 0}).sort("generated_at", 1).limit(max_batch)
        rows = await cur.to_list(length=max_batch)
        if not rows:
            return 0

        docs: List[Dict[str, Any]] = []
        latest_ts: Optional[datetime] = None
        for r in rows:
            occurred = r.get("generated_at") or r.get("date")
            if isinstance(occurred, str):
                try:
                    occurred = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
                except Exception:
                    continue
            if not isinstance(occurred, datetime):
                continue
            occurred = _iso(occurred)
            latest_ts = max(latest_ts, occurred) if latest_ts else occurred
            docs.append(_mk_doc(
                user_id=user_id,
                event_type=BehavioralEventType.DAILY_SUMMARY_GENERATED,
                occurred_at=occurred,
                metadata={"date": r.get("date"), "total_events": r.get("total_events")},
                source_type=source,
                source_ref=r.get("id") or (r.get("date") and str(r.get("date"))),
            ))
        inserted = await self.timeline.append_events(docs)
        if latest_ts:
            await self.store.upsert_cursor(user_id, source, last_processed_at=latest_ts)
        return inserted

    # ------------------------ Context snapshots ------------------------
    async def sync_context_snapshots(self, user_id: str, *, max_batch: int = 500) -> int:
        source = "context_snapshots"
        cursor = await self.store.get_cursor(user_id, source)
        since = cursor.get("last_processed_at") if cursor else None
        q: Dict[str, Any] = {"user_id": user_id}
        if since:
            q["generated_at"] = {"$gt": since}
        cur = self.db[source].find(q, {"_id": 0}).sort("generated_at", 1).limit(max_batch)
        rows = await cur.to_list(length=max_batch)
        if not rows:
            return 0
        docs: List[Dict[str, Any]] = []
        latest_ts: Optional[datetime] = None
        for r in rows:
            occurred = r.get("generated_at")
            if isinstance(occurred, str):
                try:
                    occurred = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
                except Exception:
                    continue
            if not isinstance(occurred, datetime):
                continue
            occurred = _iso(occurred)
            latest_ts = max(latest_ts, occurred) if latest_ts else occurred
            docs.append(_mk_doc(
                user_id=user_id,
                event_type=BehavioralEventType.CONTEXT_SNAPSHOT_CREATED,
                occurred_at=occurred,
                metadata={"decision_id": r.get("decision_id"), "context_hash": r.get("context_hash", "")[:12]},
                source_type=source,
                source_ref=r.get("id"),
            ))
        inserted = await self.timeline.append_events(docs)
        if latest_ts:
            await self.store.upsert_cursor(user_id, source, last_processed_at=latest_ts)
        return inserted

    # ------------------------ Orchestration ------------------------
    async def sync_all(self, user_id: str) -> Dict[str, int]:
        """Sync from every source. Safe to call before every /behavior read."""
        return {
            "decisions": await self.sync_decisions(user_id),
            "calendar_events": await self.sync_calendar_events(user_id),
            "connector_lifecycle": await self.sync_connector_lifecycle(user_id),
            "daily_summaries": await self.sync_daily_summaries(user_id),
            "context_snapshots": await self.sync_context_snapshots(user_id),
        }

    # ------------------------ Middleware hooks (app usage) ------------------------
    async def record_app_open_if_needed(self, user_id: str, *, now: Optional[datetime] = None) -> bool:
        """Idempotent per (user, UTC-date). Called by a light HTTP middleware."""
        now = now or datetime.now(timezone.utc)
        day_key = now.strftime("%Y-%m-%d")
        ok = await self.timeline.append_event(
            user_id=user_id,
            event_type=BehavioralEventType.FIRST_APP_OPEN_TODAY,
            occurred_at=now,
            metadata={"date": day_key},
            source_type="middleware",
            source_ref=f"first_open:{day_key}",
        )
        return ok

    async def record_manual_refresh(self, user_id: str, *, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        # Idempotent per minute to avoid double-fire on rapid refreshes.
        minute_key = now.strftime("%Y-%m-%dT%H:%M")
        return await self.timeline.append_event(
            user_id=user_id,
            event_type=BehavioralEventType.MANUAL_REFRESH,
            occurred_at=now,
            metadata={"minute": minute_key},
            source_type="middleware",
            source_ref=f"refresh:{minute_key}",
        )

    async def record_app_close(self, user_id: str, *, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        minute_key = now.strftime("%Y-%m-%dT%H:%M")
        return await self.timeline.append_event(
            user_id=user_id,
            event_type=BehavioralEventType.LAST_APP_CLOSE,
            occurred_at=now,
            metadata={"minute": minute_key},
            source_type="middleware",
            source_ref=f"close:{minute_key}",
        )
