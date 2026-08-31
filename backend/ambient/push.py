"""
Devices, tokens, and the one channel that can actually reach one.

The token is the sensitive object in this whole phase. It is a capability:
whoever holds it can put text on somebody's lock screen. So it is written
once, never logged, never returned by an endpoint, never included in a
report, and the only thing that ever travels back out is `public()`.

Two lifecycle rules matter more than the sending:

* A device belongs to one account at a time. Signing in as somebody else
  releases it, because a token left active for the previous account is how
  one person's notification arrives on another person's phone.
* A permanent provider rejection disables that endpoint and only that one. A
  stale Android token must not stop the same notification reaching an iPhone.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, List, Optional

from ambient.models import PushEndpoint
from ambient.repository import AmbientRepository

logger = logging.getLogger(__name__)

# Expo's own endpoint. Reachable from a server, which is why an adapter can
# exist at all before there is a device in the loop.
EXPO_ENDPOINT = "https://exp.host/--/api/v2/push/send"

# What Expo says when a token will never work again. Anything else is
# transient until proven otherwise: disabling a device because of one network
# blip would be a silent, permanent loss of reachability.
PERMANENT_FAILURES = {"DeviceNotRegistered", "InvalidCredentials", "MessageTooBig"}


def device_hash(raw: str) -> str:
    """
    A stable handle for a device that is not the device's own identifier.

    Enough to recognise the same phone signing in again; not enough to follow
    anybody anywhere.
    """
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()[:32]


class PushEndpointService:
    def __init__(self, db):
        self.db = db
        self.repo = AmbientRepository(db)

    async def register(
        self,
        owner_id: str,
        *,
        token: str,
        platform: str = "unknown",
        device: str = "",
        permission_state: str = "granted",
    ) -> Dict[str, Any]:
        """
        Remember that this device can be reached, and that it belongs here.

        Idempotent: the same phone re-registering on every launch updates one
        row. Registering a device that was signed in as somebody else releases
        it from that account first — the token is a capability, and it may
        only ever point at one person.
        """
        if not token or not owner_id:
            return {"ok": False, "reason": "missing_token"}

        handle = device_hash(device or token)
        # Whoever had this device before does not have it now.
        await self.repo.revoke_device(device_hash=handle)

        endpoint = await self.repo.upsert_endpoint(
            PushEndpoint(
                owner_id=owner_id,
                token=token,
                platform=platform if platform in ("ios", "android", "web") else "unknown",
                provider="expo" if token.startswith("ExponentPushToken") else "stub",
                device_hash=handle,
                status="active",
                permission_state=(
                    permission_state
                    if permission_state in ("granted", "denied", "undetermined")
                    else "undetermined"
                ),
            )
        )
        # The token is deliberately absent from what comes back.
        return {"ok": True, "endpoint": endpoint.public()}

    async def release_device(self, owner_id: str, device: str) -> Dict[str, Any]:
        """Logout. Nothing arrives on this phone for this account again."""
        released = await self.repo.revoke_device(
            device_hash=device_hash(device), owner_id=owner_id
        )
        return {"ok": True, "released": released}

    async def endpoints(self, owner_id: str) -> List[Dict[str, Any]]:
        return [e.public() for e in await self.repo.active_endpoints(owner_id)]


class ExpoNotificationProvider:
    """
    The real channel, as far as a server can build one without a device.

    Everything up to Expo's door is implemented and testable; what happens
    past it is not, and this class does not pretend otherwise. `cancel` is the
    honest part: a plan can be cancelled, a notification that has already
    arrived on somebody's phone cannot be taken back, and saying so in the
    return value is better than an API that implies it can.
    """

    name = "expo"

    def __init__(self, db, *, timeout: float = 10.0):
        self.db = db
        self.timeout = timeout
        self.repo = AmbientRepository(db)

    async def send(
        self,
        *,
        owner_id: str,
        plan_id: str,
        title: str,
        body: str,
        deep_link: str,
        public_title: str = "",
        public_body: str = "",
    ) -> Dict[str, Any]:
        """
        Hand the words to every device this person has, and report per device.

        Partial failure is the normal case with more than one device, so the
        result says what happened to each: one stale Android token disables
        itself and the iPhone still gets the notification.
        """
        endpoints = await self.repo.active_endpoints(owner_id)
        if not endpoints:
            return {"ok": False, "provider": self.name, "reason": "no_endpoint"}

        messages = [
            {
                "to": e.token,
                "title": public_title or title,
                "body": public_body or body,
                "data": {"deep_link": deep_link, "plan_id": plan_id},
            }
            for e in endpoints
        ]

        try:
            tickets = await self._post(messages)
        except Exception as exc:
            # Transient until proven otherwise. The plan is not lost.
            logger.info("expo push transient failure: %s", type(exc).__name__)
            return {
                "ok": False,
                "provider": self.name,
                "transient": True,
                "reason": type(exc).__name__,
            }

        accepted, failed = 0, []
        for endpoint, ticket in zip(endpoints, tickets):
            if str(ticket.get("status")) == "ok":
                accepted += 1
                continue
            detail = str((ticket.get("details") or {}).get("error") or "")
            failed.append({"endpoint": endpoint.id, "error": detail or "unknown"})
            if detail in PERMANENT_FAILURES:
                # This device will never receive again. Only this one.
                await self.repo.disable_endpoint(token=endpoint.token, reason=detail)
                logger.info("push endpoint disabled reason=%s", detail)

        return {
            "ok": accepted > 0,
            "provider": self.name,
            # Accepted by Expo. NOT the same as shown on a phone, and the
            # field name says so on purpose.
            "provider_accepted": accepted,
            "failures": failed,
            "external_id": next(
                (t.get("id") for t in tickets if t.get("id")), f"expo:{plan_id}"
            ),
            "transient": accepted == 0 and not any(
                f["error"] in PERMANENT_FAILURES for f in failed
            ),
        }

    async def cancel(self, *, owner_id: str, plan_id: str) -> Dict[str, Any]:
        """
        A plan can be cancelled. A delivered notification cannot be recalled.

        Returning `retracted: False` is the point: nothing downstream should
        be able to believe a notification was taken back off somebody's phone,
        because it was not.
        """
        return {"ok": True, "provider": self.name, "retracted": False}

    async def _post(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as http:
            response = await http.post(
                EXPO_ENDPOINT,
                json=messages,
                headers={"accept": "application/json", "content-type": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        data = payload.get("data")
        return data if isinstance(data, list) else []


def install_provider(db) -> str:
    """
    Choose the channel this process delivers through.

    Expo only when explicitly asked for. The default stays the stub, so no
    deployment starts sending because a dependency happened to be installed —
    and the name it returns is what the report is allowed to claim.
    """
    from delivery.provider import set_provider

    if os.environ.get("PUSH_PROVIDER", "").strip().lower() == "expo":
        set_provider(ExpoNotificationProvider(db))
        return "expo"
    return "stub"
