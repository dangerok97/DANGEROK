"""Present existing ORA AI Core actions in WhatsApp without reexecuting tools.

The app and WhatsApp share AICoreOrchestrator and an owner-scoped account.
This adapter does not interpret the user's intention: it makes actions already
produced by real ORA skills usable as safe links on a text-only channel.
"""
from __future__ import annotations

import os
import re
from urllib.parse import quote, urlparse, parse_qs

from whatsapp.formatting import render_whatsapp_answer

# Trusted ORA web deployment. Other arbitrary environment URLs are never
# interpolated into a WhatsApp link sent to a third party.
_DEFAULT_ORA_WEB = "https://ora-web-production-fb67.up.railway.app"
_ALLOWED_MAP_HOSTS = frozenset((
    "www.google.com", "maps.google.com", "maps.apple.com",
    "waze.com", "www.waze.com",
))
_SAFE_SESSION = re.compile(r"ces_[a-zA-Z0-9_-]{8,76}\Z")
_SAFE_PLAN = re.compile(r"lop_[a-zA-Z0-9_-]{4,76}\Z")


def _app_origin() -> str:
    value = (os.environ.get("WHATSAPP_ORA_WEB_URL") or _DEFAULT_ORA_WEB).strip()
    parsed = urlparse(value)
    if (
        parsed.scheme == "https"
        and parsed.hostname
        and (
            parsed.hostname == "ora-web-production-fb67.up.railway.app"
            or parsed.hostname.endswith(".up.railway.app")
        )
        and not parsed.username and not parsed.password and not parsed.port
        and parsed.path in ("", "/") and not parsed.query and not parsed.fragment
    ):
        return f"https://{parsed.hostname}"
    return _DEFAULT_ORA_WEB


def _safe_navigation(url: str) -> str | None:
    if not isinstance(url, str) or not url or len(url) > 1200:
        return None
    try:
        parsed = urlparse(url)
        if (
            parsed.scheme == "https" and parsed.hostname in _ALLOWED_MAP_HOSTS
            and not parsed.username and not parsed.password and parsed.port is None
        ):
            return url
    except ValueError:
        pass
    return None


def _safe_amazon(url: str) -> str | None:
    if not isinstance(url, str) or len(url) > 600:
        return None
    try:
        parsed = urlparse(url)
        if (
            parsed.scheme == "https" and parsed.hostname == "www.amazon.it"
            and not parsed.username and not parsed.password and parsed.port is None
            and parsed.path == "/s" and parse_qs(parsed.query).get("k")
        ):
            return url
    except ValueError:
        pass
    return None


def _app_conversation_url(answer: dict) -> str:
    session = str(answer.get("session_id") or "")
    if _SAFE_SESSION.fullmatch(session):
        return f"{_app_origin()}/ora/{quote(session, safe='')}"
    # Authenticated homepage, not an invented anonymous session.
    return _app_origin()


def render_core_answer_for_whatsapp(answer: dict) -> str:
    """Project verified AI Core results into one safe, readable WA message.

    No duplicate execution, no confirmation bypass, no raw DB refs in URLs.
    The app link still requires the user to sign into their ORA account.
    """
    text = render_whatsapp_answer(answer.get("ora_text") or answer.get("question"))
    rendered: list[str] = []
    seen: set[str] = set()

    def add(label: str, url: str | None) -> None:
        if url and url not in seen and len(rendered) < 3:
            seen.add(url)
            # A clickable URL needs to stand on its own line in WhatsApp.
            rendered.append(f"{label}:\n{url}")

    for item in (answer.get("navigation") or [])[:3]:
        if isinstance(item, dict):
            link = _safe_navigation(item.get("url"))
            if link:
                label = str(item.get("label") or "Apri mappa").strip()[:45]
                add(label, link)

    for item in (answer.get("ui_actions") or [])[:3]:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "amazon_search":
            add("Apri ricerca Amazon", _safe_amazon(item.get("url")))
        elif item.get("kind") == "workspace":
            plan = str(item.get("plan_id") or "")
            if _SAFE_PLAN.fullmatch(plan):
                add("Apri il piano in ORA", f"{_app_origin()}/goal-workspace/{quote(plan, safe='')}")

    # These are client-device capabilities (GPS, app-specific permissions),
    # not authorization to silently execute them from a WhatsApp webhook.
    # Never imply the tool has completed because a link was created.
    if answer.get("client_actions"):
        add("Per completare sul dispositivo, apri ORA", _app_conversation_url(answer))

    if not text:
        text = "Ho ricevuto il messaggio, ma non ho ancora una risposta verificata."
    # Do not add a URL already supplied naturally by the model's text.
    rendered = [item for item in rendered if item.split("\n")[-1] not in text]
    output = (text + "\n\n" + "\n\n".join(rendered)).strip() if rendered else text
    if len(output) > 3900:
        # Long AI replies should remain accessible in full, not be silently
        # truncated before their action URLs by the Cloud API text limit.
        return (
            output[:3600].rstrip()
            + "\n\n[Messaggio abbreviato. Leggi la risposta completa in ORA:]\n"
            + _app_conversation_url(answer)
        )
    return output
