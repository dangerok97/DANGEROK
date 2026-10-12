"""Owner-scoped durable annual memo context must be equally readable from app/WhatsApp.

Never infer the actual user's stored birthdays from these synthetic records.
"""
import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.context_broker import ContextBroker
from conversation_engine.ai_core.context_sources import ContextSourceRegistry
from conversation_engine.ai_core.models import ContextNeed


OWNER = "synthetic-person-with-memos"
OTHER = "another-owner"


def request() -> ContextNeed:
    return ContextNeed(
        query="Quali compleanni mi hai già chiesto di ricordare?",
        purpose="Riportare solo ricorrenze già salvate e verificate",
        source_hints=["memory", "recurring_memos"],
        max_items=8,
    )


async def seed(db):
    await db.memories.insert_many([
        {"user_id": OWNER, "id": "mem_elena", "status": "active",
         "statement": "Il 10 ottobre è il compleanno di zia Elena.",
         "created_at": "2026-10-07T09:00:00Z", "kind": "birthday",
         "value": {"person": "zia Elena", "month": 10, "day": 10}},
        {"user_id": OWNER, "id": "mem_active_anni", "status": "active",
         "statement": "Il 21 maggio è il compleanno di Anna.",
         "created_at": "2026-10-07T09:00:00Z", "kind": "birthday",
         "value": {"person": "Anna", "month": 5, "day": 21}},
        {"user_id": OWNER, "id": "mem_old", "status": "superseded",
         "statement": "Il 20 maggio era il compleanno di Anna."},
        {"user_id": OTHER, "id": "mem_other", "status": "active",
         "statement": "Il 2 gennaio è il compleanno privato dell'altro utente."},
    ])
    await db.recurring_memos.insert_many([
        {"id": "rmm_elena", "owner_id": OWNER, "memory_ref": "mem_elena",
         "category": "birthday", "label": "Compleanno di zia Elena",
         "month": 10, "day": 10, "recurrence": "annual", "status": "active"},
        {"id": "rmm_anna", "owner_id": OWNER, "memory_ref": "mem_active_anni",
         "category": "birthday", "label": "Compleanno di Anna",
         "month": 5, "day": 21, "recurrence": "annual", "status": "active"},
        {"id": "rmm_superseded", "owner_id": OWNER, "memory_ref": "mem_old",
         "category": "birthday", "label": "Compleanno vecchio",
         "month": 5, "day": 20, "recurrence": "annual", "status": "active"},
        {"id": "rmm_orphan", "owner_id": OWNER, "memory_ref": "missing",
         "category": "birthday", "label": "Promemoria orfano",
         "month": 8, "day": 18, "recurrence": "annual", "status": "active"},
        {"id": "rmm_disabled", "owner_id": OWNER, "memory_ref": "mem_elena",
         "category": "birthday", "label": "Non attivo",
         "month": 10, "day": 10, "recurrence": "annual", "status": "disabled"},
        {"id": "rmm_other", "owner_id": OTHER, "memory_ref": "mem_other",
         "category": "birthday", "label": "Compleanno segreto",
         "month": 1, "day": 2, "recurrence": "annual", "status": "active"},
    ])


@pytest.mark.asyncio
async def test_stage_a_indexes_saved_reminders_without_leaking_details():
    db = AsyncMongoMockClient().cross_channel_memo_index
    await seed(db)
    broker = ContextBroker(db)
    facts = await broker._memory_index_facts(OWNER)
    assert facts and all("Elena" not in x.statement for x in facts)
    assert any("ricorrenze annuali" in x.statement for x in facts)
    facts_other = await broker._memory_index_facts("no-data-user")
    assert not facts_other


@pytest.mark.asyncio
async def test_stage_b_returns_only_verified_owner_recurring_memos():
    db = AsyncMongoMockClient().cross_channel_memo_read
    await seed(db)
    registry = ContextSourceRegistry(db)
    facts = await registry._recurring_memos(OWNER, request(), "some_whatsapp_session")
    assert len(facts) == 2
    combined = "\n".join(f.statement for f in facts)
    assert "zia Elena" in combined and "10/10" in combined
    assert "Anna" in combined and "21/05" in combined
    assert "vecchio" not in combined
    assert "orfano" not in combined
    assert "segreto" not in combined
    assert all(x.ref.startswith("recurring_memo_read_only:") for x in facts)
    # No read action may modify a saved personal date or its next_due_at.
    assert await db.recurring_memos.count_documents({}) == 6


@pytest.mark.asyncio
async def test_context_broker_can_answer_birthday_question_in_whatsapp_session():
    db = AsyncMongoMockClient().cross_channel_context
    await seed(db)
    broker = ContextBroker(db)
    facts = await broker.retrieve(
        user_id=OWNER, user_message="ORA, quali compleanni ti ho già chiesto di ricordare?",
        context_need=request(), stage="B", session_id="ces_owned_whatsapp",
    )
    recurring = [x for x in facts if x.source == "recurring_memos"]
    assert recurring, broker.last_report.public()
    assert any("10/10" in x.statement and "Elena" in x.statement for x in recurring)
    assert all("segreto" not in x.statement for x in facts)
    assert "recurring_memos" in broker.last_report.queried_sources


@pytest.mark.asyncio
async def test_old_birthday_still_retrievable_after_many_recent_memories():
    db = AsyncMongoMockClient().cross_channel_old_memo
    await db.memories.insert_one({
        "user_id": OWNER, "id": "mem_older", "status": "active",
        "kind": "birthday", "statement": "Il 10 ottobre è il compleanno di zia Elena.",
        "created_at": "2026-01-01T00:00:00Z",
    })
    await db.memories.insert_many([
        {"user_id": OWNER, "id": f"mem_recent_{i}", "status": "active",
         "statement": f"Nota sintetica {i}", "created_at": "2026-10-12T12:00:00Z"}
        for i in range(55)
    ])
    await db.recurring_memos.insert_one({
        "id": "rmm_older", "owner_id": OWNER, "memory_ref": "mem_older",
        "category": "birthday", "label": "Compleanno di zia Elena",
        "month": 10, "day": 10, "recurrence": "annual", "status": "active",
    })
    facts = await ContextSourceRegistry(db)._recurring_memos(
        OWNER, request(), "ces_whatsapp_other_session"
    )
    assert len(facts) == 1 and "10/10" in facts[0].statement


@pytest.mark.asyncio
async def test_unnamed_march_13_is_not_assigned_to_october_10_elena():
    """Two independent user facts never get joined just because both are birthdays."""
    db = AsyncMongoMockClient().birthday_distinct_dates_v1
    await db.memories.insert_many([
        {"user_id": OWNER, "id": "mem_elena_oct10", "kind": "birthday",
         "status": "active",
         "statement": "Il 10 ottobre è il compleanno di zia Elena.",
         "value": {"person": "zia Elena", "month": 10, "day": 10}},
        {"user_id": OWNER, "id": "mem_unnamed_mar13", "kind": "birthday",
         "status": "active",
         "statement": "Ricorrenza annuale del 13 marzo.",
         "value": {"month": 3, "day": 13}},
    ])
    await db.recurring_memos.insert_many([
        {"id": "rmm_elena_oct10", "owner_id": OWNER, "memory_ref": "mem_elena_oct10",
         "category": "birthday", "label": "[Nome non specificato]",
         "month": 10, "day": 10, "recurrence": "annual", "status": "active"},
        {"id": "rmm_unnamed_mar13", "owner_id": OWNER, "memory_ref": "mem_unnamed_mar13",
         "category": "annual_memo", "label": "[Nome non specificato]",
         "month": 3, "day": 13, "recurrence": "annual", "status": "active"},
    ])
    facts = await ContextSourceRegistry(db)._recurring_memos(
        OWNER, request(), "ces_owned_whatsapp"
    )
    assert len(facts) == 2
    october = next(x for x in facts if "10/10" in x.statement)
    march = next(x for x in facts if "13/03" in x.statement)
    assert "zia Elena" in october.statement
    assert "zia Elena" not in march.statement
    assert "nome non recuperato" in march.statement


@pytest.mark.asyncio
async def test_generic_cached_label_can_recover_explicit_name_from_original():
    db = AsyncMongoMockClient().birthday_memory_original_name
    await db.memories.insert_one({
        "id": "mem_elena", "user_id": OWNER, "status": "active",
        "kind": "birthday",
        "statement": "Il 10 ottobre è il compleanno di mia zia Elena.",
        "value": {"month": 10, "day": 10},
    })
    await db.recurring_memos.insert_one({
        "id": "rmm_elena", "owner_id": OWNER, "memory_ref": "mem_elena",
        "category": "birthday", "label": "Compleanno di [Nome non specificato]",
        "person": "[Nome non specificato]", "month": 10, "day": 10,
        "recurrence": "annual", "status": "active",
    })
    facts = await ContextSourceRegistry(db)._recurring_memos(
        OWNER, request(), "ces_owned_whatsapp"
    )
    assert len(facts) == 1
    assert "Compleanno di zia Elena" in facts[0].statement
    assert "10/10" in facts[0].statement


@pytest.mark.asyncio
async def test_conflicting_memory_and_reminder_dates_never_claim_elena_march13():
    db = AsyncMongoMockClient().birthday_different_dates
    await db.memories.insert_one({
        "id": "mem_elena", "user_id": OWNER, "status": "active",
        "kind": "birthday",
        "statement": "Il 10 ottobre è il compleanno di zia Elena.",
        "value": {"person": "zia Elena", "month": 10, "day": 10},
    })
    await db.recurring_memos.insert_one({
        "id": "rmm_stale_march", "owner_id": OWNER, "memory_ref": "mem_elena",
        "category": "birthday", "label": "Compleanno di zia Elena",
        "person": "zia Elena", "month": 3, "day": 13,
        "recurrence": "annual", "status": "active",
    })
    facts = await ContextSourceRegistry(db)._recurring_memos(
        OWNER, request(), "ces_owned_whatsapp"
    )
    assert len(facts) == 1
    assert facts[0].status == "conflicting_evidence"
    assert "zia Elena" not in facts[0].statement
    assert "13/03" not in facts[0].statement
    assert "10/10" not in facts[0].statement
    # Lookup cannot rewrite the user's persisted reminder.
    original = await db.recurring_memos.find_one({"id": "rmm_stale_march"})
    assert original["month"] == 3 and original["day"] == 13
