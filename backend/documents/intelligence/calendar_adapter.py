"""Provider-agnostic calendar drafts (internal first; google/apple later)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from documents.intelligence.analyzer import maps_directions_url, maps_query_url
from documents.intelligence.schemas import CalendarEventDraft


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"ced_{uuid.uuid4().hex[:12]}"


class CalendarProvider(Protocol):
    name: str

    async def create_from_candidate(
        self,
        *,
        user_id: str,
        candidate: dict[str, Any],
        overrides: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ...


class InternalCalendarProvider:
    name = "internal"

    def __init__(self, db):
        self.db = db

    async def create_from_candidate(
        self,
        *,
        user_id: str,
        candidate: dict[str, Any],
        overrides: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ov = overrides or {}
        # Idempotency guard at provider level
        existing = await self.db.calendar_event_drafts.find_one(
            {
                "user_id": user_id,
                "source_document_id": candidate["source_document_id"],
                "source_event_candidate_id": candidate["id"],
                "status": {"$ne": "cancelled"},
            },
            {"_id": 0},
        )
        if existing:
            return existing
        now = _now()
        draft = CalendarEventDraft(
            id=_new_id(),
            user_id=user_id,
            provider="internal",
            title=str(ov.get("title") or candidate.get("title") or "Evento"),
            description=str(ov.get("description") or candidate.get("description") or "")[:400],
            start_datetime=ov.get("start_datetime") or candidate.get("start_datetime"),
            end_datetime=ov.get("end_datetime") or candidate.get("end_datetime"),
            timezone=str(ov.get("timezone") or candidate.get("timezone") or "Europe/Rome"),
            all_day=bool(ov.get("all_day", candidate.get("all_day", False))),
            location=ov.get("location") or _location_str(candidate),
            source_document_id=candidate["source_document_id"],
            source_event_candidate_id=candidate["id"],
            status="confirmed",
            created_at=now,
            updated_at=now,
            sync_provider="internal",
            sync_status="local_only",
            priority=candidate.get("priority"),
            urgency=candidate.get("urgency"),
        )
        doc = draft.model_dump()
        await self.db.calendar_event_drafts.insert_one(doc)
        doc.pop("_id", None)
        return doc


def _location_str(candidate: dict[str, Any]) -> Optional[str]:
    parts = [candidate.get("venue_name"), candidate.get("address"), candidate.get("city")]
    out = ", ".join(p for p in parts if p)
    return out or None


def enrich_maps(candidate: dict[str, Any]) -> dict[str, Any]:
    q = candidate.get("maps_query") or _location_str(candidate)
    if not q:
        return {"maps_url": None, "directions_url": None, "maps_query": None}
    return {
        "maps_query": q,
        "maps_url": maps_query_url(q),
        "directions_url": maps_directions_url(q),
    }


class CalendarGateway:
    def __init__(self, db):
        self.db = db
        self._providers = {"internal": InternalCalendarProvider(db)}

    def get(self, provider: str = "internal") -> CalendarProvider:
        if provider not in self._providers:
            raise ValueError(f"Calendar provider non disponibile: {provider}")
        return self._providers[provider]

    async def list_for_user(self, user_id: str, limit: int = 100) -> list[dict]:
        cur = self.db.calendar_event_drafts.find(
            {"user_id": user_id, "status": {"$ne": "cancelled"}},
            {"_id": 0},
        ).sort("start_datetime", 1).limit(limit)
        return await cur.to_list(limit)
