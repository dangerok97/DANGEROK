"""A verified final result remains deliverable after work itself has stopped.

The reader, verifier/closure orchestration, stores and Delivery run normally
against an in-process database. Model answers and the transport are fixtures;
no notification, model request or user account is accessed.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.memory_fence import inspect_memory_sources
from agent.models import (
    ActionPlan, ActionStep, AgentBudget, AgentEvidence, AgentRun, AutonomousGoal,
    CommunicationNeed, ResultProvenance, VisibilityDecision,
)
from agent.needs import NeedService
from agent.service import AgentService
from delivery.service import DeliveryService


OWNER = "synthetic-final-result-v162"
MEMORY = "mem_synthetic_final_result_v162"


class FakePush:
    def __init__(self):
        self.sent = []
        self.cancelled = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return {"ok": True, "provider": "synthetic_final_result"}

    async def cancel(self, **kwargs):
        self.cancelled.append(kwargs)
        return {"ok": True}


def push(when=None):
    return {
        "mode": "push", "timing": "at" if when else "now", "not_before": when,
        "reason_to_interrupt": "Il risultato verificato è utile adesso.",
        "reason_to_open": "Leggere il risultato già preparato.",
        "copy": {"title": "Il confronto è pronto", "body": "Apri il risultato in ORA."},
    }


async def seed(monkeypatch, *, memory=True):
    from agent import reasoning as agent_reasoning
    from delivery import context, provider, reasoning

    db = AsyncMongoMockClient().final_result_v162
    service = AgentService(db)
    await service.repo.ensure_indexes()
    await service.evidence.ensure_indexes()
    await service.needs.ensure_indexes()
    await DeliveryService(db).repo.ensure_indexes()
    channel = FakePush()
    decide = AsyncMock(return_value=push())
    monkeypatch.setattr(provider, "get_provider", lambda: channel)
    monkeypatch.setattr(context, "build", AsyncMock(return_value={"app_state": "background"}))
    monkeypatch.setattr(reasoning, "decide_delivery", decide)
    monkeypatch.setattr(DeliveryService, "_may_push", AsyncMock(return_value=(True, "")))
    monkeypatch.setattr(DeliveryService, "_arrange_wake", AsyncMock())
    monkeypatch.setattr(agent_reasoning, "verify_goal", AsyncMock(return_value={
        "outcome": "achieved", "reasoning": "Il confronto è sostenuto dalla fonte verificata.",
    }))
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())
    monkeypatch.setattr(service, "_observe_life_change", AsyncMock())

    goal = AutonomousGoal(
        owner_id=OWNER, status="active", origin="user_requested",
        source_kind="memory" if memory else "user_request",
        source_refs=[MEMORY] if memory else ["calendar:synthetic_current_source"],
        objective="Preparare un confronto sintetico", desired_outcome="Un confronto verificato e leggibile",
    )
    await service.repo.create_goal(goal)
    run = AgentRun(owner_id=OWNER, goal_id=goal.id)
    if memory:
        await db.memories.insert_one({
            "id": MEMORY, "user_id": OWNER, "status": "active", "revision": 1,
            "statement": "Opzione A: 120 euro. Opzione B: 150 euro.",
        })
        step = ActionStep(intent="Leggere la fonte del confronto", step_type="inspect",
                          capability_needed="information.read", input_refs=[MEMORY])
        result = await service.executor.run(OWNER, goal, step, may_touch_the_world=False)
        assert result.status == "succeeded"
        evidence = (await service.evidence.for_goal(OWNER, goal.id))[0]
    else:
        evidence = await service.evidence.record(AgentEvidence(
            owner_id=OWNER, goal_id=goal.id, claim="La fonte sintetica consultata conferma il confronto.",
            provenance=ResultProvenance(source_class="internal_observation", capability="calendar.read",
                                        source_refs=goal.source_refs),
        ))
    goal.prepared_text = "Confronto sintetico: A costa 120 euro; B costa 150 euro."
    goal.prepared_sources = [evidence.id]
    await service.repo.save_goal(goal)
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active")
    await service.repo.save_plan(plan)
    return SimpleNamespace(db=db, service=service, goal=goal, run=run, plan=plan,
                           evidence=evidence, channel=channel, decide=decide)


async def finish(h):
    result = await h.service._finish(OWNER, h.goal, h.plan, h.run, AgentBudget(), language="it")
    assert result["state"] == "completed"
    assert h.goal.completed_at


async def raise_result(h, *, visibility="requires_attention", refs=None):
    facts = await h.service._run_facts(OWNER, h.goal, h.run)
    decision = VisibilityDecision(
        goal_id=h.goal.id, outcome=visibility, headline="Il confronto sintetico è pronto.",
        reasoning="Il risultato è sostenuto dalle fonti consultate.",
        refs=facts["refs"] if refs is None else refs,
        memory_source_snapshot=facts["_memory_source_snapshot"],
        fingerprint="synthetic_same_visibility_topic",
    )
    return await h.service._raise_need(OWNER, h.goal, decision, facts)


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["inform_user", "requires_attention"])
@pytest.mark.parametrize("memory", [True, False])
async def test_verified_final_result_passes_real_offer_and_is_sent_only_once(monkeypatch, visibility, memory):
    h = await seed(monkeypatch, memory=memory)
    await finish(h)
    need = await raise_result(h, visibility=visibility)

    plans = await DeliveryService(h.db).repo.plans_for(OWNER, need.id, source_type="agent_need")
    assert len(plans) == 1 and plans[0].status == "delivered"
    assert plans[0].deep_link == f"/aggiornamento/{h.goal.id}"
    assert plans[0].result_goal_id == h.goal.id and plans[0].result_completed_at == h.goal.completed_at
    assert h.channel.sent[0]["deep_link"] == plans[0].deep_link
    assert need.goal_completed_at == h.goal.completed_at
    assert not need.requires_response and need.response_kind is None
    assert len(h.channel.sent) == 1 and h.decide.await_count == 1
    detail = await h.service.for_detail(OWNER, h.goal.id)
    assert detail["state"] == "Verifica completata" and detail["prepared_text"] == h.goal.prepared_text
    again = await raise_result(h, visibility=visibility)
    assert again.id == need.id
    assert len(h.channel.sent) == 1 and h.decide.await_count == 1
    assert (await DeliveryService(h.db).deliver_due(OWNER))["sent"] == 0
    opened = await DeliveryService(h.db).record_outcome(OWNER, plans[0].id, "opened")
    assert opened["ok"] and opened["route"] == plans[0].deep_link
    assert (await h.service.needs.get(OWNER, need.id)).is_open
    assert (await h.service.repo.get_goal(OWNER, h.goal.id)).status == "completed"


@pytest.mark.asyncio
async def test_final_result_has_its_own_identity_after_same_intermediate_visibility(monkeypatch):
    h = await seed(monkeypatch)
    with patch.object(NeedService, "offer_to_delivery", AsyncMock()):
        interim = await raise_result(h, visibility="inform_user", refs=[h.evidence.id])
    original_snapshot = interim.memory_source_snapshot
    await finish(h)
    final = await raise_result(h, visibility="inform_user", refs=[h.evidence.id])

    assert final.id != interim.id and final.fingerprint != interim.fingerprint
    assert final.memory_source_snapshot == original_snapshot
    assert final.goal_completed_at == h.goal.completed_at and interim.goal_completed_at is None
    assert len(h.channel.sent) == 1
    stale = await h.service.needs.offer_to_delivery(OWNER, interim)
    assert stale.blocked_by == "agent_need_source_changed" and len(h.channel.sent) == 1


@pytest.mark.asyncio
async def test_slow_intermediate_visibility_cannot_borrow_completion_after_await(monkeypatch):
    h = await seed(monkeypatch)
    earlier = SimpleNamespace(**{**vars(h), "goal": h.goal.model_copy(deep=True)})
    original_snapshot = (await inspect_memory_sources(h.db, OWNER, earlier.goal)).snapshot
    await finish(h)
    stale = await raise_result(earlier, visibility="inform_user", refs=[h.evidence.id])
    assert stale.created_at >= h.goal.completed_at
    assert stale.memory_source_snapshot == original_snapshot and stale.goal_completed_at is None
    assert h.channel.sent == [] and h.decide.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["progress_update", "needs_information", "needs_authority"])
async def test_completion_never_revives_a_question_or_intermediate_progress(monkeypatch, kind):
    h = await seed(monkeypatch)
    await finish(h)
    state = await inspect_memory_sources(h.db, OWNER, h.goal)
    need = await h.service.needs.raise_need(CommunicationNeed(
        owner_id=OWNER, goal_id=h.goal.id, kind=kind, summary="Una vecchia richiesta sintetica.",
        source_refs=[h.evidence.id], memory_source_snapshot=state.snapshot,
        goal_completed_at=h.goal.completed_at,
    ))
    result = await h.service.needs.offer_to_delivery(OWNER, need)
    assert result.blocked_by == "agent_need_source_changed"
    assert h.channel.sent == [] and h.decide.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", [
    "missing_binding", "prior_need", "reopened", "recompleted", "wrong_owner", "wrong_goal",
    "evidence_missing", "evidence_superseded", "uncited_proof", "response_required",
])
async def test_final_binding_rejects_unrelated_or_obsolete_work(monkeypatch, damage):
    h = await seed(monkeypatch)
    await finish(h)
    with patch.object(NeedService, "offer_to_delivery", AsyncMock()):
        need = await raise_result(h, refs=[h.evidence.id])
    query = {"owner_id": OWNER, "id": need.id}
    if damage == "missing_binding":
        await h.db.agent_needs.update_one(query, {"$unset": {"goal_completed_at": ""}})
    elif damage == "prior_need":
        await h.db.agent_needs.update_one(query, {"$set": {"created_at": h.goal.created_at}})
    elif damage == "reopened":
        await h.db.agent_goals.update_one({"owner_id": OWNER, "id": h.goal.id},
                                          {"$set": {"status": "active"}})
    elif damage == "recompleted":
        later = (datetime.fromisoformat(h.goal.completed_at) + timedelta(seconds=1)).isoformat()
        await h.db.agent_goals.update_one({"owner_id": OWNER, "id": h.goal.id},
                                          {"$set": {"completed_at": later}})
    elif damage == "wrong_owner":
        await h.db.agent_evidence.update_one({"id": h.evidence.id}, {"$set": {"owner_id": "other-owner"}})
    elif damage == "wrong_goal":
        await h.db.agent_evidence.update_one({"id": h.evidence.id}, {"$set": {"goal_id": "gol_other_synthetic"}})
    elif damage == "evidence_missing":
        await h.db.agent_evidence.delete_one({"id": h.evidence.id})
    elif damage == "evidence_superseded":
        await h.db.agent_evidence.update_one({"id": h.evidence.id}, {"$set": {"superseded": True}})
    elif damage == "uncited_proof":
        await h.db.agent_needs.update_one(query, {"$set": {"source_refs": ["evd_unrelated"]}})
    else:
        await h.db.agent_needs.update_one(query, {"$set": {"requires_response": True}})

    result = await h.service.needs.offer_to_delivery(OWNER, need)
    assert result.blocked_by == "agent_need_source_changed"
    assert h.channel.sent == [] and h.decide.await_count == 0
    assert await DeliveryService(h.db)._current_agent_need("other-owner", need.id) is None


@pytest.mark.asyncio
async def test_same_goal_completion_journal_can_anchor_bounded_refs(monkeypatch):
    h = await seed(monkeypatch)
    await finish(h)
    journal = await h.db.agent_journal.find_one({"owner_id": OWNER, "goal_id": h.goal.id,
                                                "kind": "goal_completed"})
    need = await raise_result(h, refs=[f"journal:{journal['at']}"])
    assert len(h.channel.sent) == 1
    assert need.goal_completed_at == h.goal.completed_at


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["unchanged", "correction", "forgotten", "cancelled", "outage"])
async def test_scheduled_result_rechecks_current_source_before_any_transport(monkeypatch, change):
    h = await seed(monkeypatch)
    await finish(h)
    h.decide.return_value = push((datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    need = await raise_result(h)
    plans = await DeliveryService(h.db).repo.plans_for(OWNER, need.id, source_type="agent_need")
    assert len(plans) == 1 and plans[0].status == "pending" and h.channel.sent == []
    plan = plans[0]
    await h.db.delivery_plans.update_one({"id": plan.id}, {"$set": {
        "not_before": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    }})
    if change == "correction":
        await h.db.memories.update_one({"id": MEMORY, "user_id": OWNER}, {
            "$set": {"statement": "Confronto corretto: A costa 160 euro."}, "$inc": {"revision": 1},
        })
    elif change == "forgotten":
        await h.db.memories.update_one({"id": MEMORY, "user_id": OWNER}, {"$set": {"status": "forgotten"}})
    elif change == "cancelled":
        await h.db.agent_goals.update_one({"id": h.goal.id, "owner_id": OWNER}, {"$set": {"status": "cancelled"}})
    elif change == "outage":
        cls, original = type(h.db.memories), type(h.db.memories).find

        def find(collection, *args, **kwargs):
            if collection.name == "memories":
                raise TimeoutError("synthetic source read outage")
            return original(collection, *args, **kwargs)

        monkeypatch.setattr(cls, "find", find)
    h.decide.return_value = push()
    result = await DeliveryService(h.db).deliver_due(OWNER)
    saved = await DeliveryService(h.db).repo.get_plan(OWNER, plan.id)
    if change == "unchanged":
        assert result["sent"] == 1 and saved.status == "delivered"
        assert len(h.channel.sent) == 1 and h.decide.await_count == 2
    elif change == "outage":
        assert result["held"] == 1 and saved.status == "pending"
        assert h.channel.sent == [] and h.decide.await_count == 1
    else:
        assert result["cancelled"] == 1 and saved.status == "cancelled"
        assert h.channel.sent == [] and h.decide.await_count == 1


@pytest.mark.asyncio
async def test_source_correction_during_channel_judgement_stops_send(monkeypatch):
    h = await seed(monkeypatch)
    await finish(h)

    async def decide(*args, **kwargs):
        await h.db.memories.update_one({"id": MEMORY, "user_id": OWNER},
                                       {"$set": {"statement": "Dato sintetico corretto durante l'attesa."}})
        return push()

    h.decide.side_effect = decide
    await raise_result(h)
    assert h.decide.await_count == 1 and h.channel.sent == []
    plans = await h.db.delivery_plans.find({"owner_id": OWNER}).to_list(2)
    assert len(plans) == 1 and plans[0]["status"] == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["silence", "quiet_presence", "in_app"])
async def test_final_result_does_not_force_a_push(monkeypatch, mode):
    h = await seed(monkeypatch)
    await finish(h)
    h.decide.return_value = {"mode": mode}
    await raise_result(h)
    assert h.decide.await_count == 1 and h.channel.sent == []
    assert await h.db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_missing_push_permission_holds_a_result_with_its_exact_target(monkeypatch):
    h = await seed(monkeypatch)
    await finish(h)
    permission = AsyncMock(return_value=(False, "no_notification_permission"))
    monkeypatch.setattr(DeliveryService, "_may_push", permission)
    need = await raise_result(h)
    plan = (await DeliveryService(h.db).repo.plans_for(OWNER, need.id, source_type="agent_need"))[0]
    assert plan.status == "held" and h.channel.sent == []
    assert plan.result_goal_id == h.goal.id and plan.deep_link == f"/aggiornamento/{h.goal.id}"
    permission.return_value = (True, "")
    assert (await DeliveryService(h.db).deliver_due(OWNER))["sent"] == 1
    assert len(h.channel.sent) == 1 and h.channel.sent[0]["deep_link"] == plan.deep_link


@pytest.mark.asyncio
@pytest.mark.parametrize("tampering", ["url", "target", "completion", "need", "missing_binding"])
async def test_final_notification_target_cannot_be_substituted_before_send_or_open(monkeypatch, tampering):
    h = await seed(monkeypatch)
    await finish(h)
    h.decide.return_value = push((datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    need = await raise_result(h)
    delivery = DeliveryService(h.db)
    plan = (await delivery.repo.plans_for(OWNER, need.id, source_type="agent_need"))[0]
    if tampering == "url":
        plan.deep_link = "/aggiornamento/gol_other_synthetic"
    elif tampering == "target":
        plan.result_goal_id = "gol_other_synthetic"
        plan.deep_link = f"/aggiornamento/{plan.result_goal_id}"
    elif tampering == "completion":
        plan.result_completed_at = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    elif tampering == "need":
        other = await h.service.needs.raise_need(CommunicationNeed(
            owner_id=OWNER, goal_id="gol_other_synthetic", kind="important_outcome",
            summary="Risultato di un altro lavoro.",
        ))
        plan.source_id = other.id
    else:
        plan.result_completed_at = None
    await delivery.repo.save_plan(plan)
    assert await delivery._current_subject_for_plan(OWNER, plan) is None
    await delivery._send(OWNER, plan)
    assert h.channel.sent == [] and h.decide.await_count == 1

    # A forged delivery receipt cannot turn the same bad target into a link.
    plan.status, plan.outcome = "delivered", "delivered"
    await delivery.repo.save_plan(plan)
    opened = await delivery.record_outcome(OWNER, plan.id, "opened")
    assert opened == {"ok": False, "reason": "invalid_notification_target"}
    assert (await delivery.repo.get_plan(OWNER, plan.id)).opened_at is None
    assert await delivery.record_outcome("other-owner", plan.id, "opened") == {
        "ok": False, "reason": "unknown_plan",
    }


@pytest.mark.asyncio
async def test_result_tap_rereads_the_current_source_without_reviving_a_question(monkeypatch):
    h = await seed(monkeypatch)
    await finish(h)
    need = await raise_result(h)
    delivery = DeliveryService(h.db)
    plan = (await delivery.repo.plans_for(OWNER, need.id, source_type="agent_need"))[0]
    await h.db.memories.update_one({"user_id": OWNER, "id": MEMORY}, {"$set": {"status": "forgotten"}})
    opened = await delivery.record_outcome(OWNER, plan.id, "opened")
    assert opened == {"ok": False, "reason": "invalid_notification_target"}
    assert len(h.channel.sent) == 1 and (await h.service.needs.get(OWNER, need.id)).is_open


@pytest.mark.asyncio
async def test_journal_proof_must_belong_to_this_exact_owned_completion(monkeypatch):
    h = await seed(monkeypatch, memory=False)
    await finish(h)
    journal = await h.db.agent_journal.find_one({"owner_id": OWNER, "goal_id": h.goal.id,
                                                "kind": "goal_completed"})
    await h.db.agent_journal.update_one({"owner_id": OWNER, "goal_id": h.goal.id, "at": journal["at"]},
                                       {"$set": {"goal_id": "gol_other_synthetic"}})
    await raise_result(h, refs=[f"journal:{journal['at']}"])
    assert h.channel.sent == [] and h.decide.await_count == 0


@pytest.mark.asyncio
async def test_verified_result_without_a_draft_still_uses_real_owned_evidence(monkeypatch):
    h = await seed(monkeypatch, memory=False)
    h.goal.prepared_text, h.goal.prepared_sources = "", []
    await h.service.repo.save_goal(h.goal)
    await finish(h)
    await raise_result(h, refs=[h.evidence.id])
    assert len(h.channel.sent) == 1
    assert h.channel.sent[0]["deep_link"] == f"/aggiornamento/{h.goal.id}"


@pytest.mark.asyncio
@pytest.mark.parametrize("source_state", ["resolved", "dismissed", "suppressed", "missing", "expired", "foreign"])
async def test_final_result_respects_later_source_dismissal_after_automatic_resolution(monkeypatch, source_state):
    from agent.source_refresh import context
    from opportunities.models import EvidenceRef, Opportunity
    from opportunities.repository import OpportunityRepository
    from opportunities.service import OpportunityService

    h = await seed(monkeypatch)
    source = await OpportunityRepository(h.db).save(Opportunity(
        owner_id=OWNER, status="active", identity_key="synthetic-final-result",
        semantic_summary="Confrontare le opzioni annotate.",
        why_it_matters="Un confronto riduce il lavoro richiesto alla persona.",
        initiative="prepare", evidence=[EvidenceRef(kind="memory", ref=MEMORY)],
    ))
    row = await h.db.opportunities.find_one({"owner_id": OWNER, "id": source.id})
    h.goal.origin = "agent_initiated"
    h.goal.source_kind = "opportunity"
    h.goal.opportunity_id = source.id
    h.goal.opportunity_revision = row["agent_review_revision"]
    h.goal.source_situation = context(row)
    await h.service.repo.save_goal(h.goal)
    await finish(h)
    resolved = await OpportunityRepository(h.db).get(OWNER, source.id)
    assert resolved.status == "resolved", "Normal completion really resolves its source."
    h.decide.return_value = push((datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    need = await raise_result(h)
    delivery = DeliveryService(h.db)
    plan = (await delivery.repo.plans_for(OWNER, need.id, source_type="agent_need"))[0]
    assert plan.status == "pending" and h.channel.sent == []
    if source_state in ("dismissed", "suppressed"):
        dismissed = await OpportunityService(h.db).dismiss(OWNER, source.id, suppress=source_state == "suppressed")
        assert dismissed["ok"] and not dismissed["goal_cancelled"]
    elif source_state == "missing":
        await h.db.opportunities.delete_one({"owner_id": OWNER, "id": source.id})
    elif source_state == "expired":
        await h.db.opportunities.update_one({"owner_id": OWNER, "id": source.id}, {"$set": {
            "valid_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }})
    elif source_state == "foreign":
        await h.db.opportunities.update_one({"owner_id": OWNER, "id": source.id}, {"$set": {"owner_id": "other-owner"}})
    await h.db.delivery_plans.update_one({"id": plan.id}, {"$set": {
        "not_before": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    }})
    h.decide.return_value = push()
    result = await delivery.deliver_due(OWNER)
    if source_state == "resolved":
        assert result["sent"] == 1 and len(h.channel.sent) == 1 and h.decide.await_count == 2
    else:
        assert result["cancelled"] == 1 and h.channel.sent == [] and h.decide.await_count == 1
