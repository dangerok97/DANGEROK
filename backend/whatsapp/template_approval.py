"""Fail-closed validation of approved UTILITY alerts with one detail parameter.

A template name stored in Railway is not proof that Meta approved it. Check
the *real* WhatsApp Business Account with the existing system-user token.
Only a BODY template with exactly one {{1}} slot can send an informative
out-of-window alert. Unsupported parameters fail closed, as do unapproved
templates. Do not expose tokens or Meta error bodies.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

import httpx

from whatsapp.cloud import CloudConfig

_CACHE: dict[tuple[str, ...], tuple[float, str]] = {}
_WABA_ID = re.compile(r"[0-9]{5,30}\Z")
_VARIABLE = re.compile(r"\{\{[^{}]*\}\}")


async def approval_status(
    config: CloudConfig | None = None,
    *, use_cache: bool = True,
) -> str:
    """approved_dynamic | approved (static) | not_configured | pending |
    rejected | paused | wrong_category | requires_parameters | not_found |
    waba_not_configured | unverified.

    Only approved_dynamic permits an informative proactive alert; proof
    that Meta accepted or delivered a particular message.
    """
    from whatsapp.alerts import template_settings

    template = template_settings()
    if not template:
        return "not_configured"
    waba = (os.environ.get("WHATSAPP_WABA_ID") or "").strip()
    if not _WABA_ID.fullmatch(waba):
        return "waba_not_configured"
    try:
        cfg = config or CloudConfig.load()
    except Exception:
        return "unverified"
    name, language = template
    key = (
        cfg.version, waba, name, language,
        hashlib.sha256(cfg.access_token.encode("utf-8")).hexdigest()[:16],
    )
    now = time.monotonic()
    cached = _CACHE.get(key)
    if use_cache and cached and now < cached[0]:
        return cached[1]

    status = "unverified"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0), follow_redirects=False
        ) as client:
            response = await client.get(
                f"https://graph.facebook.com/{cfg.version}/{waba}/message_templates",
                headers={"Authorization": f"Bearer {cfg.access_token}"},
                params={
                    "name": name,
                    "fields": "name,language,status,category,components",
                    "limit": 25,
                },
            )
            if response.status_code != 200:
                status = "unverified"
            else:
                payload = response.json()
                templates = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(templates, list):
                    status = "unverified"
                else:
                    matches = [
                        row for row in templates if isinstance(row, dict)
                        and row.get("name") == name
                        and row.get("language") == language
                    ]
                    if not matches:
                        status = "not_found"
                    else:
                        row = matches[0]
                        meta_status = str(row.get("status") or "").upper()
                        if meta_status != "APPROVED":
                            status = {
                                "PENDING": "pending", "IN_APPEAL": "pending",
                                "REJECTED": "rejected", "PAUSED": "paused",
                                "DISABLED": "paused",
                            }.get(meta_status, "unverified")
                        elif str(row.get("category") or "").upper() != "UTILITY":
                            # A marketing/authentication category cannot be
                            # used for ORA's operational reminder opt-in.
                            status = "wrong_category"
                        else:
                            components = row.get("components")
                            if not isinstance(components, list):
                                status = "unverified"
                            else:
                                body = next(
                                    (part for part in components
                                     if isinstance(part, dict)
                                     and part.get("type") == "BODY"),
                                    None,
                                )
                                media_required = any(
                                    isinstance(part, dict)
                                    and part.get("type") == "HEADER"
                                    and str(part.get("format") or "").upper()
                                    in ("IMAGE", "VIDEO", "DOCUMENT", "LOCATION")
                                    for part in components
                                )
                                if not isinstance(body, dict) or not str(body.get("text") or "").strip():
                                    status = "requires_parameters"
                                elif media_required:
                                    status = "requires_parameters"
                                else:
                                    body_text = str(body["text"])
                                    # Meta's one approved BODY variable lets us
                                    # show the actual update, without interpolating
                                    # unreviewed headers, buttons, or media.
                                    mentions = _VARIABLE.findall(
                                        json.dumps(components, ensure_ascii=False)
                                    )
                                    slots = _VARIABLE.findall(body_text)
                                    outside = [
                                        part for part in components
                                        if isinstance(part, dict) and part is not body
                                    ]
                                    outside_text = json.dumps(outside, ensure_ascii=False)
                                    if (slots == ["{{1}}"]
                                        and mentions == ["{{1}}"]
                                        and "{{" not in body_text.replace("{{1}}", "")
                                        and "}}" not in body_text.replace("{{1}}", "")
                                        and "{{" not in outside_text
                                        and "}}" not in outside_text):
                                        status = "approved_dynamic"
                                    elif "{{" in json.dumps(components, ensure_ascii=False):
                                        status = "requires_parameters"
                                    else:
                                        status = "approved"
    except (httpx.RequestError, ValueError, TypeError, OSError):
        status = "unverified"
    _CACHE[key] = (time.monotonic() + (300 if status in ("approved", "approved_dynamic") else 30), status)
    # Keep only a small set of recent template fingerprints in memory.
    if len(_CACHE) > 32:
        for old_key in list(_CACHE)[:16]:
            _CACHE.pop(old_key, None)
    return status
