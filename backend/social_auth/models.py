"""Typed shapes for verified provider claims and identity docs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


PROVIDERS = frozenset({"password", "google", "apple"})


@dataclass(frozen=True)
class VerifiedIdentity:
    provider: str
    subject: str
    email: Optional[str]
    email_verified: bool
    display_name: Optional[str]
    avatar_url: Optional[str]
    nonce: Optional[str] = None


def identity_public(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc.get("id"),
        "provider": doc.get("provider"),
        "email": doc.get("email"),
        "email_verified": bool(doc.get("email_verified")),
        "display_name": doc.get("display_name"),
        "avatar_url": doc.get("avatar_url"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "last_login_at": doc.get("last_login_at"),
        # never expose provider_subject to clients that don't need it for UI;
        # settings may show linked status without the raw sub.
        "linked": True,
    }
