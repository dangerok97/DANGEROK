"""OAuth scopes for Google Calendar connector — minimal set for sync."""

# Write events ORA creates/updates/deletes + list calendars for selection.
# Login Google (ID token) does NOT use these scopes.
GOOGLE_CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "openid",
    "email",
    "profile",
)

# Legacy read-only scopes (inbound polling still works with events scope).
GOOGLE_CALENDAR_READ_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
)

CAPABILITY_ID = "calendar.read"
CAPABILITY_WRITE_ID = "calendar.write"
CONNECTOR_ID = "calendar_google"
