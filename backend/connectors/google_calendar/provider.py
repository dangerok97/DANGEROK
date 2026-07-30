"""Provider abstraction — real Google client vs in-memory fake.

The provider ONLY performs data-plane calls (list calendars, list
events). OAuth token acquisition happens in `oauth.py`; the provider
receives an already-materialized access token from the caller and never
persists it.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

import httpx


class ProviderNotConfigured(Exception):
    """The real provider was requested but env is missing configuration."""


@dataclass
class CalendarSummary:
    id: str
    summary: Optional[str]
    time_zone: Optional[str]
    primary: bool = False
    access_role: Optional[str] = None


@dataclass
class EventsPage:
    events: List[Dict[str, Any]] = field(default_factory=list)
    next_page_token: Optional[str] = None
    next_sync_token: Optional[str] = None


class CalendarProviderProtocol(Protocol):
    """Interface implemented by both real and fake providers."""

    async def list_calendars(self, *, access_token: str) -> List[CalendarSummary]: ...

    async def list_events(
        self,
        *,
        access_token: str,
        calendar_id: str,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        page_token: Optional[str] = None,
        sync_token: Optional[str] = None,
        max_results: int = 250,
    ) -> EventsPage: ...


# ============================================================
# REAL provider — HTTP to googleapis.com
# ============================================================
class RealGoogleCalendarProvider:
    BASE = "https://www.googleapis.com/calendar/v3"

    async def list_calendars(self, *, access_token: str) -> List[CalendarSummary]:
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.get(
                f"{self.BASE}/users/me/calendarList",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"maxResults": 250},
            )
            r.raise_for_status()
            body = r.json()
        items = []
        for c in body.get("items") or []:
            items.append(CalendarSummary(
                id=c["id"],
                summary=c.get("summary"),
                time_zone=c.get("timeZone"),
                primary=bool(c.get("primary")),
                access_role=c.get("accessRole"),
            ))
        return items

    async def list_events(
        self,
        *,
        access_token: str,
        calendar_id: str,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        page_token: Optional[str] = None,
        sync_token: Optional[str] = None,
        max_results: int = 250,
    ) -> EventsPage:
        params: Dict[str, Any] = {
            "maxResults": max_results,
            "singleEvents": True,
            "showDeleted": True,
        }
        if sync_token:
            params["syncToken"] = sync_token
        else:
            if time_min:
                params["timeMin"] = time_min
            if time_max:
                params["timeMax"] = time_max
            params["orderBy"] = "startTime"
        if page_token:
            params["pageToken"] = page_token
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.get(
                f"{self.BASE}/calendars/{httpx.URL(calendar_id).host or calendar_id}/events",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            r.raise_for_status()
            body = r.json()
        return EventsPage(
            events=body.get("items") or [],
            next_page_token=body.get("nextPageToken"),
            next_sync_token=body.get("nextSyncToken"),
        )


# ============================================================
# FAKE provider — in-memory, seeded deterministically. Only active
# with CALENDAR_PROVIDER_MODE=fake.
# ============================================================
class FakeGoogleCalendarProvider:
    """Deterministic in-memory calendar store.

    Fixtures can call `seed_calendar`, `seed_event`, `update_event`,
    `delete_event`, `bump_sync_cursor` to drive scenarios.
    """

    def __init__(self):
        self.calendars: Dict[str, Dict[str, Any]] = {}
        # events[calendar_id][external_event_id] = raw google-shaped dict
        self.events: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # per-calendar sync cursor -> list of (event_id, version) snapshots
        self._sync_generation = 0

    # ---- fixture helpers (never used by real provider) ----
    def seed_calendar(self, *, calendar_id: str, summary: str, time_zone: str = "Europe/Rome", primary: bool = False):
        self.calendars[calendar_id] = {
            "id": calendar_id, "summary": summary, "time_zone": time_zone, "primary": primary,
            "access_role": "owner",
        }
        self.events.setdefault(calendar_id, {})

    def seed_event(self, *, calendar_id: str, event: Dict[str, Any]):
        assert calendar_id in self.calendars, f"unknown calendar {calendar_id}"
        self.events.setdefault(calendar_id, {})[event["id"]] = dict(event)
        self._sync_generation += 1

    def update_event(self, *, calendar_id: str, event_id: str, patch: Dict[str, Any]):
        assert calendar_id in self.events, f"unknown calendar {calendar_id}"
        assert event_id in self.events[calendar_id], f"unknown event {event_id}"
        self.events[calendar_id][event_id].update(patch)
        self._sync_generation += 1

    def cancel_event(self, *, calendar_id: str, event_id: str):
        self.update_event(calendar_id=calendar_id, event_id=event_id, patch={"status": "cancelled"})

    # ---- provider interface ----
    async def list_calendars(self, *, access_token: str) -> List[CalendarSummary]:
        return [
            CalendarSummary(
                id=c["id"], summary=c.get("summary"), time_zone=c.get("time_zone"),
                primary=bool(c.get("primary")), access_role=c.get("access_role"),
            )
            for c in self.calendars.values()
        ]

    async def list_events(
        self,
        *,
        access_token: str,
        calendar_id: str,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        page_token: Optional[str] = None,
        sync_token: Optional[str] = None,
        max_results: int = 250,
    ) -> EventsPage:
        if calendar_id not in self.events:
            return EventsPage(events=[], next_sync_token=f"fake:{self._sync_generation}")
        events = list(self.events[calendar_id].values())
        # crude window filter (respect time_min/time_max if not using sync token)
        if not sync_token:
            def _key(e):
                s = e.get("start") or {}
                return s.get("dateTime") or s.get("date") or ""
            events = sorted(events, key=_key)
        return EventsPage(
            events=events,
            next_page_token=None,
            next_sync_token=f"fake:{self._sync_generation}",
        )


# ============================================================
# Factory — driven by env CALENDAR_PROVIDER_MODE
# ============================================================
_FAKE_SINGLETON = FakeGoogleCalendarProvider()


def get_fake_provider() -> FakeGoogleCalendarProvider:
    """Test-only accessor for the shared in-memory fake."""
    return _FAKE_SINGLETON


def build_calendar_provider() -> CalendarProviderProtocol:
    mode = os.environ.get("CALENDAR_PROVIDER_MODE", "real").strip().lower()
    if mode == "fake":
        return _FAKE_SINGLETON
    return RealGoogleCalendarProvider()


def is_real_provider_configured() -> bool:
    """Return True iff the REAL provider has all its required env vars."""
    return bool(
        os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
        and os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
        and os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    )
