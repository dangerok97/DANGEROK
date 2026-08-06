"""Adapter stubs — Email / Open Banking / WhatsApp / Weather NOT implemented."""
from __future__ import annotations

from typing import Any, Dict


def stub_response(name: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "stub": True,
        "adapter": name,
        "honesty": (
            f"{name} non è operativo in questa fondazione Life Setup. "
            "Nessun dato inventato. Nessuna integrazione simulata."
        ),
    }


class EmailAdapterStub:
    name = "email"

    async def fetch(self, *_a, **_k) -> Dict[str, Any]:
        return stub_response(self.name)


class OpenBankingAdapterStub:
    name = "open_banking"

    async def fetch(self, *_a, **_k) -> Dict[str, Any]:
        return stub_response(self.name)


class WhatsAppAdapterStub:
    name = "whatsapp"

    async def fetch(self, *_a, **_k) -> Dict[str, Any]:
        return stub_response(self.name)


class WeatherAdapterStub:
    name = "weather"

    async def fetch(self, *_a, **_k) -> Dict[str, Any]:
        return stub_response(self.name)


STUBS = {
    "email": EmailAdapterStub(),
    "open_banking": OpenBankingAdapterStub(),
    "whatsapp": WhatsAppAdapterStub(),
    "weather": WeatherAdapterStub(),
}
