"""The call gate must check the selected voice runtime, not an unused one."""

import asyncio
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telephone.service import TelephoneService


def _module(name, **members):
    module = ModuleType(name)
    for key, value in members.items():
        setattr(module, key, value)
    return module


def test_gemini_live_does_not_require_deepgram(monkeypatch):
    class Resolver:
        def __init__(self, db):
            pass

        async def resolve(self, owner, capability):
            return SimpleNamespace(known=True, permitted=True, executable=True)

    class Authority:
        def __init__(self, db):
            pass

        async def has_grant(self, owner, capability):
            return False

        async def is_denied(self, owner, capability):
            return False

    monkeypatch.setitem(sys.modules, "agent.capabilities", _module(
        "agent.capabilities", CapabilityResolver=Resolver))
    monkeypatch.setitem(sys.modules, "agent.authority", _module(
        "agent.authority", AuthorityService=Authority))
    monkeypatch.setitem(sys.modules, "telephone.live", _module(
        "telephone.live", live_is_configured=lambda: ""))
    monkeypatch.setenv("ORA_VOICE_RUNTIME", "gemini_live")

    from telephone import carrier, deepgram

    monkeypatch.setattr(carrier, "can_call", lambda: True)
    monkeypatch.setattr(carrier, "why_not", lambda: "")
    monkeypatch.setattr(deepgram, "is_configured", lambda: False)

    readiness = asyncio.run(TelephoneService(None).may_i_call("owner"))
    assert readiness["provider_ready"] is True
    assert readiness["why_not"] == ""

    monkeypatch.setenv("ORA_VOICE_RUNTIME", "classic")
    classic = asyncio.run(TelephoneService(None).may_i_call("owner"))
    assert classic["provider_ready"] is False
    assert "nessuna voce" in classic["why_not"]
