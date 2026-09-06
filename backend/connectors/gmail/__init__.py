"""Gmail — a mailbox read as a sensor. No send, no reply, no labels."""

from .scopes import (
    CAPABILITY_ID,
    CAPABILITY_READ_ID,
    CONNECTOR_ID,
    EMAIL_RECORD_TYPE,
    GMAIL_SCOPES,
)
from .router import router as gmail_router
from .service import GmailReadService

__all__ = [
    "CAPABILITY_ID",
    "CAPABILITY_READ_ID",
    "CONNECTOR_ID",
    "EMAIL_RECORD_TYPE",
    "GMAIL_SCOPES",
    "GmailReadService",
    "gmail_router",
]
