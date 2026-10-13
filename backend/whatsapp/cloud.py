"""Official Meta WhatsApp Cloud API transport. Never store tokens or log phone numbers."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass

import httpx
from cryptography.fernet import Fernet


class WhatsAppNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class CloudConfig:
    app_secret: str
    verify_token: str
    access_token: str
    phone_number_id: str
    data_key: str
    version: str
    display_number: str

    @classmethod
    def load(cls) -> "CloudConfig":
        get = lambda name: (os.environ.get(name) or "").strip()
        values = [get(k) for k in (
            "WHATSAPP_APP_SECRET", "WHATSAPP_VERIFY_TOKEN",
            "WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_DATA_KEY",
        )]
        if not all(values):
            raise WhatsAppNotConfigured("WhatsApp Cloud API credentials are incomplete")
        version = get("WHATSAPP_GRAPH_VERSION") or "v26.0"
        if not re.fullmatch(r"v[0-9]{1,2}\.[0-9]{1,2}", version):
            raise WhatsAppNotConfigured("Invalid WhatsApp Graph API version")
        try:
            Fernet(values[4].encode("ascii"))
        except Exception as exc:
            raise WhatsAppNotConfigured("WHATSAPP_DATA_KEY must be a Fernet key") from exc
        if not re.fullmatch(r"[0-9]{5,30}", values[3]):
            raise WhatsAppNotConfigured("Invalid WhatsApp phone number ID")
        display = re.sub(r"[\s()+-]", "", get("WHATSAPP_DISPLAY_NUMBER"))
        if display and not re.fullmatch(r"[0-9]{7,15}", display):
            raise WhatsAppNotConfigured("Invalid display number")
        return cls(*values, version, display)

    @classmethod
    def available(cls) -> bool:
        try:
            cls.load()
            return True
        except WhatsAppNotConfigured:
            return False

    def crypto(self) -> Fernet:
        return Fernet(self.data_key.encode("ascii"))

    def fingerprint(self, prefix: str, value: str) -> str:
        return hmac.new(self.data_key.encode("ascii"), f"{prefix}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()

    def encrypt(self, value: str) -> str:
        return self.crypto().encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        return self.crypto().decrypt(value.encode("ascii")).decode("utf-8")

    def verify_signature(self, payload: bytes, header: str) -> bool:
        expected = "sha256=" + hmac.new(self.app_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return bool(header) and hmac.compare_digest(expected, header)

    def verify_challenge(self, mode: str, token: str) -> bool:
        return mode == "subscribe" and hmac.compare_digest(self.verify_token, token)

    async def send_text(self, recipient: str, text: str, *, context_id: str | None = None) -> None:
        if not re.fullmatch(r"[1-9][0-9]{6,14}", recipient):
            raise ValueError("Invalid WhatsApp recipient")
        if not text.strip():
            raise ValueError("WhatsApp reply cannot be blank")
        # Cloud API text limit 4096 chars; ensure the user knows a reply was shortened.
        body = text if len(text) <= 4000 else text[:3960].rstrip() + "\n\n[Messaggio abbreviato: apri ORA per il testo completo.]"
        data: dict = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
        if context_id and len(context_id) <= 200:
            data["context"] = {"message_id": context_id}
        url = f"https://graph.facebook.com/{self.version}/{self.phone_number_id}/messages"
        async with httpx.AsyncClient(timeout=httpx.Timeout(18.0)) as client:
            response = await client.post(url, headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }, json=data)
        if response.status_code >= 400:
            # Meta may echo recipient, message content or authorization context
            # in free-form error fields. Keep ONLY bounded numeric diagnostics.
            error_code = None
            error_subcode = None
            try:
                api_error = response.json().get("error") or {}
                if isinstance(api_error, dict):
                    for name in ("code", "error_subcode"):
                        value = api_error.get(name)
                        parsed = int(value) if isinstance(value, int) and not isinstance(value, bool) else None
                        if parsed is not None and 0 <= parsed <= 9999999:
                            if name == "code":
                                error_code = parsed
                            else:
                                error_subcode = parsed
            except (ValueError, TypeError, AttributeError):
                pass
            raise CloudSendError(response.status_code, error_code, error_subcode)
        try:
            parsed = response.json()
            if not parsed.get("messages"):
                raise CloudSendError(502)
        except (json.JSONDecodeError, ValueError) as exc:
            raise CloudSendError(502) from exc



    async def send_proactive(
        self, recipient: str, *, message: str = "",
        template: tuple[str, str] | tuple[str, str, str] | None = None,
    ) -> str:
        """Return Meta message id for a permitted alert; not proof of delivery.

        A registered approved template is required outside the customer
        service window. The owner-scoped worker verifies APPROVED, UTILITY
        and the exact single-body-variable contract before this function binds
        the verified summary to that slot. No unverified components.
        """
        if not re.fullmatch(r"[1-9][0-9]{6,14}", recipient):
            raise ValueError("invalid_whatsapp_recipient")
        data = {"messaging_product": "whatsapp",
                "recipient_type": "individual", "to": recipient}
        if template is not None:
            if len(template) not in (2, 3):
                raise ValueError("invalid_template_shape")
            name, language = template[:2]
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,120}", name) or not re.fullmatch(
                r"[a-z]{2}(?:_[A-Z]{2})?", language
            ):
                raise ValueError("invalid_approved_template_reference")
            payload = {"name": name, "language": {"code": language}}
            if len(template) == 3:
                detail = template[2]
                if (
                    not isinstance(detail, str)
                    or not detail.strip() or len(detail) > 500
                    or "{{" in detail or "}}" in detail
                    or any(ord(ch) < 32 and ch not in "\n\t" for ch in detail)
                ):
                    raise ValueError("invalid_template_detail_parameter")
                payload["components"] = [{
                    "type": "body", "parameters": [{"type": "text", "text": detail}]
                }]
            data.update({"type": "template", "template": payload})
        else:
            if not isinstance(message, str) or not message.strip():
                raise ValueError("empty_alert")
            data.update({
                "type": "text",
                "text": {"preview_url": False, "body": message[:4000]},
            })
        url = f"https://graph.facebook.com/{self.version}/{self.phone_number_id}/messages"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(18.0)) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                    },
                    json=data,
                )
        except httpx.RequestError as exc:
            # Acceptance is unknown after a network failure. Never blind retry.
            raise CloudSendError(502) from exc
        if response.status_code >= 400:
            code = None
            subcode = None
            try:
                raw = response.json().get("error") or {}
                if isinstance(raw, dict):
                    for field in ("code", "error_subcode"):
                        val = raw.get(field)
                        if isinstance(val, int) and not isinstance(val, bool) and 0 <= val <= 9999999:
                            if field == "code":
                                code = val
                            else:
                                subcode = val
            except (ValueError, TypeError, AttributeError):
                pass
            raise CloudSendError(response.status_code, code, subcode)
        try:
            messages = response.json().get("messages") or []
            mid = messages[0].get("id") if isinstance(messages[0], dict) else None
            if not isinstance(mid, str) or not mid.startswith("wamid.") or len(mid) > 220:
                raise ValueError("invalid_meta_message_id")
            return mid
        except (ValueError, TypeError, IndexError, AttributeError) as exc:
            # A 200 with unparseable body might still have been accepted:
            # the worker must mark acceptance_unknown, not resend.
            raise CloudSendError(502) from exc


class CloudSendError(Exception):
    """Safe Meta failure diagnostics; never retain error text or the raw body."""

    def __init__(self, status: int, code: int | None = None, subcode: int | None = None):
        self.status = status
        self.code = code
        self.subcode = subcode
        super().__init__(f"Meta Cloud API HTTP {status}, code {code}, subcode {subcode}")


def iter_inbound_messages(payload: dict, expected_phone_number_id: str):
    """Only new inbound messages for our own business number, never status events."""
    if payload.get("object") != "whatsapp_business_account":
        return
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []):
            if not isinstance(change, dict) or change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata") or {}
            if metadata.get("phone_number_id") != expected_phone_number_id:
                continue
            for message in value.get("messages") or []:
                if not isinstance(message, dict):
                    continue
                mid = message.get("id")
                sender = message.get("from")
                if not isinstance(mid, str) or not (8 <= len(mid) <= 200):
                    continue
                if not isinstance(sender, str) or not re.fullmatch(r"[1-9][0-9]{6,14}", sender):
                    continue
                kind = str(message.get("type") or "")[:32]
                body = ""
                media = None
                if kind == "text" and isinstance(message.get("text"), dict):
                    body = str((message["text"] or {}).get("body") or "")
                elif kind in ("image", "document", "audio") and isinstance(message.get(kind), dict):
                    incoming_media = message[kind]
                    media_id = incoming_media.get("id")
                    if isinstance(media_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{8,180}", media_id):
                        media = {
                            "id": media_id,
                            "mime_type": str(incoming_media.get("mime_type") or "")[:120],
                            "filename": str(incoming_media.get("filename") or "")[:200],
                        }
                        body = str(incoming_media.get("caption") or "")[:2400]
                elif kind == "location" and isinstance(message.get("location"), dict):
                    incoming_location = message["location"]
                    try:
                        lat = float(incoming_location["latitude"])
                        lon = float(incoming_location["longitude"])
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            # A shared pin is user-provided, never a live GPS permission.
                            body = (
                                "Ti condivido un punto sulla mappa WhatsApp "
                                f"(non posizione GPS in tempo reale): {lat:.6f}, {lon:.6f}."
                            )
                            label = str(incoming_location.get("name") or "").strip()[:120]
                            if label:
                                body += " Etichetta fornita: " + label
                    except (ValueError, TypeError, KeyError):
                        pass
                elif kind == "button" and isinstance(message.get("button"), dict):
                    body = str((message["button"] or {}).get("text") or "")[:400]
                elif kind == "interactive" and isinstance(message.get("interactive"), dict):
                    interactive = message["interactive"]
                    reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
                    if isinstance(reply, dict):
                        body = str(reply.get("title") or "")[:400]
                if not isinstance(body, str):
                    body = ""
                # A delayed AI worker must never artificially reopen Meta's
                # 24-hour conversation window. Carry the signed sender time.
                raw_time = message.get("timestamp")
                if (
                    not isinstance(raw_time, str)
                    or not raw_time.isascii()
                    or not re.fullmatch(r"[1-9][0-9]{8,11}", raw_time)
                ):
                    raw_time = None
                yield {
                    "id": mid, "from": sender, "type": kind,
                    "text": body[:8000], "media": media,
                    "sent_at": int(raw_time) if raw_time is not None else None,
                }



def iter_signed_delivery_statuses(payload: dict, expected_phone_number_id: str):
    """Read Meta receipt events from the same *signed* WhatsApp webhook.

    This yields no freeform error details, recipient names, or message bodies.
    Correlation against the owner's outbound record is enforced by the caller.
    """
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, dict) or change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata") or {}
            if not isinstance(metadata, dict) or metadata.get("phone_number_id") != expected_phone_number_id:
                continue
            for item in (value.get("statuses") or [])[:100]:
                if not isinstance(item, dict):
                    continue
                mid = item.get("id")
                status = item.get("status")
                to = item.get("recipient_id")
                if (
                    isinstance(mid, str) and mid.startswith("wamid.")
                    and len(mid) <= 220
                    and status in ("sent", "delivered", "read", "failed")
                    and isinstance(to, str)
                    and re.fullmatch(r"[1-9][0-9]{6,14}", to)
                ):
                    yield {"id": mid, "status": status, "recipient_id": to}
