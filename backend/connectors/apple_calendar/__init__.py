"""Apple Calendar connector package.

Read-only EventKit connector for iOS/iPadOS. Unlike the Google Calendar
connector, ORA does NOT talk to any remote server here: the source of
truth lives on the user's device and the mobile client uploads a
sanitized batch via `POST /instances/{id}/sync`.

Behind feature flag `APPLE_CALENDAR_ENABLED=false` by default.
Cross-provider deduplication (Google ↔ Apple) is implemented in
`ingestion.cross_provider.CrossProviderDedupService` and follows the
"first-write wins" strategy — new sources are attached as mirrored
sources on the existing life-graph node, never as new nodes.
"""
from .router import router as apple_calendar_router
from .scopes import (
    APPLE_CALENDAR_CAPABILITY_ID,
    APPLE_CALENDAR_CONNECTOR_ID,
    APPLE_CALENDAR_SCOPES,
    is_apple_calendar_enabled,
)
from .service import AppleCalendarService

__all__ = [
    "apple_calendar_router",
    "AppleCalendarService",
    "APPLE_CALENDAR_CAPABILITY_ID",
    "APPLE_CALENDAR_CONNECTOR_ID",
    "APPLE_CALENDAR_SCOPES",
    "is_apple_calendar_enabled",
]
