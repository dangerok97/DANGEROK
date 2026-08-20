"""Calendar consent check — thin, non-HTTP-coupled wrapper reusable by a
future AI Core calendar capability handler (which receives `db`/`user_id`
from `runtime`, not a FastAPI `Request`).

Does NOT introduce a second permission system: this only fixes the correct
`capability_id`/`connector_id` constants and calls the existing, generic
`PermissionService.check_access`/`require_access` — the same mechanism
already used by `permissions.guard.require_capability` for HTTP routes.
"""
from __future__ import annotations

from permissions.errors import CapabilityDisabled, CapabilityUnknown, ConsentDenied
from permissions.models import INSTANCE_WILDCARD
from permissions.service import PermissionService

from .scopes import CAPABILITY_ID as CALENDAR_READ_CAPABILITY_ID
from .scopes import CAPABILITY_WRITE_ID as CALENDAR_WRITE_CAPABILITY_ID
from .scopes import CONNECTOR_ID


async def calendar_consent_granted(
    db, *, user_id: str, write: bool, connector_instance_id: str = INSTANCE_WILDCARD
) -> bool:
    """Bounded, user-scoped check. No OAuth/network call — reads consent
    state already persisted by the OAuth callback flow."""
    if not user_id:
        return False
    capability_id = CALENDAR_WRITE_CAPABILITY_ID if write else CALENDAR_READ_CAPABILITY_ID
    return await PermissionService(db).check_access(
        user_id=user_id,
        capability_id=capability_id,
        connector_id=CONNECTOR_ID,
        connector_instance_id=connector_instance_id,
    )


async def require_calendar_consent(
    db, *, user_id: str, write: bool, connector_instance_id: str = INSTANCE_WILDCARD
) -> None:
    """Raises `permissions.errors.ConsentDenied` (or `CapabilityDisabled` /
    `CapabilityUnknown`) when access is not currently granted. Callers in a
    non-HTTP context (e.g. a future AI Core tool handler) should catch these
    directly rather than expecting an HTTPException."""
    capability_id = CALENDAR_WRITE_CAPABILITY_ID if write else CALENDAR_READ_CAPABILITY_ID
    await PermissionService(db).require_access(
        user_id=user_id,
        capability_id=capability_id,
        connector_id=CONNECTOR_ID,
        connector_instance_id=connector_instance_id,
    )


__all__ = [
    "calendar_consent_granted",
    "require_calendar_consent",
    "CapabilityDisabled",
    "CapabilityUnknown",
    "ConsentDenied",
]
