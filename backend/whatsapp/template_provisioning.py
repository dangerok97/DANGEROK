"""Operator-only Meta template review workflow.

This module is not imported by the WhatsApp webhook or worker. It has no
background mutation, no token in source control, and never sends a WhatsApp
message. An operator must explicitly invoke 'submit --confirm-request' from
an environment that already holds the server-side Meta credentials.

The template is scoped to a user-requested recurring reminder. A generic
placeholder for arbitrary AI-generated alerts is NOT a Utility contract.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from typing import Any

import httpx

TEMPLATE_NAME = "ora_promemoria_ricorrente_v1"
TEMPLATE_LANGUAGE = "it"
TEMPLATE_SCOPE = "recurring_memo"
TEMPLATE_BODY = (
    "ORA ti ricorda una ricorrenza che hai salvato: {{1}}. "
    "Puoi modificare o interrompere il promemoria nelle impostazioni di ORA."
)
EXAMPLE_TEXT = "Domani ricorre un anniversario che hai salvato in ORA."
_WABA_ID = re.compile(r"[0-9]{5,30}\Z")


def review_payload() -> dict[str, Any]:
    """Exact non-personal example that Meta may review; approval is not assumed."""
    assert TEMPLATE_BODY.count("{{1}}") == 1
    assert not TEMPLATE_BODY.startswith("{{1}}")
    assert not TEMPLATE_BODY.endswith("{{1}}")
    return {
        "name": TEMPLATE_NAME,
        "language": TEMPLATE_LANGUAGE,
        "category": "UTILITY",
        "allow_category_change": False,
        "components": [{
            "type": "BODY",
            "text": TEMPLATE_BODY,
            "example": {"body_text": [[EXAMPLE_TEXT]]},
        }],
    }


def validate_environment(*, live: bool) -> None:
    """Require an explicit scope and exact configured template before a Meta call."""
    if not live:
        return
    from whatsapp.alerts import template_settings
    if template_settings() != (TEMPLATE_NAME, TEMPLATE_LANGUAGE):
        raise ValueError("template_name_language_or_scope_not_configured")
    if os.environ.get("WHATSAPP_ALERT_TEMPLATE_SCOPE", "").strip() != TEMPLATE_SCOPE:
        raise ValueError("template_scope_not_configured")
    if not _WABA_ID.fullmatch((os.environ.get("WHATSAPP_WABA_ID") or "").strip()):
        raise ValueError("waba_not_configured")


async def inspect_status() -> dict[str, Any]:
    """Read-only Meta verification; expose no provider details beyond status."""
    validate_environment(live=True)
    from whatsapp.cloud import CloudConfig
    from whatsapp.template_approval import approval_status
    status = await approval_status(CloudConfig.load(), use_cache=False)
    return {"template": TEMPLATE_NAME, "scope": TEMPLATE_SCOPE, "status": status}


async def request_review(*, confirm: bool = False) -> dict[str, Any]:
    """Idempotent submission: only a verifiable not-found can become a POST."""
    if not confirm:
        raise ValueError("explicit_review_confirmation_required")
    validate_environment(live=True)
    from whatsapp.cloud import CloudConfig
    cfg = CloudConfig.load()
    status = (await inspect_status())["status"]
    if status != "not_found":
        return {
            "requested": False, "template": TEMPLATE_NAME,
            "status": status, "reason": "existing_or_unverifiable_template",
        }

    waba = os.environ["WHATSAPP_WABA_ID"].strip()
    endpoint = f"https://graph.facebook.com/{cfg.version}/{waba}/message_templates"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0), follow_redirects=False
        ) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {cfg.access_token}",
                         "Content-Type": "application/json"},
                json=review_payload(),
            )
    except httpx.RequestError:
        # An unknown acceptance state must never trigger a blind second POST.
        return {"requested": False, "template": TEMPLATE_NAME,
                "status": "acceptance_unknown", "reason": "network_uncertain"}

    if response.status_code >= 400:
        code = None
        try:
            value = (response.json().get("error") or {}).get("code")
            if type(value) is int and 0 <= value <= 9999999:
                code = value
        except (ValueError, TypeError, AttributeError):
            pass
        # Do not print Meta's freeform error: it can contain private context.
        return {
            "requested": False, "template": TEMPLATE_NAME,
            "status": "rejected_by_api", "http_status": response.status_code,
            "meta_code": code,
        }

    try:
        body = response.json()
    except (ValueError, TypeError):
        body = {}
    raw_status = body.get("status") if isinstance(body, dict) else None
    status = raw_status if raw_status in ("PENDING", "APPROVED", "REJECTED") else "acceptance_unknown"
    # HTTP success is not proof of template approval.
    return {"requested": status != "acceptance_unknown",
            "template": TEMPLATE_NAME, "status": status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ORA recurring reminder template operator")
    parser.add_argument("action", choices=("preview", "inspect", "submit"))
    parser.add_argument("--confirm-request", action="store_true",
                        help="Explicitly submit one Meta review request (no recipient sends)")
    args = parser.parse_args(argv)
    try:
        if args.action == "preview":
            result = review_payload()
        elif args.action == "inspect":
            result = asyncio.run(inspect_status())
        else:
            result = asyncio.run(request_review(confirm=args.confirm_request))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.action == "submit" and result.get("status") in (
            "acceptance_unknown", "rejected_by_api", "unverified"
        ):
            return 2
        return 0
    except Exception as exc:
        # Only safe error categories. Never show token, provider response or DB.
        print(json.dumps({"ok": False, "reason": type(exc).__name__,
                          "detail": str(exc) if isinstance(exc, ValueError) else None}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
