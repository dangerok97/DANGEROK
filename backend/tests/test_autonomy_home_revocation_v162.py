"""A dismissed source cannot be revived by a durable Home handoff.

The reader, completion, Opportunity lifecycle, outbox and Home readback use
the real code against an isolated database. Only the model's verification
answer is controlled; no model, notification or real account is accessed.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionPlan, ActionStep, AgentBudget, AgentRun, AutonomousGoal, VisibilityDecision
from agent.service import AgentService
from agent.source_refresh import context
from agent.visibility import VisibilityService
from delivery.service import DeliveryService
from opportunities.models import EvidenceRef, Opportunity
from opportunities.repository import OpportunityRepository
from opportunities.service import OpportunityService


OWNER = "synthetic-home-revocation-v162"
MEMORY = "mem_synthetic_home_revocation_v162"


async def completed_handoff(monkeypatch):
    from agent import reasoning

    db = AsyncMongoMockClient().home_revocation_v162
    service = AgentService(db)
    visibility = VisibilityService(db)
    await service.repo.ensure_indexes()
    await service.evidence.ensure_indexes()
    await visibility.ensure_indexes()
    await DeliveryService(db).repo.ensure_indexes()
    await db.memories.insert_one({
        "id": MEMORY, "user_id": OWNER, "status": "active", "revision": 1,
        "statement": "Opzione sintetica A: 20 euro; opzione sintetica B: 25 euro.",
    })
    source = await OpportunityRepository(db).save(Opportunity(
        owner_id=OWNER, status="active", identity_key="synthetic-home-revocation",
        semantic_summary="Preparare il confronto delle due opzioni annotate.",
        why_it_matters="Il confronto scritto manca ancora.", initiative="prepare",
        evidence=[EvidenceRef(kind="memory", ref=MEMORY)],
    ))
    source_row = await db.opportunities.find_one({"owner_id": OWNER, "id": source.id})
    goal = AutonomousGoal(
        owner_id=OWNER, status="active", origin="agent_initiated",
        source_kind="opportunity", source_refs=[MEMORY], opportunity_id=source.id,
        opportunity_revision=source_row["agent_review_revision"], source_situation=context(source_row),
        objective="Confrontare le due opzioni annotate", desired_outcome="Un confronto scritto leggibile",
    )
    await service.repo.create_goal(goal)
    read = ActionStep(intent="Leggere la nota del confronto", step_type="inspect",
                      capability_needed="information.read", input_refs=[MEMORY])
    result = await service.executor.run(OWNER, goal, read, may_touch_the_world=False)
    assert result.status == "succeeded"
    evidence = (await service.evidence.for_goal(OWNER, goal.id))[0]
    goal.prepared_text = "Secondo la nota, A costa 20 euro e B costa 25 euro: la differenza è 5 euro."
    goal.prepared_sources = [evidence.id]
    await service.repo.save_goal(goal)
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active")
    await service.repo.save_plan(plan)
    run = AgentRun(owner_id=OWNER, goal_id=goal.id)
    monkeypatch.setattr(reasoning, "verify_goal", AsyncMock(return_value={
        "outcome": "achieved", "reasoning": "Il confronto è sostenuto dalla nota letta.",
    }))
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())
    monkeypatch.setattr(service, "_observe_life_change", AsyncMock())
    outcome = await service._finish(OWNER, goal, plan, run, AgentBudget(), language="it")
    assert outcome["state"] == "completed" and goal.completed_at
    assert (await OpportunityRepository(db).get(OWNER, source.id)).status == "resolved"

    facts = await service._run_facts(OWNER, goal, run)
    decision = VisibilityDecision(
        goal_id=goal.id, outcome="inform_user", headline="Il confronto verificato è pronto in ORA.",
        reasoning="La nota letta sostiene il risultato già preparato.", refs=facts["refs"],
        memory_source_snapshot=facts["_memory_source_snapshot"], fingerprint="synthetic-home-result",
    )
    assert await visibility._record(OWNER, decision)
    return SimpleNamespace(db=db, service=service, visibility=visibility, goal=goal,
                           source=source, decision=decision)


async def due_again(h):
    await h.db.agent_updates.update_one(
        {"owner_id": OWNER, "fingerprint": h.decision.fingerprint},
        {"$set": {"home_due_at": (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()}},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("suppress", [False, True])
async def test_source_dismissed_after_completion_is_not_replayed_to_home(monkeypatch, suppress):
    h = await completed_handoff(monkeypatch)
    dismissed = await OpportunityService(h.db).dismiss(OWNER, h.source.id, suppress=suppress)
    assert dismissed["ok"] and not dismissed["goal_cancelled"]
    assert (await h.service.repo.get_goal(OWNER, h.goal.id)).status == "completed"

    recovered = await h.visibility.recover_pending_home()

    assert recovered == {"checked": 1, "shown": 0, "deferred": 0, "stale": 1}
    assert await h.db.ambient_activity.count_documents({"owner_id": OWNER}) == 0
    assert await DeliveryService(h.db).ambient_line(OWNER) is None
    saved = await h.db.agent_updates.find_one({"owner_id": OWNER, "fingerprint": h.decision.fingerprint})
    assert saved["home_pending"] is False and "home_due_at" not in saved
    assert saved["home_skipped"] == "opportunity_no_longer_current"
    assert (await h.visibility.recover_pending_home())["checked"] == 0


@pytest.mark.asyncio
async def test_already_materialised_home_line_is_hidden_after_source_dismissal(monkeypatch):
    h = await completed_handoff(monkeypatch)
    assert await h.visibility.show(OWNER, h.goal, h.decision)
    assert (await DeliveryService(h.db).ambient_line(OWNER))["text"] == h.decision.headline
    assert (await OpportunityService(h.db).dismiss(OWNER, h.source.id))["ok"]

    assert await DeliveryService(h.db).ambient_line(OWNER) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing", "foreign", "expired_status", "past_deadline"])
async def test_noncurrent_owned_source_never_replays_a_completed_result(monkeypatch, change):
    h = await completed_handoff(monkeypatch)
    query = {"owner_id": OWNER, "id": h.source.id}
    if change == "missing":
        await h.db.opportunities.delete_one(query)
    elif change == "foreign":
        await h.db.opportunities.update_one(query, {"$set": {"owner_id": "other-synthetic-owner"}})
    elif change == "expired_status":
        await h.db.opportunities.update_one(query, {"$set": {"status": "expired"}})
    else:
        await h.db.opportunities.update_one(query, {"$set": {
            "valid_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }})

    assert (await h.visibility.recover_pending_home())["stale"] == 1
    assert await h.db.ambient_activity.count_documents({}) == 0
    assert await DeliveryService(h.db).ambient_line(OWNER) is None
    assert await DeliveryService(h.db).ambient_line("other-synthetic-owner") is None
    assert (await h.service.repo.get_goal(OWNER, h.goal.id)).status == "completed"


@pytest.mark.asyncio
async def test_current_resolved_source_retries_home_write_once_without_new_work(monkeypatch):
    h = await completed_handoff(monkeypatch)
    original = DeliveryService.note_activity
    writes = 0

    async def fail_once(self, *args, **kwargs):
        nonlocal writes
        writes += 1
        if writes == 1:
            raise ConnectionError("synthetic Home write outage")
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(DeliveryService, "note_activity", fail_once)
    assert not await h.visibility.show(OWNER, h.goal, h.decision)
    pending = await h.db.agent_updates.find_one({"owner_id": OWNER})
    assert pending["home_pending"] and "home_skipped" not in pending
    assert await h.db.ambient_activity.count_documents({}) == 0

    await due_again(h)
    assert await h.visibility.recover_pending_home() == {"checked": 1, "shown": 1, "deferred": 0, "stale": 0}
    activity = await h.db.ambient_activity.find_one({"owner_id": OWNER})
    assert (await DeliveryService(h.db).ambient_line(OWNER))["id"] == activity["id"]
    assert await DeliveryService(h.db).ambient_line("other-synthetic-owner") is None
    assert not await h.visibility.show("other-synthetic-owner", h.goal, h.decision)
    assert (await h.visibility.recover_pending_home())["checked"] == 0
    assert writes == 2
    assert await h.db.ambient_activity.count_documents({}) == 1
    assert await h.db.agent_needs.count_documents({}) == 0
    assert await h.db.delivery_plans.count_documents({}) == 0
    assert await h.db.agent_evidence.count_documents({"provenance.capability": "information.read"}) == 1
    assert (await OpportunityRepository(h.db).get(OWNER, h.source.id)).status == "resolved"


@pytest.mark.asyncio
async def test_source_database_outage_defers_without_consuming_the_handoff(monkeypatch):
    h = await completed_handoff(monkeypatch)
    collection_type = type(h.db.opportunities)
    original = collection_type.find_one

    async def unavailable(collection, *args, **kwargs):
        if collection.name == "opportunities":
            raise TimeoutError("synthetic source read unavailable")
        return await original(collection, *args, **kwargs)

    with monkeypatch.context() as transient:
        transient.setattr(collection_type, "find_one", unavailable)
        assert await h.visibility.recover_pending_home() == {"checked": 1, "shown": 0, "deferred": 1, "stale": 0}
    pending = await h.db.agent_updates.find_one({"owner_id": OWNER})
    assert pending["home_pending"] and "home_skipped" not in pending
    assert pending["home_due_at"]
    assert await h.db.ambient_activity.count_documents({}) == 0
    await due_again(h)
    assert (await h.visibility.recover_pending_home())["shown"] == 1
    assert await h.db.ambient_activity.count_documents({}) == 1
    with monkeypatch.context() as transient:
        transient.setattr(collection_type, "find_one", unavailable)
        assert await DeliveryService(h.db).ambient_line(OWNER) is None
    assert (await DeliveryService(h.db).ambient_line(OWNER))["text"] == h.decision.headline
    assert (await h.visibility.recover_pending_home())["checked"] == 0


@pytest.mark.asyncio
async def test_known_revocation_cannot_be_reopened_by_a_delayed_home_worker(monkeypatch):
    h = await completed_handoff(monkeypatch)
    assert (await OpportunityService(h.db).dismiss(OWNER, h.source.id))["ok"]
    assert (await h.visibility.recover_pending_home())["stale"] == 1
    # A new source state cannot retroactively validate this skipped handoff.
    await h.db.opportunities.update_one({"owner_id": OWNER, "id": h.source.id},
                                       {"$set": {"status": "active"}})

    assert not await h.visibility.show(OWNER, h.goal, h.decision)
    assert (await h.visibility.recover_pending_home())["checked"] == 0
    assert await h.db.ambient_activity.count_documents({}) == 0
    assert await DeliveryService(h.db).ambient_line(OWNER) is None
    saved = await h.db.agent_updates.find_one({"owner_id": OWNER})
    assert not saved["home_pending"] and "home_delivered_at" not in saved
    assert saved["home_skipped"] == "opportunity_no_longer_current"


@pytest.mark.asyncio
async def test_dismissal_during_activity_write_is_not_acknowledged_or_exposed(monkeypatch):
    h = await completed_handoff(monkeypatch)
    original = DeliveryService.note_activity
    writes = 0

    async def withdraw_before_ack(self, *args, **kwargs):
        nonlocal writes
        writes += 1
        activity = await original(self, *args, **kwargs)
        dismissed = await OpportunityService(h.db).dismiss(OWNER, h.source.id)
        assert dismissed["ok"] and not dismissed["goal_cancelled"]
        return activity

    monkeypatch.setattr(DeliveryService, "note_activity", withdraw_before_ack)
    assert not await h.visibility.show(OWNER, h.goal, h.decision)
    assert await h.db.ambient_activity.count_documents({}) == 1  # Historical work remains recorded.
    assert await DeliveryService(h.db).ambient_line(OWNER) is None
    saved = await h.db.agent_updates.find_one({"owner_id": OWNER})
    assert saved["home_skipped"] == "opportunity_no_longer_current"
    assert not saved["home_pending"] and "home_delivered_at" not in saved

    await h.db.opportunities.update_one({"owner_id": OWNER, "id": h.source.id},
                                       {"$set": {"status": "active"}})
    assert await DeliveryService(h.db).ambient_line(OWNER) is None
    assert not await h.visibility.show(OWNER, h.goal, h.decision)
    assert writes == 1 and (await h.visibility.recover_pending_home())["checked"] == 0
    assert (await h.service.repo.get_goal(OWNER, h.goal.id)).status == "completed"


@pytest.mark.asyncio
async def test_source_withdrawn_during_home_readback_cannot_escape_the_last_check(monkeypatch):
    from delivery import service as delivery_module

    h = await completed_handoff(monkeypatch)
    assert await h.visibility.show(OWNER, h.goal, h.decision)
    original = delivery_module.memory_result_current

    async def withdraw_during_memory_read(*args, **kwargs):
        current = await original(*args, **kwargs)
        assert (await OpportunityService(h.db).dismiss(OWNER, h.source.id))["ok"]
        return current

    monkeypatch.setattr(delivery_module, "memory_result_current", withdraw_during_memory_read)
    assert await DeliveryService(h.db).ambient_line(OWNER) is None


@pytest.mark.asyncio
async def test_concurrent_revocation_wins_over_a_late_home_acknowledgement(monkeypatch):
    h = await completed_handoff(monkeypatch)
    collection_type = type(h.db.agent_updates)
    original = collection_type.update_one
    raced = False

    async def dismiss_before_ack(collection, query, update, *args, **kwargs):
        nonlocal raced
        if (not raced and collection.name == "agent_updates"
                and "home_delivered_at" in update.get("$set", {})):
            raced = True
            assert (await OpportunityService(h.db).dismiss(OWNER, h.source.id))["ok"]
            assert (await VisibilityService(h.db).recover_pending_home())["stale"] == 1
        return await original(collection, query, update, *args, **kwargs)

    monkeypatch.setattr(collection_type, "update_one", dismiss_before_ack)
    assert not await h.visibility.show(OWNER, h.goal, h.decision)
    saved = await h.db.agent_updates.find_one({"owner_id": OWNER})
    assert raced and saved["home_skipped"] == "opportunity_no_longer_current"
    assert not saved["home_pending"] and "home_delivered_at" not in saved
    assert await DeliveryService(h.db).ambient_line(OWNER) is None
