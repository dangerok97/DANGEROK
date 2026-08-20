"""Provider abstraction — real Google client vs in-memory fake.

The provider ONLY performs data-plane calls (list calendars, list/write
events). OAuth token acquisition happens in `oauth.py`; the provider
receives an already-materialized access token from the caller and never
persists it.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol
from urllib.parse import quote

import httpx


class ProviderNotConfigured(Exception):
    """The real provider was requested but env is missing configuration."""


class GoogleCalendarAPIError(Exception):
    def __init__(self, status_code: int, message: str = "", *, etag_conflict: bool = False):
        super().__init__(message or f"google_calendar_http_{status_code}")
        self.status_code = status_code
        self.etag_conflict = etag_conflict


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


def _cal_path(calendar_id: str) -> str:
    return quote(calendar_id, safe="")


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

    async def create_event(
        self, *, access_token: str, calendar_id: str, body: Dict[str, Any],
    ) -> Dict[str, Any]: ...

    async def get_event(
        self, *, access_token: str, calendar_id: str, event_id: str,
    ) -> Dict[str, Any]: ...

    async def update_event(
        self,
        *,
        access_token: str,
        calendar_id: str,
        event_id: str,
        body: Dict[str, Any],
        etag: Optional[str] = None,
    ) -> Dict[str, Any]: ...

    async def delete_event(
        self, *, access_token: str, calendar_id: str, event_id: str,
    ) -> bool: ...


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
                f"{self.BASE}/calendars/{_cal_path(calendar_id)}/events",
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

    async def _find_by_ora_event_id(
        self, *, access_token: str, calendar_id: str, ora_event_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Bounded, exact lookup via Google's own privateExtendedProperty
        filter — never a fuzzy match on title/start/location. Best-effort:
        a failed lookup falls through to create() rather than blocking it.
        """
        try:
            async with httpx.AsyncClient(timeout=30) as h:
                r = await h.get(
                    f"{self.BASE}/calendars/{_cal_path(calendar_id)}/events",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "privateExtendedProperty": f"ora_event_id={ora_event_id}",
                        "maxResults": 1,
                        "showDeleted": False,
                        "singleEvents": True,
                    },
                )
                if r.status_code >= 400:
                    return None
                items = (r.json() or {}).get("items") or []
                return items[0] if items else None
        except httpx.HTTPError:
            return None

    async def create_event(
        self, *, access_token: str, calendar_id: str, body: Dict[str, Any],
    ) -> Dict[str, Any]:
        ora_event_id = (
            (body.get("extendedProperties") or {}).get("private") or {}
        ).get("ora_event_id")
        if ora_event_id:
            existing = await self._find_by_ora_event_id(
                access_token=access_token,
                calendar_id=calendar_id,
                ora_event_id=str(ora_event_id),
            )
            if existing:
                return existing
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.post(
                f"{self.BASE}/calendars/{_cal_path(calendar_id)}/events",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if r.status_code >= 400:
                raise GoogleCalendarAPIError(r.status_code, r.text[:200])
            return r.json()

    async def get_event(
        self, *, access_token: str, calendar_id: str, event_id: str,
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.get(
                f"{self.BASE}/calendars/{_cal_path(calendar_id)}/events/{quote(event_id, safe='')}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if r.status_code == 404:
                raise GoogleCalendarAPIError(404, "not_found")
            if r.status_code >= 400:
                raise GoogleCalendarAPIError(r.status_code, r.text[:200])
            return r.json()

    async def update_event(
        self,
        *,
        access_token: str,
        calendar_id: str,
        event_id: str,
        body: Dict[str, Any],
        etag: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        if etag:
            headers["If-Match"] = etag
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.patch(
                f"{self.BASE}/calendars/{_cal_path(calendar_id)}/events/{quote(event_id, safe='')}",
                headers=headers,
                json=body,
            )
            if r.status_code == 412:
                raise GoogleCalendarAPIError(412, "etag_conflict", etag_conflict=True)
            if r.status_code == 404:
                raise GoogleCalendarAPIError(404, "not_found")
            if r.status_code >= 400:
                raise GoogleCalendarAPIError(r.status_code, r.text[:200])
            return r.json()

    async def delete_event(
        self, *, access_token: str, calendar_id: str, event_id: str,
    ) -> bool:
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.delete(
                f"{self.BASE}/calendars/{_cal_path(calendar_id)}/events/{quote(event_id, safe='')}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if r.status_code in (204, 200, 410):
                return True
            if r.status_code == 404:
                return True  # already gone
            raise GoogleCalendarAPIError(r.status_code, r.text[:200])


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

    def patch_seeded_event(self, *, calendar_id: str, event_id: str, patch: Dict[str, Any]):
        """Test helper — must not collide with async update_event protocol method."""
        assert calendar_id in self.events, f"unknown calendar {calendar_id}"
        assert event_id in self.events[calendar_id], f"unknown event {event_id}"
        self.events[calendar_id][event_id].update(patch)
        self._sync_generation += 1

    # Back-compat alias for older tests/fixtures
    def update_seeded_event(self, *, calendar_id: str, event_id: str, patch: Dict[str, Any]):
        return self.patch_seeded_event(calendar_id=calendar_id, event_id=event_id, patch=patch)

    def cancel_event(self, *, calendar_id: str, event_id: str):
        self.patch_seeded_event(calendar_id=calendar_id, event_id=event_id, patch={"status": "cancelled"})

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

    async def create_event(
        self, *, access_token: str, calendar_id: str, body: Dict[str, Any],
    ) -> Dict[str, Any]:
        if calendar_id not in self.calendars:
            raise GoogleCalendarAPIError(404, "calendar_not_found")
        eid = body.get("id") or f"fake_{hashlib.sha1(repr(body).encode()).hexdigest()[:12]}"
        # idempotency via extendedProperties.private.ora_event_id
        ora_id = ((body.get("extendedProperties") or {}).get("private") or {}).get("ora_event_id")
        if ora_id:
            for existing in self.events.get(calendar_id, {}).values():
                priv = ((existing.get("extendedProperties") or {}).get("private") or {})
                if priv.get("ora_event_id") == ora_id:
                    return existing
        event = {
            **body,
            "id": eid,
            "etag": f"etag-{self._sync_generation + 1}",
            "htmlLink": f"https://calendar.google.com/event?eid={eid}",
            "status": "confirmed",
        }
        self.seed_event(calendar_id=calendar_id, event=event)
        return event

    async def get_event(
        self, *, access_token: str, calendar_id: str, event_id: str,
    ) -> Dict[str, Any]:
        ev = (self.events.get(calendar_id) or {}).get(event_id)
        if not ev or ev.get("status") == "cancelled":
            raise GoogleCalendarAPIError(404, "not_found")
        return dict(ev)

    async def update_event(
        self,
        *,
        access_token: str,
        calendar_id: str,
        event_id: str,
        body: Dict[str, Any],
        etag: Optional[str] = None,
    ) -> Dict[str, Any]:
        ev = (self.events.get(calendar_id) or {}).get(event_id)
        if not ev:
            raise GoogleCalendarAPIError(404, "not_found")
        if etag and ev.get("etag") and etag != ev.get("etag"):
            raise GoogleCalendarAPIError(412, "etag_conflict", etag_conflict=True)
        ev.update(body)
        ev["etag"] = f"etag-{self._sync_generation + 1}"
        self._sync_generation += 1
        return dict(ev)

    async def delete_event(
        self, *, access_token: str, calendar_id: str, event_id: str,
    ) -> bool:
        if calendar_id in self.events and event_id in self.events[calendar_id]:
            self.cancel_event(calendar_id=calendar_id, event_id=event_id)
        return True


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
