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
from pydantic import BaseModel

from deps import db, get_current_user
from whatsapp.cloud import (
    CloudConfig, WhatsAppNotConfigured,
    iter_inbound_messages, iter_signed_delivery_statuses,
)
from whatsapp.alerts import set_opt_in, set_detail_preference, record_status, template_settings
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
            "notifications_detail_enabled": False,
            "template_configured": False,
            "template_scope": None,
            "template_approval_status": "not_configured",
            "notification_channel_ready": False,
            # Credentials are missing, but the shared AI catalog still exists.
            # This is not a claim that the provider transport is usable.
            "shared_ai_core": True,
            "shared_capability_count": None,
            "capability_contract_version": 1,
            "device_handoff_supported": True,
        }


class NotificationConsentIn(BaseModel):
    enabled: bool


@router.put("/notifications")
async def set_whatsapp_notifications(
    body: NotificationConsentIn, user=Depends(get_current_user),
):
    """Opt in or revoke ORA proactive WhatsApp messages independently of pairing."""
    _config()
    try:
        return await set_opt_in(db, user["user_id"], body.enabled)
    except ValueError as exc:
        if str(exc) == "whatsapp_not_linked":
            raise HTTPException(status_code=409, detail="whatsapp_not_linked") from exc
        raise


@router.put("/notifications/details")
async def set_whatsapp_notification_details(
    body: NotificationConsentIn, user=Depends(get_current_user),
):
    """Owner opt-in for expanded copy, including private content on Meta."""
    _config()
    try:
        return await set_detail_preference(db, user["user_id"], body.enabled)
    except ValueError as exc:
        if str(exc) in ("whatsapp_not_linked", "whatsapp_alerts_not_enabled"):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise


@router.get("/notifications/history")
async def whatsapp_notification_history(user=Depends(get_current_user)):
    """Bounded owner-only provider delivery statuses; never expose message bodies."""
    owner = user["user_id"]
    cursor = db.whatsapp_alert_outbox.find(
        {"owner_id": owner}, {"_id": 0, "plan_id": 1, "status": 1,
                             "created_at": 1, "accepted_at": 1,
                             "meta_status_at": 1, "failure_code": 1},
    ).sort("created_at", -1).limit(20)
    return {"alerts": await cursor.to_list(20),
            "template_configured": bool(template_settings())}


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
    # Meta reports outgoing message receipt states in the *same signed
    # webhook*, but they are not new inbound conversations.
    for receipt in iter_signed_delivery_statuses(payload, config.phone_number_id):
        await record_status(db, config, receipt)
    return Response(status_code=200)
