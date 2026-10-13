"""Authenticated account pairing + Meta-signed HTTPS webhook.

No ORA JWT is ever accepted on public provider callbacks; only Meta's signature
authenticates a webhook, and a separate one-time challenge associates a phone
with a specific user.
"""
from __future__ import annotations

import json
import logging
import hmac
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse

from deps import db, get_current_user
from whatsapp.cloud import CloudConfig, WhatsAppNotConfigured, iter_inbound_messages
from whatsapp.service import WhatsAppService

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
log = logging.getLogger("ora.whatsapp.webhook")


def _config() -> CloudConfig:
    try:
        return CloudConfig.load()
    except WhatsAppNotConfigured as exc:
        raise HTTPException(status_code=503, detail="WhatsApp non ancora configurato su ORA") from exc


@router.get("/status")
async def whatsapp_status(user=Depends(get_current_user)):
    """Never return provider credentials or unmasked phone numbers."""
    try:
        service = WhatsAppService(db)
        return await service.status(user["user_id"])
    except WhatsAppNotConfigured:
        return {
            "configured": False,
            "linked": False,
            "phone_last4": None,
            "display_number": None,
            "notifications_enabled": False,
            # Credentials are missing, but the shared AI catalog still exists.
            # This is not a claim that the provider transport is usable.
            "shared_ai_core": True,
            "shared_capability_count": None,
            "capability_contract_version": 1,
            "device_handoff_supported": True,
        }


@router.post("/link/start")
async def whatsapp_start_pairing(user=Depends(get_current_user)):
    return await WhatsAppService(db, _config()).issue_pairing_code(user["user_id"])


@router.delete("/link")
async def whatsapp_unlink(user=Depends(get_current_user)):
    from whatsapp.service import disconnect_account
    await disconnect_account(db, user["user_id"])
    return {"ok": True, "linked": False}


@router.get("/webhook", response_class=PlainTextResponse)
async def whatsapp_verify_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    # Meta's GET verification needs only the shared challenge token.
    # App Secret / access token are required for signed POST and replies,
    # but Meta can verify the callback before those credentials are ready.
    verify_token = (os.environ.get("WHATSAPP_VERIFY_TOKEN") or "").strip()
    if not verify_token:
        raise HTTPException(status_code=503, detail="whatsapp_verify_token_not_configured")
    if (
        hub_mode != "subscribe"
        or not hmac.compare_digest(verify_token, hub_verify_token)
        or not (1 <= len(hub_challenge) <= 512)
    ):
        raise HTTPException(status_code=403, detail="verification_failed")
    return PlainTextResponse(content=hub_challenge, status_code=200)


@router.post("/webhook")
async def whatsapp_receive_webhook(request: Request):
    config = _config()
    raw = await request.body()
    if len(raw) > 256 * 1024:
        raise HTTPException(status_code=413, detail="payload_too_large")
    if not config.verify_signature(raw, request.headers.get("x-hub-signature-256", "")):
        raise HTTPException(status_code=403, detail="signature_invalid")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="invalid_json")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_payload")
    svc = WhatsAppService(db, config)
    # Persist before acknowledging delivery; Meta retries on transient DB errors.
    # Duplicate Meta webhook deliveries are deduplicated by a stable message id.
    count = 0
    for message in iter_inbound_messages(payload, config.phone_number_id):
        if count >= 100:
            # Do not silently lose messages from an unexpectedly large webhook.
            raise HTTPException(status_code=413, detail="too_many_messages")
        await svc.persist_incoming(message)
        count += 1
    return Response(status_code=200)
