"""No Home request: every persisted opportunity must reach goal admission."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.background import consider_opportunities
from agent.service import AgentService
from opportunities.models import Opportunity
from opportunities.repository import OpportunityRepository


def opportunity(n=0, owner="alice"):
    return Opportunity(owner_id=owner, identity_key=f"concern:{n}",
        status="active", semantic_summary=f"Situazione {n}",
        why_it_matters="Conseguenze da verificare", initiative="prepare")


@pytest.mark.asyncio
async def test_all_persisted_concerns_survive_batch_limit(monkeypatch):
    db = AsyncMongoMockClient().test
    repo = OpportunityRepository(db)
    rows = [await repo.save(opportunity(i)) for i in range(5)]
    decide = AsyncMock(return_value={"outcome": "no_goal"})
    monkeypatch.setattr(AgentService, "consider", decide)
    await consider_opportunities(db, "alice", SimpleNamespace(created=rows, updated=[]))
    # Recovery must continue even if the scan object is gone and Home is closed.
    from agent.background import recover_due
    for _ in range(3):
        await recover_due(db)
    assert {c.kwargs['opportunity_id'] for c in decide.await_args_list} == {o.id for o in rows}
    assert decide.await_count == 5


@pytest.mark.asyncio
async def test_updated_opportunity_reaches_admission(monkeypatch):
    db = AsyncMongoMockClient().test
    repo = OpportunityRepository(db)
    row = await repo.save(opportunity())
    decide = AsyncMock(return_value={"outcome": "no_goal"})
    monkeypatch.setattr(AgentService, "consider", decide)
    await consider_opportunities(db, "alice", SimpleNamespace(created=[row], updated=[]))
    row.semantic_summary = "Nuovo fatto cambia la situazione"
    await repo.save(row)
    await consider_opportunities(db, "alice", SimpleNamespace(created=[], updated=[row]))
    assert decide.await_count == 2
    assert decide.await_args.kwargs['situation']['what'] == row.semantic_summary


@pytest.mark.asyncio
async def test_decision_survives_presentation_save_and_other_owner(monkeypatch):
    from agent.admission import drain
    db = AsyncMongoMockClient().test
    repo = OpportunityRepository(db)
    a = await repo.save(opportunity())
    b = await repo.save(opportunity(owner="bob"))
    decide = AsyncMock(return_value={"outcome": "no_goal"})
    monkeypatch.setattr(AgentService, "consider", decide)
    await drain(db, owner_id="alice")
    a.surface_state = "surfaced"
    await repo.save(a)
    await drain(db, owner_id="alice")
    assert decide.await_count == 1
    assert (await db.opportunities.find_one({"id": b.id}))["agent_review_state"] == "pending"
    a.status = "dismissed"
    await repo.save(a)
    await drain(db, owner_id="alice")
    assert decide.await_count == 1


@pytest.mark.asyncio
async def test_two_workers_share_one_claim(monkeypatch):
    import asyncio
    from agent.admission import drain
    db = AsyncMongoMockClient().test
    await OpportunityRepository(db).save(opportunity())
    entered, release = asyncio.Event(), asyncio.Event()
    async def slow(*a, **kw):
        entered.set()
        await release.wait()
        return {"outcome": "no_goal"}
    decide = AsyncMock(side_effect=slow)
    monkeypatch.setattr(AgentService, "consider", decide)
    first = asyncio.create_task(drain(db))
    await entered.wait()
    assert await drain(db) == 0
    release.set()
    await first
    assert decide.await_count == 1


@pytest.mark.asyncio
async def test_new_revision_during_judgement_is_not_acknowledged(monkeypatch):
    from agent.admission import drain
    db = AsyncMongoMockClient().test
    repo = OpportunityRepository(db)
    row = await repo.save(opportunity())
    async def changed(*a, **kw):
        row.semantic_summary = "Fonte aggiornata durante la valutazione"
        await repo.save(row)
        return {"outcome": "no_goal"}
    decide = AsyncMock(side_effect=changed)
    monkeypatch.setattr(AgentService, "consider", decide)
    await drain(db, limit=1)
    saved = await db.opportunities.find_one({"id": row.id})
    assert saved["agent_review_state"] == "pending"
    assert saved["agent_review_attempts"] == 0
    assert "agent_review_token" not in saved
    decide.side_effect = None
    decide.return_value = {"outcome": "no_goal"}
    await drain(db)
    assert decide.await_count == 2


@pytest.mark.asyncio
async def test_unavailable_retries_then_pauses_without_false_no_goal(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from agent.admission import drain
    db = AsyncMongoMockClient().test
    row = await OpportunityRepository(db).save(opportunity())
    decide = AsyncMock(return_value={"outcome": "unavailable"})
    monkeypatch.setattr(AgentService, "consider", decide)
    now = datetime.now(timezone.utc)
    await drain(db, now=now)
    await drain(db, now=now)
    assert decide.await_count == 1
    await drain(db, now=now + timedelta(minutes=2))
    await drain(db, now=now + timedelta(minutes=8))
    await drain(db, now=now + timedelta(days=1))
    saved = await db.opportunities.find_one({"id": row.id})
    assert saved["agent_review_state"] == "paused"
    assert saved["agent_review_outcome"] == "unavailable"
    assert decide.await_count == 3


@pytest.mark.asyncio
async def test_expired_lease_recovers_without_scan_or_home(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from agent.admission import drain
    db = AsyncMongoMockClient().test
    row = await OpportunityRepository(db).save(opportunity())
    now = datetime.now(timezone.utc)
    await db.opportunities.update_one({"id": row.id}, {"$set": {
        "agent_review_lease_until": (now + timedelta(seconds=120)).isoformat(),
        "agent_review_token": "dead-worker", "agent_review_attempts": 1}})
    decide = AsyncMock(return_value={"outcome": "no_goal"})
    monkeypatch.setattr(AgentService, "consider", decide)
    assert await drain(db, now=now) == 0
    assert await drain(db, now=now + timedelta(seconds=121)) == 1
    assert decide.await_count == 1


@pytest.mark.asyncio
async def test_wait_and_question_are_saved_not_lost(monkeypatch):
    from agent.admission import drain
    db = AsyncMongoMockClient().test
    row = await OpportunityRepository(db).save(opportunity())
    decide = AsyncMock(return_value={"outcome": "wait", "reasoning": "Attendere dati aggiornati"})
    monkeypatch.setattr(AgentService, "consider", decide)
    await drain(db)
    saved = await db.opportunities.find_one({"id": row.id})
    assert saved["agent_review_due"] and saved["agent_review_outcome"] == "wait"
    row.semantic_summary = "Nuovi dati disponibili"
    await OpportunityRepository(db).save(row)
    decide.return_value = {"outcome": "clarify", "question": "Quale contratto è ancora attivo?"}
    await drain(db)
    saved = await db.opportunities.find_one({"id": row.id})
    assert saved["agent_review_question"] == decide.return_value["question"]
    assert saved["agent_review_due"] is None


@pytest.mark.asyncio
async def test_goal_storage_failure_is_retryable(monkeypatch):
    from agent import reasoning
    db = AsyncMongoMockClient().test
    service = AgentService(db)
    monkeypatch.setattr(reasoning, "decide_goal", AsyncMock(return_value={
        "outcome": "create_goal", "objective": "Verifica", "desired_outcome": "Informazione verificata"}))
    monkeypatch.setattr(service.repo, "create_goal", AsyncMock(return_value=None))
    out = await service.consider("alice", situation={}, opportunity_id="opp_missing")
    assert out["outcome"] == "unavailable"


@pytest.mark.asyncio
async def test_real_goal_creation_and_wake_without_home(monkeypatch):
    from agent import reasoning
    from agent.background import recover_due
    db = AsyncMongoMockClient().test
    row = await OpportunityRepository(db).save(opportunity())
    monkeypatch.setattr(reasoning, "decide_goal", AsyncMock(return_value={
        "outcome": "create_goal", "objective": "Verifica le conseguenze",
        "desired_outcome": "Sapere quali impegni sono coinvolti"}))
    # Only presentation is excluded; goal persistence and wake scheduling are real code.
    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())
    await recover_due(db)
    await recover_due(db)
    assert await db.agent_goals.count_documents({"owner_id": "alice"}) == 1
    goal = await db.agent_goals.find_one({"opportunity_id": row.id})
    saved = await db.opportunities.find_one({"id": row.id})
    assert saved["agent_review_goal_id"] == goal["id"]
    assert goal["origin"] == "agent_initiated"
    assert await db.ambient_wakes.count_documents({"source_ref": f"goal:{goal['id']}"}) == 1


@pytest.mark.asyncio
async def test_expired_inactive_and_unmarked_history_do_not_start(monkeypatch):
    from agent.admission import drain
    db = AsyncMongoMockClient().test
    repo = OpportunityRepository(db)
    expired = opportunity(0)
    expired.valid_until = "2020-01-01T01:00:00+02:00"
    await repo.save(expired)
    candidate = opportunity(1)
    candidate.status = "candidate"
    await repo.save(candidate)
    await db.opportunities.insert_one(opportunity(2).model_dump())
    decide = AsyncMock()
    monkeypatch.setattr(AgentService, "consider", decide)
    await drain(db, limit=10)
    decide.assert_not_awaited()
    assert (await db.opportunities.find_one({"id": expired.id}))["agent_review_outcome"] == "expired"


@pytest.mark.asyncio
async def test_one_provider_exception_does_not_drop_the_other_concern(monkeypatch):
    from agent.admission import drain
    db = AsyncMongoMockClient().test
    repo = OpportunityRepository(db)
    await repo.save(opportunity(0))
    await repo.save(opportunity(1))
    decide = AsyncMock(side_effect=[RuntimeError("provider failed"), {"outcome": "no_goal"}])
    monkeypatch.setattr(AgentService, "consider", decide)
    assert await drain(db) == 2
    assert await db.opportunities.count_documents({"agent_review_outcome": "no_goal"}) == 1
    assert await db.opportunities.count_documents({"agent_review_state": "pending", "agent_review_error_kind": "RuntimeError"}) == 1


@pytest.mark.asyncio
async def test_live_voice_can_defer_admission_without_losing_it(monkeypatch):
    from agent.background import recover_due
    db = AsyncMongoMockClient().test
    await OpportunityRepository(db).save(opportunity())
    decide = AsyncMock(return_value={"outcome": "no_goal"})
    monkeypatch.setattr(AgentService, "consider", decide)
    await recover_due(db, admit=False)
    decide.assert_not_awaited()
    await recover_due(db)
    decide.assert_awaited_once()
