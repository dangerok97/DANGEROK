"""Portable ORA UI handoffs emitted by verified AI Core tool observations.

Adding an AI skill requires registering it only once in ToolRegistry.
If its result needs a UI screen, the skill can emit:
  observation.payload.ui_action = {
      "kind": "ora_screen", "path": "/vision-xray", "label": "Visione esplosa"
  }

The core, app and WhatsApp share this representation; WhatsApp needs no
per-skill action handler. This is a *handoff* to the signed-in app, NOT
remote access to hardware or bypass of any permission/approval.
"""
from __future__ import annotations

import re
from typing import Any


_MAX_PATH = 240
_MAX_LABEL = 64
_PATH_SEGMENT = re.compile(r"[A-Za-z0-9_-]{1,90}\Z")
# These paths are not feature surfaces. They carry authentication, account
# changes or session setup and should never be manufactured by a skill.
_NON_FEATURE_ROOTS = frozenset({
    "api", "account", "login", "google-auth-complete",
    "connect-apple-calendar", "collega-conto", "privacy", "terms",
})


def safe_ora_screen_path(raw: Any) -> str | None:
    """Accept plain relative feature paths only (no scheme, query, encoding)."""
    if not isinstance(raw, str) or not raw.startswith("/") or len(raw) > _MAX_PATH:
        return None
    if raw.startswith("//") or any(c in raw for c in "\\?&#%:\r\n\t"):
        return None
    parts = raw[1:].split("/")
    if not 1 <= len(parts) <= 5 or any(not _PATH_SEGMENT.fullmatch(p) for p in parts):
        return None
    if parts[0].lower() in _NON_FEATURE_ROOTS:
        return None
    return raw


def portable_ui_action(raw: Any) -> dict | None:
    """Normalize actions, falling back to the authenticated ORA conversation.

    Unknown future UI kinds do not silently disappear from WhatsApp. They
    cannot, however, be interpreted as successful actions or as openable
    external URLs.
    """
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip()
    if not kind:
        return None

    if kind == "ora_screen":
        path = safe_ora_screen_path(raw.get("path"))
        if path:
            label = str(raw.get("label") or "Apri in ORA").strip()[:_MAX_LABEL]
            return {"kind": "ora_screen", "path": path, "label": label or "Apri in ORA"}
        return {"kind": "app_handoff", "label": "Apri la funzione in ORA"}

    if kind == "app_handoff":
        return {"kind": "app_handoff", "label": "Apri in ORA"}

    # Unknown UI kinds are not links and must never carry arbitrary untrusted
    # urls into the client. The user can continue the current owned session
    # in the full app if the channel does not know this visualization.
    return {"kind": "app_handoff", "label": "Apri la funzione in ORA"}
