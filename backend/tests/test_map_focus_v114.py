"""V114 — knowledge map focus follows new/updated/talked-about grounded stars."""
import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import _display_focus_ref
from conversation_engine.ai_core.models import CognitiveDecision
from life_profile.knowledge_map import knowledge_map


def test_memory_write_becomes_visual_focus_even_if_model_omits_it():
    decision = CognitiveDecision(response_mode="answer", message_to_user="Salvato.")
    ref = _display_focus_ref(
        decision,
        [{
            "kind": "tool",
            "name": "memory_governance",
            "status": "ok",
            "payload": {
                "outcomes": [{
                    "decision": "PROMOTE",
                    "memory_id": "mem_birthday",
                    "persisted": True,
                }]
            },
        }],
        None,
    )
    assert ref == "mem_birthday"


def test_explicit_grounded_focus_ref_has_priority():
    decision = CognitiveDecision(
        response_mode="answer",
        message_to_user="Parliamo di questo.",
        display_focus_ref="mem_existing",
    )
    assert _display_focus_ref(decision, [], None) == "mem_existing"


@pytest.mark.asyncio
async def test_grouped_birthday_star_resolves_each_underlying_memory_ref():
    db = AsyncMongoMockClient().focus_v114
    await db.memories.insert_many([
        {
            "id": "mem_elena",
            "user_id": "owner",
            "status": "active",
            "authority": "user_stated",
            "epistemic_status": "asserted",
            "kind": "birthday",
            "statement": "L'8 ottobre è il compleanno di zia Elena.",
            "value": {"person": "zia Elena", "month": 10, "day": 8},
            "updated_at": "2026-10-07T21:55:00+00:00",
        },
        {
            "id": "mem_marco",
            "user_id": "owner",
            "status": "active",
            "authority": "user_stated",
            "epistemic_status": "asserted",
            "kind": "birthday",
            "statement": "Il 4 agosto è il compleanno di Marco.",
            "value": {"person": "Marco", "month": 8, "day": 4},
            "updated_at": "2026-10-07T21:56:00+00:00",
        },
    ])
    result = await knowledge_map(db, "owner")
    star = next(s for s in result["stars"] if s.get("group_kind") == "birthdays")
    assert star["title"] == "Compleanni"
    assert "mem_elena" in star["source_refs"]
    assert "mem_marco" in star["source_refs"]
    assert "memory_group:birthdays" in star["source_refs"]


@pytest.mark.asyncio
async def test_temporary_star_exposes_exact_situation_ref():
    db = AsyncMongoMockClient().focus_situation_v114
    await db.situations.insert_one({
        "id": "sit_focus",
        "user_id": "owner",
        "status": "active",
        "summary": "Una cosa temporanea.",
        "semantic_kind": "Situazione",
        "revision": 1,
        "history": [],
        "applied_epochs": [],
        "created_at": "2026-10-07T21:00:00+00:00",
        "updated_at": "2026-10-07T21:00:00+00:00",
    })
    result = await knowledge_map(db, "owner")
    star = next(s for s in result["stars"] if s.get("situation_id") == "sit_focus")
    assert star["source_refs"] == ["situation:sit_focus"]
