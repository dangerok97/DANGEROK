"""Google Calendar connector package.

Two providers coexist:
  - RealGoogleCalendarProvider (HTTP against googleapis.com)
  - FakeGoogleCalendarProvider (in-memory, activated ONLY when
    CALENDAR_PROVIDER_MODE=fake)
The factory `build_calendar_provider()` selects one at import time and
raises `ProviderNotConfigured` when the real provider is requested but
credentials are missing.
"""
from .provider import (
    CalendarProviderProtocol,
    FakeGoogleCalendarProvider,
    ProviderNotConfigured,
    RealGoogleCalendarProvider,
    build_calendar_provider,
)
from .router import router as google_calendar_router
from .service import GoogleCalendarService

__all__ = [
    "CalendarProviderProtocol",
    "FakeGoogleCalendarProvider",
    "ProviderNotConfigured",
    "RealGoogleCalendarProvider",
    "build_calendar_provider",
    "google_calendar_router",
    "GoogleCalendarService",
]
