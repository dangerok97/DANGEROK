"""One full synthetic autonomous wake through ORA's actual components.

The AI choice and notification transport are deterministic stand-ins, not
real model/device evidence. A connected signal is processed by the NEW
separate source-understanding lane, the ordinary Core writes an authorized
calendar event, Home stores a verified result, and the existing Delivery
pipeline accepts one notification. No personal account or external provider.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from connected import polling, core_work
from connected.core_work import SourceCoreWorker
from delivery import admission, provider, reasoning, context
from delivery.service import DeliveryService
from test_general_source_core_v166 import world, OWNER, OTHER, BODY
from test_durable_source_work_v169 import grant, decisions
from test_source_result_delivery_v170 import RecordingProvider, answer
from test_source_integrity_v168 import StableMockDatabase


@pytest.mark.asyncio
async def test_real_autonomy_wiring_from_pending_mail_to_verified_delivery(world, monkeypatch):
    raw, signal, source_reader = world
    db = StableMockDatabase(raw)
    monkeypatch.setenv("ORA_SOURCE_CORE_PILOT_OWNERS", OWNER)
    monkeypatch.setenv("ORA_SOURCE_RESULT_DELIVERY_OWNERS", OWNER)
    monkeypatch.setenv("ORA_SOURCE_MODEL_CONTRACT", '{"synthetic":"scripted-model"}')
    await grant(db)
    assert await core_work.ready_for_owner(db, OWNER)

    # Only the model's decisions are scripted; the actual Core/source reader,
    # calendar mutation, Home receipt and delivery handlers execute unchanged.
    choose, reasoning_turns = decisions(signal)
    original_process_one = SourceCoreWorker.process_one

    async def scripted_process_one(self, owner_id, signal_id, *, decision_fn=None):
        return await original_process_one(
            self, owner_id, signal_id, decision_fn=choose
        )

    monkeypatch.setattr(SourceCoreWorker, "process_one", scripted_process_one)
    channel = RecordingProvider()
    delivery_judgement = AsyncMock(return_value=answer())
    monkeypatch.setattr(provider, "get_provider", lambda: channel)
    monkeypatch.setattr(context, "_permission", AsyncMock(return_value={"push": True}))
    monkeypatch.setattr(reasoning, "decide_delivery", delivery_judgement)

    # This is the background lane introduced after PR #333, not the
    # interactive chat entry point and not direct SourceCoreWorker invocation.
    first = await polling.interpret_due(db)
    assert first == {"looked_at": 1, "understood": 1, "noise": 0}
    assert len(reasoning_turns) == 3
    source_reader.assert_awaited_once()

    events = await db.life_nodes.find(
        {"user_id": OWNER, "type": "event"}, {"_id": 0}
    ).to_list(10)
    assert len(events) == 1
    assert events[0]["label"] == "Colloquio confermato"
    assert events[0]["attributes"]["starts_at"] == "2031-05-16T14:00:00+02:00"
    visible = await db.ambient_activity.find(
        {"owner_id": OWNER, "visibility": "ambient"}, {"_id": 0}
    ).to_list(10)
    assert len(visible) == 1
    assert "16/05/2031 alle 14:00" in visible[0]["summary"]
    assert BODY not in json.dumps(visible, default=str)

    source = await db.connected_signals.find_one(
        {"owner_id": OWNER, "id": signal.id}, {"_id": 0}
    )
    assert source["status"] == "interpreted"
    assert source["_core_work"]["effect"]["state"] == "verified"
    assert source["_core_work"]["delivery_review"]["phase"] == "pending"
    assert not channel.calls, "Home is not a claim that a push was sent"

    await DeliveryService(db).repo.ensure_indexes()
    handled = await admission.drain_with_receipts(db)
    assert handled == 1
    assert len(channel.calls) == 1
    assert channel.calls[0]["owner_id"] == OWNER
    assert "Colloquio confermato" in channel.calls[0]["body"]
    assert "UNSUPPORTED_MODEL" not in json.dumps(channel.calls, default=str)

    plan = await db.delivery_plans.find_one({"owner_id": OWNER}, {"_id": 0})
    assert plan["status"] == "delivered"
    assert plan["_source_dispatch"]["state"] == "accepted"
    assert plan["_source_dispatch"]["device_delivery_verified"] is False
    assert delivery_judgement.await_count == 1
    assert await admission.drain_with_receipts(db) == 0
    assert await polling.interpret_due(db) == {
        "looked_at": 0, "understood": 0, "noise": 0
    }
    assert len(channel.calls) == 1
    assert await db.life_nodes.count_documents({"user_id": OTHER}) == 0
    assert await db.autonomy_consents.count_documents(
        {"source": "explicit_user_command"}
    ) == 0

    print("ORA_AUTONOMY_E2E_SYNTHETIC " + json.dumps({
        "source_read": True,
        "source_ai_decisions_scripted": True,
        "calendar_event_verified": True,
        "home_result_visible": True,
        "delivery_provider_accepted_once": True,
        "physical_device_delivery_verified": False,
        "real_account_touched": False,
        "real_model_used": False,
    }), flush=True)
