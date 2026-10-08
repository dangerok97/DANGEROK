"""V134: background Delivery must not starve one owner behind another.

The source is an owned Opportunity and only DeliveryService chooses how to
contact a person. This gate tests the Mongo admission queue, not a real push.
"""
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from delivery.admission import drain
from delivery.models import DeliveryResult
from delivery.service import DeliveryService
from opportunities.models import Opportunity
from opportunities.repository import OpportunityRepository


async def make(db, owner: str, index: int):
    return await OpportunityRepository(db).save(Opportunity(
        owner_id=owner, identity_key=f"v134-fair-{owner}-{index}",
        status="active", semantic_summary=f"Synthetic update {index}",
        why_it_matters="Proactive update awaiting a delivery decision.",
        initiative="inform",
    ))


def scripted_delivery(monkeypatch):
    decide = AsyncMock(return_value=DeliveryResult(mode="in_app"))
    monkeypatch.setattr(DeliveryService, "evaluate", decide)
    return decide


@pytest.mark.asyncio
async def test_two_global_slots_serve_two_owners_during_one_owners_burst(monkeypatch):
    db = AsyncMongoMockClient().fair_delivery_v134
    for index in range(5):
        await make(db, "alice", index)
    await make(db, "bob", 0)
    evaluate = scripted_delivery(monkeypatch)

    assert await drain(db, limit=2) == 2
    assert [c.args[0] for c in evaluate.await_args_list] == ["alice", "bob"]
    assert await db.opportunities.count_documents({
        "owner_id": "alice", "delivery_review_state": "pending",
    }) == 4
    assert await db.opportunities.count_documents({
        "owner_id": "bob", "delivery_review_state": "pending",
    }) == 0


@pytest.mark.asyncio
async def test_one_owner_keeps_all_idle_capacity(monkeypatch):
    db = AsyncMongoMockClient().single_delivery_v134
    for index in range(3):
        await make(db, "alice", index)
    evaluate = scripted_delivery(monkeypatch)
    assert await drain(db, limit=2) == 2
    assert [c.args[0] for c in evaluate.await_args_list] == ["alice", "alice"]
    assert await db.opportunities.count_documents({
        "owner_id": "alice", "delivery_review_state": "pending",
    }) == 1


@pytest.mark.asyncio
async def test_owner_scoped_admission_cannot_consume_another_owners_review(monkeypatch):
    db = AsyncMongoMockClient().scoped_delivery_v134
    await make(db, "alice", 0)
    await make(db, "bob", 0)
    evaluate = scripted_delivery(monkeypatch)

    assert await drain(db, owner_id="alice", limit=2) == 1
    assert [c.args[0] for c in evaluate.await_args_list] == ["alice"]
    assert await db.opportunities.count_documents({
        "owner_id": "bob", "delivery_review_state": "pending",
    }) == 1
    assert await drain(db, owner_id="bob", limit=2) == 1
    assert [c.args[0] for c in evaluate.await_args_list] == ["alice", "bob"]


@pytest.mark.asyncio
async def test_concurrent_workers_do_not_review_the_same_opportunity(monkeypatch):
    db = AsyncMongoMockClient().concurrent_delivery_v134
    row = await make(db, "alice", 0)
    evaluate = scripted_delivery(monkeypatch)

    import asyncio
    results = await asyncio.gather(
        drain(db, limit=1), drain(db, limit=1),
    )
    assert sorted(results) == [0, 1]
    assert evaluate.await_count == 1
    saved = await db.opportunities.find_one({"id": row.id})
    assert saved["delivery_review_state"] == "settled"
