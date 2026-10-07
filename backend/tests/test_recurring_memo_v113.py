"""V113 — durable recurring Memo + aggregated birthday Memory star."""
from datetime import datetime, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.models import MemoryCandidate
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.models import ConversationSession
from life_memory.governance import MemoryGovernanceService
from life_profile.knowledge_map import knowledge_map
from memos.service import RecurringMemoService


def birthday_candidate(person: str, month: int, day: int, *, identity: str):
    return MemoryCandidate(
        operation="propose",
        summary=f"Il {day}/{month} è il compleanno di {person}.",
        kind="birthday",
        identity_key=identity,
        value={"person": person, "month": month, "day": day},
        confidence=0.99,
        authority="user_stated",
        epistemic_status="asserted",
        provenance=["user_conversation"],
        permanence="durable",
        recurrence="annual",
        sensitivity="normal",
        reason_for_future_utility="Ricordare ogni anno il compleanno alla persona.",
        requires_confirmation=False,
        user_authorized=False,
    )


@pytest.mark.asyncio
async def test_clear_birthday_is_durable_without_redundant_confirmation():
    db = AsyncMongoMockClient().memo_v113
    service = MemoryGovernanceService(db)
    await service.ensure_indexes()

    result = await service.process(
        user_id="owner",
        session_id="s1",
        reasoning_epoch="e1",
        candidates=[birthday_candidate("zia Elena", 3, 13, identity="birthday:zia_elena")],
    )

    assert result[0].decision == "PROMOTE"
    assert result[0].persisted is True
    memory = await db.memories.find_one({"id": result[0].memory_id}, {"_id": 0})
    assert memory["kind"] == "birthday"
    assert memory["value"] == {"person": "zia Elena", "month": 3, "day": 13}
    assert memory["temporal_scope"]["recurrence"] == "annual"


@pytest.mark.asyncio
async def test_two_people_are_two_memories_but_one_compleanni_star():
    db = AsyncMongoMockClient().memo_map_v113
    governance = MemoryGovernanceService(db)
    await governance.ensure_indexes()

    first = await governance.process(
        user_id="owner",
        session_id="s1",
        reasoning_epoch="e1",
        candidates=[birthday_candidate("zia Elena", 3, 13, identity="birthday:zia_elena")],
    )
    second = await governance.process(
        user_id="owner",
        session_id="s2",
        reasoning_epoch="e2",
        candidates=[birthday_candidate("Marco", 8, 4, identity="birthday:marco")],
    )
    assert first[0].persisted and second[0].persisted
    assert await db.memories.count_documents({"user_id": "owner", "kind": "birthday", "status": "active"}) == 2

    projected = await knowledge_map(db, "owner")
    groups = [s for s in projected["stars"] if s.get("group_kind") == "birthdays"]
    assert len(groups) == 1
    star = groups[0]
    assert star["title"] == "Compleanni"
    assert star["area"] == "people"
    assert star["statement"] == "2 compleanni salvati"
    assert [(x["label"], x["date_label"]) for x in star["group_items"]] == [
        ("zia Elena", "13 marzo"),
        ("Marco", "4 agosto"),
    ]
    assert not any(
        s.get("title") == "Ricordo" and "compleanno" in s.get("statement", "").lower()
        for s in projected["stars"]
    )


@pytest.mark.asyncio
async def test_annual_memo_requires_owned_memory_and_schedules_next_occurrence():
    db = AsyncMongoMockClient().memo_schedule_v113
    service = RecurringMemoService(db)
    await service.ensure_indexes()

    missing = await service.save_annual(
        "owner", memory_ref="mem_missing", category="birthday",
        label="Compleanno di Elena", person="Elena", month=3, day=13,
    )
    assert missing == {"ok": False, "error": "durable_memory_required"}

    await db.memories.insert_one({
        "id": "mem_elena", "user_id": "owner", "status": "active",
        "statement": "Il 13 marzo è il compleanno di Elena.",
        "value": {"person": "Elena", "month": 3, "day": 13},
    })
    saved = await service.save_annual(
        "owner", memory_ref="mem_elena", category="birthday",
        label="Compleanno di Elena", person="Elena", month=3, day=13,
        timezone_name="Europe/Rome",
    )
    assert saved["ok"] is True
    assert saved["memo"]["status"] == "active"
    due = datetime.fromisoformat(saved["memo"]["next_due_at"])
    local = due.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Rome"))
    assert (local.month, local.day, local.hour) == (3, 13, 9)


@pytest.mark.asyncio
async def test_due_birthday_raises_one_existing_delivery_opportunity_and_moves_to_next_year():
    db = AsyncMongoMockClient().memo_due_v113
    service = RecurringMemoService(db)
    await service.ensure_indexes()

    await db.memories.insert_one({
        "id": "mem_elena", "user_id": "owner", "status": "active",
        "statement": "Il 13 marzo è il compleanno di Elena.",
        "value": {"person": "Elena", "month": 3, "day": 13},
    })
    saved = await service.save_annual(
        "owner", memory_ref="mem_elena", category="birthday",
        label="Compleanno di Elena", person="Elena", month=3, day=13,
        timezone_name="Europe/Rome",
    )
    memo_id = saved["memo"]["id"]
    moment = datetime(2027, 3, 13, 8, 5, tzinfo=timezone.utc)  # 09:05 Rome
    await db.recurring_memos.update_one(
        {"id": memo_id}, {"$set": {"next_due_at": datetime(2027, 3, 13, 8, 0, tzinfo=timezone.utc).isoformat()}}
    )

    fired = await service.fire_due(now=moment)
    assert fired == {"due": 1, "raised": 1, "disabled": 0}

    opportunities = await db.opportunities.find({"owner_id": "owner"}, {"_id": 0}).to_list(None)
    assert len(opportunities) == 1
    assert opportunities[0]["status"] == "active"
    assert opportunities[0]["surface_state"] == "surfaced"
    assert "Compleanno di Elena" in opportunities[0]["semantic_summary"]
    assert opportunities[0]["delivery_review_state"] == "pending"

    memo = await db.recurring_memos.find_one({"id": memo_id}, {"_id": 0})
    next_due = datetime.fromisoformat(memo["next_due_at"])
    next_local = next_due.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Rome"))
    assert next_local.year == 2028
    assert (next_local.month, next_local.day, next_local.hour) == (3, 13, 9)
    assert memo["last_fired_year"] == 2027


@pytest.mark.asyncio
async def test_forgotten_memory_disables_due_memo_instead_of_reminding():
    db = AsyncMongoMockClient().memo_forget_v113
    service = RecurringMemoService(db)
    await service.ensure_indexes()
    await db.memories.insert_one({
        "id": "mem_old", "user_id": "owner", "status": "forgotten",
        "statement": "Vecchio compleanno",
        "value": {"person": "X", "month": 3, "day": 13},
    })
    await db.recurring_memos.insert_one({
        "id": "rmm_old", "owner_id": "owner", "memory_ref": "mem_old",
        "category": "birthday", "label": "Compleanno X", "person": "X",
        "recurrence": "annual", "month": 3, "day": 13, "timezone": "Europe/Rome",
        "remind_hour_local": 9, "next_due_at": "2026-01-01T00:00:00+00:00",
        "status": "active", "claim_until": None,
    })
    fired = await service.fire_due(now=datetime(2026, 10, 7, 19, 0, tzinfo=timezone.utc))
    assert fired["disabled"] == 1
    assert await db.opportunities.count_documents({"owner_id": "owner"}) == 0
    assert (await db.recurring_memos.find_one({"id": "rmm_old"}))["status"] == "disabled"


def test_memo_is_an_ai_capability_not_a_dedicated_product_button():
    registry = ToolRegistry(None)
    tool = registry.get("save_recurring_memo")
    assert tool is not None
    assert tool.side_effect == "REVERSIBLE_WRITE"
    assert "memo" in tool.tags


@pytest.mark.asyncio
async def test_birthday_turn_persists_memory_then_schedule_before_promising():
    db = AsyncMongoMockClient().memo_turn_v113
    await MemoryGovernanceService(db).ensure_indexes()
    await RecurringMemoService(db).ensure_indexes()
    session = ConversationSession(
        user_id="turn-owner",
        meta={"ui_mode": "ai_core", "ai_core": {}},
    )
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "answer",
                "message_to_user": "Lo terrò a mente.",
                "memory_candidates": [{
                    "operation": "propose",
                    "summary": "Il 13 marzo è il compleanno di zia Elena.",
                    "kind": "birthday",
                    "identity_key": "birthday:zia_elena",
                    "value": {"person": "zia Elena", "month": 3, "day": 13},
                    "confidence": 0.99,
                    "authority": "user_stated",
                    "epistemic_status": "asserted",
                    "provenance": ["user_conversation"],
                    "permanence": "durable",
                    "recurrence": "annual",
                    "sensitivity": "normal",
                    "reason_for_future_utility": "Ricordare ogni anno il compleanno.",
                    "requires_confirmation": False,
                    "user_authorized": False,
                }],
                "situation_update": {"operation": "none"},
            }
        if calls == 2:
            memory = await db.memories.find_one(
                {"user_id": "turn-owner", "identity_key": "birthday:zia_elena"},
                {"_id": 0},
            )
            assert memory is not None, "Memory governance must happen before scheduling"
            return {
                "response_mode": "tool",
                "tool_call": {
                    "capability": "save_recurring_memo",
                    "arguments": {
                        "memory_ref": memory["id"],
                        "category": "birthday",
                        "label": "Compleanno di zia Elena",
                        "person": "zia Elena",
                        "month": 3,
                        "day": 13,
                        "timezone": "Europe/Rome",
                        "remind_hour_local": 9,
                    },
                },
                "situation_update": {"operation": "none"},
            }
        memo = await db.recurring_memos.find_one(
            {"owner_id": "turn-owner", "category": "birthday"}, {"_id": 0}
        )
        assert memo is not None, "Final promise may happen only after recurrence persisted"
        return {
            "response_mode": "answer",
            "message_to_user": "Ok, te lo ricorderò ogni 13 marzo.",
            "situation_update": {"operation": "none"},
        }

    result = await run_cognitive_loop(
        sess=session,
        user_message="Il 13 marzo è il compleanno di mia zia Elena.",
        db=db,
        decision_fn=decide,
    )

    assert result.ok
    assert result.ora_text == "Ok, te lo ricorderò ogni 13 marzo."
    assert await db.memories.count_documents(
        {"user_id": "turn-owner", "identity_key": "birthday:zia_elena", "status": "active"}
    ) == 1
    assert await db.recurring_memos.count_documents(
        {"owner_id": "turn-owner", "category": "birthday", "status": "active"}
    ) == 1
    assert await db.situations.count_documents({"user_id": "turn-owner"}) == 0
