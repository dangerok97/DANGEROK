"""Minimal, general-purpose user-timezone resolver.

Not a reasoning engine: a bounded, local-only, authority-tiered lookup used by
Calendar (and, later, AI Core) to resolve "what timezone should this datetime
be interpreted in". No external calls, no GPS-derived residence inference, no
new UI/wizard — this only READS signals that already exist elsewhere in the
system, or falls back to a single, explicitly-labeled system default.

Precedence (first present + valid wins):
  1. user_confirmed   — `users.settings.timezone` (the one generic account
                         preference slot the app already has, e.g.
                         `settings.location_mode`; no dedicated write path is
                         created here — this only reads it if/when set).
  2. connector_calendar — the most recently synced Google/Apple calendar
                         event's own IANA timezone, already persisted locally
                         on `life_nodes` (type="event") by the ingestion
                         pipeline (`ingestion/routing.py`). No live Google
                         call is made to obtain this.
  3. system_fallback  — a single named constant, never presented as
                         user-confirmed.

Deliberately excluded from this version: any device/browser timezone signal
(none exists in the codebase today — PresenceContext carries no timezone
field) and any GPS/coordinate-derived timezone (explicitly forbidden: GPS
must never be used to infer a durable residence/timezone).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TimezoneAuthority = Literal["user_confirmed", "connector_calendar", "system_fallback"]

# Single named fallback constant. Intentionally the same value already used
# ambiently across ~15 unrelated modules (study/travel parsers, document
# intelligence, etc.) so this resolver does not introduce a *second*,
# divergent default — but it is always reported with authority
# "system_fallback", never silently presented as a confirmed user setting.
DEFAULT_SYSTEM_TIMEZONE = "Europe/Rome"


@dataclass
class ResolvedTimezone:
    tz_name: str
    authority: TimezoneAuthority
    source_ref: Optional[str] = None

    def is_confirmed(self) -> bool:
        return self.authority == "user_confirmed"


def is_valid_iana_timezone(tz_name: Optional[str]) -> bool:
    if not tz_name or not isinstance(tz_name, str):
        return False
    try:
        ZoneInfo(tz_name)
        return True
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return False


async def resolve_user_timezone(db, user_id: str) -> ResolvedTimezone:
    """Bounded, local-only. No external/Google call. Safe to call per turn."""
    if not user_id:
        return ResolvedTimezone(DEFAULT_SYSTEM_TIMEZONE, "system_fallback", None)

    user_doc = await db.users.find_one(
        {"id": user_id}, {"_id": 0, "settings.timezone": 1}
    )
    candidate = ((user_doc or {}).get("settings") or {}).get("timezone")
    if is_valid_iana_timezone(candidate):
        return ResolvedTimezone(
            str(candidate), "user_confirmed", "users.settings.timezone"
        )

    node = await db.life_nodes.find_one(
        {
            "user_id": user_id,
            "type": "event",
            "attributes.timezone": {"$exists": True, "$ne": None},
        },
        {"_id": 0, "id": 1, "attributes.timezone": 1},
        sort=[("updated_at", -1)],
    )
    candidate = ((node or {}).get("attributes") or {}).get("timezone")
    if is_valid_iana_timezone(candidate):
        node_id = (node or {}).get("id")
        return ResolvedTimezone(
            str(candidate),
            "connector_calendar",
            f"life_nodes:{node_id}" if node_id else "life_nodes",
        )

    return ResolvedTimezone(DEFAULT_SYSTEM_TIMEZONE, "system_fallback", None)


def localize_naive_datetime(
    naive: datetime, resolved: ResolvedTimezone
) -> datetime:
    """Attach the resolved timezone to an already-structured naive datetime.

    Not a natural-language parser: the caller is responsible for turning
    "domani alle 15" into a naive `datetime` first. This only performs the
    final, deterministic localization step, DST-aware via `zoneinfo`.
    """
    if naive.tzinfo is not None:
        return naive
    return naive.replace(tzinfo=ZoneInfo(resolved.tz_name))
