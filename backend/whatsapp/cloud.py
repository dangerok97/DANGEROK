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
            # Provider errors can echo sensitive message content/number: never log body.
            raise CloudSendError(response.status_code)
        try:
            parsed = response.json()
            if not parsed.get("messages"):
                raise CloudSendError(502)
        except (json.JSONDecodeError, ValueError) as exc:
            raise CloudSendError(502) from exc


class CloudSendError(Exception):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"Meta Cloud API status {status}")


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
                kind = message.get("type")
                body = (message.get("text") or {}).get("body") if kind == "text" and isinstance(message.get("text"), dict) else ""
                if not isinstance(body, str):
                    body = ""
                yield {"id": mid, "from": sender, "type": kind, "text": body[:8000]}
