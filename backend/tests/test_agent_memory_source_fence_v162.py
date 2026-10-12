"""Memory versions fence prepared work and queued communication at reuse time.

All records and transports are synthetic. These checks exercise actual stores
and service boundaries; they do not send a notification or call a real model.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.memory_fence import (
    MemorySourcesUnavailable, inspect_memory_sources, memory_result_current,
)
from agent.models import (
    ActionStep, AgentEvidence, AutonomousGoal, CommunicationNeed,
    ResultProvenance, VisibilityDecision,
)
from agent.preparation import prepare
from agent.providers import read_internal_state
from agent.service import AgentService
from agent.source_refresh import refresh
from agent.visibility import VisibilityService
from delivery.models import DeliveryPlan, PushCopy
from delivery.service import DeliveryService

OWNER = "memory-fence-v162-synthetic"
MEMORY = "mem_16200000000000000001"
OLD_TEXT = "Costo annotato: 120 euro per dodici mesi."
NEW_TEXT = "Costo corretto: 150 euro per dodici mesi."


class FakePush:
    def __init__(self):
        self.sent = []
        self.cancelled = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return {"ok": True}

    async def cancel(self, **kwargs):
        self.cancelled.append(kwargs)
        return {"ok": True}


async def read_evidence(db, service, goal):
    result = await read_internal_state(db, OWNER, goal)
    assert result.status == "succeeded"
    evidence = AgentEvidence(
        owner_id=OWNER, goal_id=goal.id, claim=result.claims[0].text,
        provenance=result.provenance,
    )
    await service.evidence.record(evidence)
    return evidence


async def seed(monkeypatch, *, explicit=True):
    from delivery import context, provider, reasoning

    db = AsyncMongoMockClient().memory_fence_v162
    service = AgentService(db)
    await service.repo.ensure_indexes()
    await service.evidence.ensure_indexes()
    await service.needs.ensure_indexes()
    await VisibilityService(db).ensure_indexes()
    await DeliveryService(db).repo.ensure_indexes()
    channel = FakePush()
    monkeypatch.setattr(provider, "get_provider", lambda: channel)
    monkeypatch.setattr(context, "build", AsyncMock(return_value={"app_state": "background"}))
    monkeypatch.setattr(reasoning, "decide_delivery", AsyncMock(return_value={
        "mode": "push", "timing": "now", "reason_to_interrupt": "Confronto sintetico utile",
        "copy": {"title": "Il confronto è pronto", "body": "Apri il risultato in ORA."},
    }))
    monkeypatch.setattr(DeliveryService, "_may_push", AsyncMock(return_value=(True, "")))
    monkeypatch.setattr(DeliveryService, "_arrange_wake", AsyncMock())
    goal = AutonomousGoal(
        owner_id=OWNER, status="active", objective="Confrontare i costi annotati",
        desired_outcome="Una bozza sostenuta dalle memorie attuali",
        source_kind="memory", source_refs=[MEMORY] if explicit else [],
    )
    await service.repo.save_goal(goal)
    memory = {
        "id": MEMORY, "user_id": OWNER, "status": "active", "revision": 1,
        "statement": OLD_TEXT, "content": OLD_TEXT,
        "authority": "user_asserted", "epistemic_status": "known",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.memories.insert_one(memory)
    evidence = await read_evidence(db, service, goal)
    return db, service, goal, evidence, channel


async def withdraw(db):
    await db.memories.update_one({"id": MEMORY, "user_id": OWNER}, {
        "$set": {"status": "forgotten"}, "$inc": {"revision": 1},
    })


async def queued_need(db, service, goal, evidence):
    snapshot = (await inspect_memory_sources(db, OWNER, goal)).snapshot
    need = await service.needs.raise_need(CommunicationNeed(
        owner_id=OWNER, goal_id=goal.id, kind="useful_result",
        summary="Il confronto dei costi annotati è disponibile.",
        reason="La bozza cita la memoria corrente.", source_refs=[evidence.id],
        memory_source_snapshot=snapshot,
    ))
    plan = DeliveryPlan(
        owner_id=OWNER, source_type="agent_need", source_id=need.id, mode="push",
        words=PushCopy(title="Il confronto è pronto", body="Apri il risultato in ORA."),
        not_before=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        not_after=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    await DeliveryService(db).repo.save_plan(plan)
    return need, plan


def memory_read_outage(monkeypatch, db):
    cls = type(db.memories)
    original = cls.find

    def find(collection, *args, **kwargs):
        if collection.name == "memories":
            raise TimeoutError("synthetic source read timeout")
        return original(collection, *args, **kwargs)

    monkeypatch.setattr(cls, "find", find)


@pytest.mark.asyncio
async def test_internal_source_metadata_is_not_model_evidence(monkeypatch):
    db, service, goal, evidence, _ = await seed(monkeypatch)
    state = await inspect_memory_sources(db, OWNER, goal)
    assert state.status == "current" and len(state.snapshot) == 64
    assert evidence.provenance.memory_read_scope == "versioned"
    assert evidence.provenance.source_versions[MEMORY]
    assert "source_versions" not in evidence.for_ai()
    assert "memory_read_scope" not in evidence.for_ai()
    decision = VisibilityDecision(memory_source_snapshot=state.snapshot)
    assert "memory_source_snapshot" not in decision.for_human()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["forgotten", "foreign", "missing", "legacy_inline", "authority"])
async def test_prepared_source_requires_its_owned_current_version(monkeypatch, change):
    db, service, goal, evidence, _ = await seed(monkeypatch, explicit=False)
    goal.prepared_text, goal.prepared_sources = OLD_TEXT, [evidence.id]
    await service.repo.save_goal(goal)
    old = (await inspect_memory_sources(db, OWNER, goal)).snapshot
    if change == "forgotten":
        await withdraw(db)
    elif change == "foreign":
        await db.memories.update_one({"id": MEMORY}, {"$set": {"user_id": "other-owner"}})
    elif change == "missing":
        await db.memories.delete_one({"id": MEMORY})
    elif change == "authority":
        await db.memories.update_one({"id": MEMORY}, {"$set": {"authority": "model_inferred"}})
    else:
        # Legacy in-place edits did not always increment a revision counter.
        await db.memories.update_one({"id": MEMORY}, {"$set": {"statement": NEW_TEXT}})
    state = await inspect_memory_sources(db, OWNER, goal)
    assert state.status == ("changed" if change in ("legacy_inline", "authority") else "revoked")
    assert not await memory_result_current(db, OWNER, goal, old)
    assert await service.for_detail(OWNER, goal.id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("owned_backlink", [True, False])
async def test_only_governed_owned_successor_can_replace_a_source(monkeypatch, owned_backlink):
    db, service, goal, evidence, _ = await seed(monkeypatch)
    successor = "mem_16200000000000000002"
    await db.memories.update_one({"id": MEMORY}, {"$set": {
        "status": "superseded", "superseded_by": successor,
    }})
    await db.memories.insert_one({
        "id": successor, "user_id": OWNER, "status": "active", "revision": 1,
        "statement": NEW_TEXT, "supersedes_refs": [MEMORY] if owned_backlink else [],
    })
    state = await inspect_memory_sources(db, OWNER, goal)
    assert state.status == ("changed" if owned_backlink else "revoked")
    if owned_backlink:
        assert state.replacements == {MEMORY: successor}


@pytest.mark.asyncio
async def test_legacy_unreferenced_claim_is_invalidated_once_and_current_empty_read_is_honest(monkeypatch):
    db, service, goal, evidence, _ = await seed(monkeypatch, explicit=False)
    await db.agent_evidence.update_one({"id": evidence.id}, {"$set": {
        "provenance.source_refs": [], "provenance.source_versions": {},
        "provenance.memory_read_scope": "",
    }})
    goal.prepared_text, goal.prepared_sources = OLD_TEXT, [evidence.id]
    await service.repo.save_goal(goal)
    await withdraw(db)
    assert (await inspect_memory_sources(db, OWNER, goal)).status == "changed"
    assert await refresh(service, goal)
    assert goal.is_open and goal.next_run_at
    assert not goal.prepared_text and not goal.prepared_sources
    assert (await db.agent_evidence.find_one({"id": evidence.id}))["superseded"] is True
    fresh = await read_evidence(db, service, goal)
    assert fresh.provenance.memory_read_scope == "empty"
    assert fresh.provenance.source_refs == [] and fresh.provenance.source_versions == {}
    assert OLD_TEXT not in fresh.claim
    assert (await inspect_memory_sources(db, OWNER, goal)).status == "current"
    assert await refresh(service, goal) is False, "A legitimate empty read must not cause another reread loop."


@pytest.mark.asyncio
async def test_preparation_sources_remain_checked_outside_the_recent_evidence_window(monkeypatch):
    db, service, goal, evidence, _ = await seed(monkeypatch, explicit=False)
    goal.prepared_text, goal.prepared_sources = OLD_TEXT, [evidence.id]
    await service.repo.save_goal(goal)
    for index in range(45):
        newer = AgentEvidence(
            owner_id=OWNER, goal_id=goal.id, claim="Lettura sintetica senza memorie selezionate.",
            observed_at=(datetime.now(timezone.utc) + timedelta(seconds=index + 1)).isoformat(),
            provenance=ResultProvenance(
                source_class="internal_observation", capability="information.read",
                provider="life_memory", memory_read_scope="empty",
            ),
        )
        await service.evidence.record(newer)
    await withdraw(db)
    assert (await inspect_memory_sources(db, OWNER, goal)).status == "revoked"


@pytest.mark.asyncio
@pytest.mark.parametrize("lost", ["deleted", "superseded"])
async def test_missing_prepared_evidence_cannot_certify_old_text_from_current_database(monkeypatch, lost):
    db, service, goal, evidence, _ = await seed(monkeypatch, explicit=False)
    goal.prepared_text, goal.prepared_sources = OLD_TEXT, [evidence.id]
    await service.repo.save_goal(goal)
    if lost == "deleted":
        await db.agent_evidence.delete_one({"id": evidence.id})
    else:
        await db.agent_evidence.update_one({"id": evidence.id}, {"$set": {"superseded": True}})
    await withdraw(db)
    state = await inspect_memory_sources(db, OWNER, goal)
    assert state.status != "current"
    assert await service.for_detail(OWNER, goal.id) is None
    assert await service.for_home(OWNER) == []


@pytest.mark.asyncio
async def test_correction_clears_old_preparation_without_overriding_explicit_user_defer(monkeypatch):
    db, service, goal, evidence, _ = await seed(monkeypatch, explicit=False)
    goal.prepared_text, goal.prepared_sources = OLD_TEXT, [evidence.id]
    await service.repo.save_goal(goal)
    until = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    goal = await service.repo.defer_goal(OWNER, goal.id, until=until)
    await db.memories.update_one({"id": MEMORY}, {"$set": {"statement": NEW_TEXT}})
    assert await refresh(service, goal)
    current = await service.repo.get_goal(OWNER, goal.id)
    assert current.status == "waiting" and current.user_deferred_until == current.next_run_at == until
    assert not current.prepared_text and not current.prepared_sources
    assert not current.requires_user_input and not current.requires_user_authority


@pytest.mark.asyncio
@pytest.mark.parametrize("withdraw_on_call", [1, 2])
async def test_revocation_during_draft_or_audit_never_persists_old_content(monkeypatch, withdraw_on_call):
    from agent import reasoning

    db, service, goal, evidence, _ = await seed(monkeypatch)
    calls = []

    async def answer(*args, **kwargs):
        calls.append(args)
        if len(calls) == withdraw_on_call:
            await withdraw(db)
        return {"content": OLD_TEXT, "verified": True, "evidence_ids": [evidence.id]}

    monkeypatch.setattr(reasoning, "_ask_model", answer)
    step = ActionStep(step_type="prepare", capability_needed="document.create", intent="Preparare una bozza")
    result = await prepare(db, OWNER, goal, step)
    assert result.status == "unavailable" and result.retryable
    assert result.error_type == "preparation_memory_changed"
    assert len(calls) == withdraw_on_call
    assert not (await service.repo.get_goal(OWNER, goal.id)).prepared_text
    assert not goal.prepared_text


@pytest.mark.asyncio
async def test_old_visibility_cannot_borrow_fresh_evidence_after_correction(monkeypatch):
    db, service, goal, evidence, _ = await seed(monkeypatch)
    snapshot = (await inspect_memory_sources(db, OWNER, goal)).snapshot
    decision = VisibilityDecision(
        goal_id=goal.id, outcome="inform_user", headline=OLD_TEXT,
        refs=[evidence.id], memory_source_snapshot=snapshot, fingerprint="old-memory-result",
    )
    visibility = VisibilityService(db)
    assert await visibility._record(OWNER, decision)
    assert (await visibility.recent(OWNER))[0]["said"] == OLD_TEXT
    await db.memories.update_one({"id": MEMORY}, {"$set": {"statement": NEW_TEXT, "content": NEW_TEXT}})
    assert await refresh(service, goal)
    await read_evidence(db, service, goal)
    assert (await inspect_memory_sources(db, OWNER, goal)).status == "current"
    assert not await visibility.show(OWNER, goal, decision)
    assert await visibility.recent(OWNER) == []
    assert await db.ambient_activity.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["evaluate", "due", "send"])
async def test_queued_need_never_reaches_transport_after_memory_withdrawal(monkeypatch, boundary):
    from delivery import reasoning

    db, service, goal, evidence, channel = await seed(monkeypatch)
    need, plan = await queued_need(db, service, goal, evidence)
    await withdraw(db)
    delivery = DeliveryService(db)
    if boundary == "evaluate":
        from delivery.models import DeliverySubject
        result = await delivery.evaluate_subject(OWNER, DeliverySubject.model_validate(need.as_subject()))
        assert result.blocked_by == "agent_need_source_changed"
    elif boundary == "due":
        assert await delivery.deliver_due(OWNER) == {"sent": 0, "cancelled": 1, "held": 0}
    else:
        await delivery._send(OWNER, plan)
    assert channel.sent == []
    reasoning.decide_delivery.assert_not_awaited()
    assert (await delivery.repo.get_plan(OWNER, plan.id)).status == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["evaluate", "due", "send"])
async def test_source_read_outage_defers_same_plan_and_recovers_without_false_revocation(monkeypatch, boundary):
    from delivery import reasoning
    from delivery.models import DeliverySubject

    db, service, goal, evidence, channel = await seed(monkeypatch)
    need, plan = await queued_need(db, service, goal, evidence)
    delivery = DeliveryService(db)
    with monkeypatch.context() as outage:
        memory_read_outage(outage, db)
        with pytest.raises(MemorySourcesUnavailable):
            await inspect_memory_sources(db, OWNER, goal)
        if boundary == "evaluate":
            result = await delivery.evaluate_subject(OWNER, DeliverySubject.model_validate(need.as_subject()))
            assert result.unavailable and result.blocked_by == "source_check_unavailable"
        elif boundary == "due":
            assert await delivery.deliver_due(OWNER) == {"sent": 0, "cancelled": 0, "held": 1}
        else:
            await delivery._send(OWNER, plan)
        held = await delivery.repo.get_plan(OWNER, plan.id)
        assert held.status == "pending"
        assert datetime.fromisoformat(held.not_before) > datetime.now(timezone.utc) + timedelta(seconds=110)
        assert channel.sent == channel.cancelled == []
        reasoning.decide_delivery.assert_not_awaited()
        assert (await service.repo.get_goal(OWNER, goal.id)).is_open
    await db.delivery_plans.update_one({"id": plan.id}, {"$set": {
        "not_before": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    }})
    assert await delivery.deliver_due(OWNER) == {"sent": 1, "cancelled": 0, "held": 0}
    assert len(channel.sent) == 1
    assert await delivery.deliver_due(OWNER) == {"sent": 0, "cancelled": 0, "held": 0}
    assert len(channel.sent) == 1


@pytest.mark.asyncio
async def test_permission_example_cannot_quote_a_withdrawn_memory_result(monkeypatch):
    db, service, goal, evidence, channel = await seed(monkeypatch)
    _, plan = await queued_need(db, service, goal, evidence)
    plan.status = "held"
    plan.rationale = "no_notification_permission"
    plan.reason_to_open = OLD_TEXT
    delivery = DeliveryService(db)
    await delivery.repo.save_plan(plan)
    assert (await delivery.permission_moment(OWNER))["example"] == OLD_TEXT
    await withdraw(db)
    assert await delivery.permission_moment(OWNER) is None
    assert channel.sent == channel.cancelled == []  # The read has no side effects.


@pytest.mark.asyncio
async def test_direct_opportunity_delivery_checks_canonically_withdrawn_memory(monkeypatch):
    from opportunities.models import EvidenceRef, Opportunity
    from opportunities.repository import OpportunityRepository
    from delivery import reasoning

    db, service, goal, evidence, channel = await seed(monkeypatch)
    opportunity = Opportunity(
        owner_id=OWNER, identity_key="memory-fence:queued", status="active",
        semantic_summary=OLD_TEXT, why_it_matters="Una nota sintetica da verificare",
        evidence=[EvidenceRef(kind="memory", ref=MEMORY, summary=OLD_TEXT)],
    )
    await OpportunityRepository(db).save(opportunity)
    delivery = DeliveryService(db)
    plan = DeliveryPlan(owner_id=OWNER, source_id=opportunity.id, mode="push")
    await delivery.repo.save_plan(plan)
    await withdraw(db)
    assert (await delivery.evaluate(OWNER, opportunity.id)).blocked_by == "memory_sources_changed"
    assert (await delivery.repo.get_plan(OWNER, plan.id)).status == "cancelled"
    reasoning.decide_delivery.assert_not_awaited()
    assert channel.sent == []
