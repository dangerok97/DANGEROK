"""Opportunity bursts must reach delivery even after the scan object is gone."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from delivery.admission import drain
from delivery.service import DeliveryService
from opportunities.models import Opportunity
from opportunities.repository import OpportunityRepository


def concern(index, owner="alice"):
    return Opportunity(owner_id=owner, identity_key=f"delivery:{index}",
        status="active", semantic_summary=f"Situazione {index}",
        why_it_matters="Conseguenze da verificare", initiative="prepare")


@pytest.mark.asyncio
async def test_every_concern_is_reviewed_across_bounded_passes(monkeypatch):
    db = AsyncMongoMockClient().test
    repo = OpportunityRepository(db)
    rows = [await repo.save(concern(i)) for i in range(5)]
    decide = AsyncMock(return_value=type("Result", (), {"unavailable": False, "mode": "in_app"})())
    monkeypatch.setattr(DeliveryService, "evaluate", decide)

    assert await drain(db, owner_id="alice") == 2
    # No scan and no Home request are needed for the other three.
    assert await drain(db) == 2
    assert await drain(db) == 1
    assert await drain(db) == 0
    assert {call.args[1] for call in decide.await_args_list} == {row.id for row in rows}
    for row in rows:
        assert (await db.opportunities.find_one({"id": row.id}))["delivery_review_state"] == "settled"


@pytest.mark.asyncio
async def test_update_requeues_but_presentation_save_and_other_owner_do_not(monkeypatch):
    db = AsyncMongoMockClient().test
    repo = OpportunityRepository(db)
    row = await repo.save(concern(1))
    other = await repo.save(concern(2, "bob"))
    decide = AsyncMock(return_value=type("Result", (), {"unavailable": False, "mode": "silence"})())
    monkeypatch.setattr(DeliveryService, "evaluate", decide)
    await drain(db, owner_id="alice")
    row.surface_state = "surfaced"
    await repo.save(row)
    assert await drain(db, owner_id="alice") == 0
    row.semantic_summary = "La fonte ha cambiato il contesto"
    await repo.save(row)
    assert await drain(db, owner_id="alice") == 1
    assert decide.await_count == 2
    assert (await db.opportunities.find_one({"id": other.id}))["delivery_review_state"] == "pending"


@pytest.mark.asyncio
async def test_unavailable_retries_and_closed_concern_cancels(monkeypatch):
    db = AsyncMongoMockClient().test
    repo = OpportunityRepository(db)
    row = await repo.save(concern(1))
    decide = AsyncMock(return_value=type("Result", (), {"unavailable": True, "mode": ""})())
    cancel = AsyncMock()
    monkeypatch.setattr(DeliveryService, "evaluate", decide)
    monkeypatch.setattr(DeliveryService, "cancel_for_opportunity", cancel)
    now = datetime.now(timezone.utc)
    assert await drain(db, now=now) == 1
    assert await drain(db, now=now) == 0
    await drain(db, now=now + timedelta(minutes=2))
    await drain(db, now=now + timedelta(minutes=8))
    saved = await db.opportunities.find_one({"id": row.id})
    assert saved["delivery_review_state"] == "paused"
    assert decide.await_count == 3

    row.status = "resolved"
    await repo.save(row)
    assert await drain(db, now=now + timedelta(minutes=9)) == 1
    cancel.assert_awaited_once()
    assert (await db.opportunities.find_one({"id": row.id}))["delivery_review_outcome"] == "closed"


@pytest.mark.asyncio
async def test_two_workers_cannot_take_the_same_review(monkeypatch):
    db = AsyncMongoMockClient().test
    await OpportunityRepository(db).save(concern(1))
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        entered.set()
        await release.wait()
        return type("Result", (), {"unavailable": False, "mode": "in_app"})()

    monkeypatch.setattr(DeliveryService, "evaluate", slow)
    first = asyncio.create_task(drain(db))
    await entered.wait()
    assert await drain(db) == 0
    release.set()
    await first


@pytest.mark.asyncio
async def test_source_change_during_review_stays_due(monkeypatch):
    db = AsyncMongoMockClient().test
    repo = OpportunityRepository(db)
    row = await repo.save(concern(1))

    async def changed(*args, **kwargs):
        row.semantic_summary = "Nuovo fatto mentre ORA valuta la consegna"
        await repo.save(row)
        return SimpleNamespace(unavailable=False, mode="in_app")

    decide = AsyncMock(side_effect=changed)
    monkeypatch.setattr(DeliveryService, "evaluate", decide)
    await drain(db, limit=1)
    saved = await db.opportunities.find_one({"id": row.id})
    assert saved["delivery_review_state"] == "pending"
    assert saved["delivery_review_attempts"] == 0
    assert "delivery_review_token" not in saved
    decide.side_effect = None
    decide.return_value = SimpleNamespace(unavailable=False, mode="in_app")
    assert await drain(db) == 1
    assert decide.await_count == 2


@pytest.mark.asyncio
async def test_background_scan_starts_two_and_later_tick_gets_the_rest(monkeypatch):
    from ambient.models import AmbientWake
    from ambient.service import AmbientService
    from opportunities.discovery import OpportunityDiscovery
    from opportunities.surfacing import SurfacingService
    from agent import background

    db = AsyncMongoMockClient().test
    repo = OpportunityRepository(db)
    rows = [await repo.save(concern(i)) for i in range(5)]
    scan = SimpleNamespace(created=rows, updated=[])
    monkeypatch.setattr(OpportunityDiscovery, "review", AsyncMock(return_value=
                        SimpleNamespace(ran=True, unavailable=False, scan=scan)))
    monkeypatch.setattr(AmbientService, "_note", AsyncMock())
    monkeypatch.setattr(SurfacingService, "decide", AsyncMock())
    monkeypatch.setattr(background, "consider_opportunities", AsyncMock())
    decide = AsyncMock(return_value=SimpleNamespace(unavailable=False, mode="in_app"))
    monkeypatch.setattr(DeliveryService, "evaluate", decide)

    result = await AmbientService(db).review_life(
        AmbientWake(owner_id="alice", reason="state_changed")
    )
    assert result.result == "reviewed"
    assert decide.await_count == 2
    assert await drain(db) == 2
    assert await drain(db) == 1
    assert {call.args[1] for call in decide.await_args_list} == {row.id for row in rows}
