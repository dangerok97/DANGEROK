"""OAuth scopes for Google Calendar connector — MINIMAL set only."""

# Read-only. No write scope on purpose. Do NOT add mail, drive, contacts, etc.
GOOGLE_CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    # Explicit user identity so we can key ConnectorInstance by account.
    "openid",
    "email",
    "profile",
)

CAPABILITY_ID = "calendar.read"
CONNECTOR_ID = "calendar_google"
