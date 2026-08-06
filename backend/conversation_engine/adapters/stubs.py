"""Origin stubs — email / whatsapp / open_banking accepted but not simulated."""
from __future__ import annotations

from typing import Any, Dict

from conversation_engine.models import STUB_ORIGINS


class StubOriginAdapter:
    """Honest stubs: structure only, no fabricated messages or balances."""

    SUPPORTED_NOW = frozenset({"home", "voice", "text", "documents", "notifications", "proactive"})

    @classmethod
    def is_stub(cls, origin: str) -> bool:
        return origin in STUB_ORIGINS

    @classmethod
    def acknowledge(cls, origin: str) -> Dict[str, Any]:
        return {
            "ok": True,
            "stub": True,
            "origin": origin,
            "implemented": False,
            "honesty": (
                f"Origin '{origin}' is predisposed only — no connector, "
                "no simulated inbox/chat/banking data."
            ),
        }
