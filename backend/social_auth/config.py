"""Environment configuration for social auth (no secrets logged)."""
from __future__ import annotations

import os
from typing import Any


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def google_audiences() -> list[str]:
    """Accepted Google ID token audiences (client IDs)."""
    ids: list[str] = []
    for key in (
        "GOOGLE_WEB_CLIENT_ID",
        "GOOGLE_IOS_CLIENT_ID",
        "GOOGLE_ANDROID_CLIENT_ID",
    ):
        v = _env(key)
        if v and v not in ids:
            ids.append(v)
    # Optional comma-separated extras
    extra = _env("GOOGLE_ALLOWED_CLIENT_IDS")
    if extra:
        for part in extra.split(","):
            p = part.strip()
            if p and p not in ids:
                ids.append(p)
    return ids


def google_configured() -> bool:
    return bool(google_audiences())


def apple_client_ids() -> list[str]:
    """Audiences for Apple identity tokens (bundle id and/or Services ID)."""
    ids: list[str] = []
    for key in ("APPLE_CLIENT_ID", "APPLE_SERVICE_ID", "APPLE_BUNDLE_ID"):
        v = _env(key)
        if v and v not in ids:
            ids.append(v)
    return ids


def apple_configured() -> bool:
    # Verification of id_token needs at least one audience (client/service id).
    # Key material is required only for authorization-code exchange (web).
    return bool(apple_client_ids())


def apple_web_secret_ready() -> bool:
    return bool(
        _env("APPLE_TEAM_ID")
        and _env("APPLE_KEY_ID")
        and (_env("APPLE_PRIVATE_KEY_PATH") or _env("APPLE_PRIVATE_KEY"))
        and _env("APPLE_SERVICE_ID")
    )


def social_auth_status() -> dict[str, Any]:
    g_aud = google_audiences()
    a_ids = apple_client_ids()
    return {
        "google": {
            "configured": bool(g_aud),
            "audiences_configured": len(g_aud),
            "platforms": {
                "web": bool(_env("GOOGLE_WEB_CLIENT_ID")),
                "ios": bool(_env("GOOGLE_IOS_CLIENT_ID")),
                "android": bool(_env("GOOGLE_ANDROID_CLIENT_ID")),
            },
            "legacy_emergent": _env("EMERGENT_GOOGLE_AUTH").lower() in ("1", "true", "yes"),
        },
        "apple": {
            "configured": bool(a_ids),
            "audiences_configured": len(a_ids),
            "web_secret_ready": apple_web_secret_ready(),
            "platforms": {
                "ios_native": bool(_env("APPLE_CLIENT_ID") or _env("APPLE_BUNDLE_ID")),
                "web": bool(_env("APPLE_SERVICE_ID")),
                "android_web": bool(_env("APPLE_SERVICE_ID")),
            },
        },
        "password": {"configured": True},
    }
