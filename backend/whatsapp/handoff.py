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
from conversation_engine.ai_core.channel_actions import safe_ora_screen_path

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
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return _DEFAULT_ORA_WEB
    if (
        parsed.scheme == "https"
        and hostname
        and (
            hostname == "ora-web-production-fb67.up.railway.app"
            or hostname.endswith(".up.railway.app")
        )
        and not parsed.username and not parsed.password and port is None
        and parsed.path in ("", "/") and not parsed.query and not parsed.fragment
    ):
        return f"https://{hostname}"
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

    # A real open_navigation client action already contains the provider URL.
    # WhatsApp cannot auto-launch the phone's map app, but the link itself is
    # directly usable: never replace it with a generic ORA app deep link.
    app_required = False
    for action in (answer.get("client_actions") or [])[:4]:
        if not isinstance(action, dict):
            continue
        link = _safe_navigation(action.get("url"))
        if action.get("type") == "open_navigation" and link:
            add("Apri la navigazione", link)
        else:
            app_required = True
    # Other client actions still require consent or local device capabilities.
    if app_required:
        add("Per completare sul dispositivo, apri ORA", _app_conversation_url(answer))

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
        elif item.get("kind") == "ora_screen":
            # A new UI skill can open any safe ORA feature route without a
            # new hardcoded WhatsApp handler. The tool supplied a relative
            # in-app path, not an arbitrary provider URL or authorization.
            path = safe_ora_screen_path(item.get("path"))
            if path:
                label = str(item.get("label") or "Apri in ORA").strip()[:64]
                add(label or "Apri in ORA", f"{_app_origin()}{path}")
            else:
                add("Continua nella tua app ORA", _app_conversation_url(answer))
        else:
            # Unknown future visual actions never vanish silently. The
            # authenticated conversation remains the portable safe fallback.
            add("Continua nella tua app ORA", _app_conversation_url(answer))

    # Links are only handoffs; no WhatsApp webhook may silently perform a
    # client permission, device GPS acquisition or irreversible confirmation.
    if not text:
        if any(_safe_navigation(part.splitlines()[-1]) for part in rendered):
            text = (
                "Ho preparato il collegamento per la navigazione. "
                "L'app mappe userà la posizione del telefono quando la apri "
                "e mostrerà percorso e traffico aggiornati."
            )
        elif rendered:
            text = "Ho preparato il collegamento per proseguire."
        else:
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
