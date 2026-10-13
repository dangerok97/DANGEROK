"""Release gate: a new ORA cognitive skill must reach WhatsApp automatically.

This validates the shared catalog and generic presentation contract. It does
NOT assert that a third-party connector or unsupported device sensor works.
"""
from types import SimpleNamespace

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.channel_actions import (
    portable_ui_action,
    safe_ora_screen_path,
)
from conversation_engine.ai_core.loop import _ui_actions_from
from conversation_engine.ai_core.orchestrator import _ui_actions
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools.capability import CapabilitySpec
from conversation_engine.ai_core.tools.registry import ToolRegistry
from whatsapp.handoff import render_core_answer_for_whatsapp
from whatsapp.parity import shared_ai_capability_manifest
from whatsapp.service import WhatsAppService


def test_whatsapp_catalog_is_exact_same_live_tool_registry():
    registry = ToolRegistry()
    visible = registry.list_public()
    contract = shared_ai_capability_manifest(registry)
    assert contract["shared_ai_core"] is True
    assert contract["automatic_future_skill_discovery"] is True
    assert contract["source"] == "ai_core_tool_registry"
    assert contract["capability_count"] == len(visible)
    assert contract["capability_count"] >= 20
    assert {t["capability"] for t in contract["capabilities"]} == {
        t["capability"] for t in visible
    }
    assert all(t["surface"] == "shared_ai_core" for t in contract["capabilities"])
    assert all(registry.get(t["capability"]).handler is not None for t in visible)


def test_new_skill_automatically_joins_whatsapp_without_a_second_allowlist():
    registry = ToolRegistry()
    before = shared_ai_capability_manifest(registry)

    async def future_skill(arguments, runtime):
        return Observation(
            kind="tool", name="future_skill", status="ok",
            payload={"value": arguments.get("value"), "ok": True},
        )

    registry.register(CapabilitySpec(
        capability="future_skill", description="A simulated future ORA skill",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
        handler=future_skill,
    ))
    after = shared_ai_capability_manifest(registry)
    assert after["capability_count"] == before["capability_count"] + 1
    assert "future_skill" in {row["capability"] for row in after["capabilities"]}
    assert registry.get("future_skill").handler is future_skill

    registry.register(CapabilitySpec(
        capability="future_hidden_internal", description="Not AI selectable",
        input_schema={"type": "object", "properties": {}},
        availability="hidden", handler=future_skill,
    ))
    assert shared_ai_capability_manifest(registry)["capability_count"] == after["capability_count"]


def test_new_skill_ui_screen_flows_from_one_core_observation_to_whatsapp():
    future_observation = Observation(
        kind="tool", name="future_3d_skill", status="ok",
        payload={"ui_action": {
            "kind": "ora_screen", "path": "/vision-xray",
            "label": "Apri visione 3D",
        }},
    )
    actions = _ui_actions_from([future_observation.model_dump()])
    assert actions == [{
        "kind": "ora_screen", "path": "/vision-xray",
        "label": "Apri visione 3D",
    }]
    public = _ui_actions(actions)
    assert public == actions
    output = render_core_answer_for_whatsapp({
        "ok": True, "session_id": "ces_abcdefgh123456",
        "ora_text": "Per la visione esplosa ti apro il modello interattivo.",
        "ui_actions": public,
    })
    assert "Apri visione 3D" in output
    assert "https://ora-web-production-fb67.up.railway.app/vision-xray" in output
    assert "/ora/ces_" not in output  # Feature-specific handoff is preferred.


@pytest.mark.parametrize("malicious", [
    "", "https://example.org", "//example.org", "/login",
    "/google-auth-complete", "/account", "/api/admin",
    "/vision-xray?ticket=TOKEN", "/vision-xray#other",
    "/vision-xray/%2Fadmin", "/vision-xray/../account",
    "/vision-xray\\admin", "/vision-xray\nhttp:evil",
    "/path with spaces",
])
def test_app_screen_links_cannot_escape_authored_route(malicious):
    assert safe_ora_screen_path(malicious) is None
    projected = portable_ui_action({
        "kind": "ora_screen", "path": malicious,
        "label": "Malicious feature",
    })
    assert projected == {"kind": "app_handoff", "label": "Apri la funzione in ORA"}


def test_unknown_future_visual_action_keeps_authenticated_app_handoff():
    source = Observation(
        kind="tool", name="future_visual_skill", status="ok",
        payload={"ui_action": {
            "kind": "totally_new_immersive_view", "url": "https://evil.invalid/x",
        }},
    )
    actions = _ui_actions(_ui_actions_from([source.model_dump()]))
    assert actions == [{"kind": "app_handoff", "label": "Apri in ORA"}]
    output = render_core_answer_for_whatsapp({
        "ora_text": "Per interagire con il risultato, apri ORA.",
        "session_id": "ces_abcdefgh123456", "ui_actions": actions,
    })
    assert "/ora/ces_abcdefgh123456" in output
    assert "evil.invalid" not in output


def test_failed_or_unverified_tools_cannot_generate_feature_link():
    evidence = Observation(
        kind="tool", name="failing_tool", status="error",
        payload={"ui_action": {
            "kind": "ora_screen", "path": "/vision-xray",
            "label": "Non aperto",
        }},
    )
    assert _ui_actions_from([evidence.model_dump()]) == []


@pytest.mark.asyncio
async def test_linked_whatsapp_status_uses_live_shared_catalog():
    db = AsyncMongoMockClient().whatsapp_shared_catalog_status
    await db.whatsapp_links.insert_one({
        "user_id": "owner_account",
        "phone_hash": "fake",
        "phone_last4": "1234",
    })
    config = SimpleNamespace(display_number="3907611810322")
    svc = WhatsAppService(db, config=config)
    status = await svc.status("owner_account")
    assert status["linked"] is True
    assert status["shared_ai_core"] is True
    assert status["shared_capability_count"] == shared_ai_capability_manifest()["capability_count"]
    assert status["capability_contract_version"] == 1
    assert status["notifications_enabled"] is False
    other = await svc.status("other_account")
    assert other["linked"] is False
    assert other["shared_capability_count"] == status["shared_capability_count"]
    assert other["phone_last4"] is None
