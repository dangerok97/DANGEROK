"""
The last few inches, and nothing about whether to walk them.

    CODE ORCHESTRATES. AI REASONS.

A notification provider takes words that have already been decided and puts
them on a device. It has no opinion about whether they should be sent, cannot
read the opportunity behind them, and never sees the reasoning — which is why
it is an interface rather than a call inside the reasoner. Binding the model
directly to Expo would mean every future change of delivery channel reaches
back into the part of the system that decides whether to interrupt somebody,
and those two things must never move together.

Sprint 1 ships the stub. It records what would have been sent, which is
exactly what the tests need and honestly what the product needs until a real
device is in the loop: nothing here has been proven to reach a phone, and the
class names say so.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


class NotificationProvider(Protocol):
    """
    What any channel has to be able to do. Two verbs, no judgement.

    `cancel` matters as much as `send`: a plan that was right when it was made
    and wrong by the time it fires has to be stoppable, and a provider that
    can only send makes that impossible to guarantee.
    """

    name: str

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
        ...

    async def cancel(self, *, owner_id: str, plan_id: str) -> Dict[str, Any]:
        ...


class StubNotificationProvider:
    """
    Records what would have been sent, and sends nothing.

    Not a placeholder to be replaced quietly: as long as this is the provider
    in use, no claim can be made that anything reaches a device. It exists so
    the decision half can be built, tested and reviewed honestly before there
    is a phone to prove it on.
    """

    name = "stub"

    def __init__(self) -> None:
        self.sent: List[Dict[str, Any]] = []
        self.cancelled: List[str] = []

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
        # Only what a lock screen would carry is kept, and only in memory.
        record = {
            "owner_id": owner_id,
            "plan_id": plan_id,
            "title": title,
            "body": body,
            "public_title": public_title or title,
            "public_body": public_body or body,
            "deep_link": deep_link,
        }
        self.sent.append(record)
        logger.info("stub notification prepared plan=%s", plan_id)
        return {"ok": True, "provider": self.name, "external_id": f"stub:{plan_id}"}

    async def cancel(self, *, owner_id: str, plan_id: str) -> Dict[str, Any]:
        self.cancelled.append(plan_id)
        return {"ok": True, "provider": self.name}


_provider: Optional[Any] = None


def get_provider() -> Any:
    """
    The one provider this process delivers through.

    A module-level singleton so a test can replace it and know that every path
    — including ones it did not write — goes through the replacement. Nothing
    reaches a device today.
    """
    global _provider
    if _provider is None:
        _provider = StubNotificationProvider()
    return _provider


def set_provider(provider: Any) -> None:
    global _provider
    _provider = provider
