"""Apple Calendar connector — identifiers, feature flag and scopes."""
from __future__ import annotations

import os

APPLE_CALENDAR_CONNECTOR_ID = "calendar_apple"
APPLE_CALENDAR_CAPABILITY_ID = "calendar.read"

# Apple has no OAuth scopes — permission is granted natively by EventKit
# on the device. We record a symbolic scope string so audit logs remain
# consistent with the OAuth-based connectors.
APPLE_CALENDAR_SCOPES = ("apple.eventkit.calendar.readonly",)


def is_apple_calendar_enabled() -> bool:
    """Master feature flag. Defaults to FALSE — the connector must be
    explicitly enabled at deploy time before any endpoint becomes usable.

    Reads `APPLE_CALENDAR_ENABLED` from the environment. Accepts:
    "1", "true", "yes", "on" (case-insensitive)."""
    return os.environ.get("APPLE_CALENDAR_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on",
    )
