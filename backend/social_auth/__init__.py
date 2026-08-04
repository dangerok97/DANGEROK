"""First-party Google / Apple identity verification for ORA."""

from .config import social_auth_status
from .migrate import ensure_identity_indexes, migrate_password_identities
from .service import SocialAuthService

__all__ = [
    "SocialAuthService",
    "social_auth_status",
    "ensure_identity_indexes",
    "migrate_password_identities",
]
