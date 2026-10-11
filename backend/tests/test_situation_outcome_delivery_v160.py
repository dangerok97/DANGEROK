"""A useful Situation result can arrive, but cannot outlive its actual source.

The real Situation/goal/evidence/need/delivery stores run against an in-process
test database. Model judgements and the push transport are explicit fixtures;
these tests do not assert real physical readiness or device receipt.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import (
    ActionPlan, AgentEvidence, AgentRun, AutonomousGoal, CommunicationNeed,
    ResultProvenance, VisibilityDecision,
)
from agent.needs import NeedService
from agent.service import AgentService
from ambient.models import AmbientWake
from ambient.service import AmbientService
from delivery.models import DeliveryPlan
from delivery.service import DeliveryService
from situations.followup import goal_id_for
from situations.models import SituationState, SituationUpdate
from situations.outcomes import current_outcome, outcome_refs, validate_assessment
from situations.repository import SituationRepository
from situations.service import SituationService

OWNER = "outcome-delivery-v160-synthetic"
SID = "sit_outcome_delivery_v160"


class FakePush:
    name = "synthetic_push_v160"

    def __init__(self):
        self.sent = []
        self.cancelled = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return {"ok": True, "provider": self.name, "external_id": "synthetic-receipt"}

    async def cancel(self, **kwargs):
        self.cancelled.append(kwargs)
        return {"ok": True}


def push(when=None):
    return {
        "mode": "push", "timing": "at" if when else "now",
        "not_before": when, "not_after": None,
        "reason_to_interrupt": "È arrivato il momento utile stimato.",
        "reason_to_open": "Leggere la stima e il passo utile.",
        "what_decided_the_mode": "Un risultato ancora valido richiede attenzione.",
        "copy_intent": "Comunica il consiglio utile mantenendo l'incertezza.",
        "confidence": "reasonable", "sensitivity": "ordinary", "requires_recheck": True,
        "copy": {"title": "È il momento di ritirarli",
                 "body": "Secondo la stima aggiornata dovrebbero essere pronti: ritirali.",
                 "public_title": "Un aggiornamento utile", "public_body": "Apri ORA."},
    }


async def setup(monkeypatch, *, action_reason="outcome_ready", kind="important_outcome"):
    from delivery import context, provider, reasoning
    from opportunities.discovery import OpportunityDiscovery

    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setattr(OpportunityDiscovery, "note", AsyncMock(return_value={"outcome": "accepted"}))
    db = AsyncMongoMockClient().situation_delivery_v160
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index("identity", unique=True)
    await db.users.insert_one({"id": OWNER, "settings": {"timezone": "Europe/Rome"}})
    now = datetime.now(timezone.utc)
    state = SituationState(
        id=SID, user_id=OWNER, summary="Panni sintetici stesi in un luogo confermato",
        attention_intent="Stimare il momento utile di ritiro e segnalare rischi prima",
        next_check_summary="Rileggere la fonte", location_label="Tarquinia",
    )
    await SituationRepository(db).insert(state)
    service = AgentService(db)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())
    goal = AutonomousGoal(
        id=goal_id_for(OWNER, SID), owner_id=OWNER, status="active",
        objective="Seguire il momento utile del processo sintetico",
        desired_outcome="Fornire una stima attuale per il ritiro",
        source_kind="situation_followup", source_refs=[f"situation:{SID}"],
        source_situation={"situation_id": SID, "situation_revision": "1",
                          "attention_epoch": "1", "attention_expected": "true"},
    )
    await service.repo.save_goal(goal)
    weather = AgentEvidence(
        owner_id=OWNER, goal_id=goal.id, claim="Condizioni meteorologiche sintetiche del luogo fissato.",
        provenance=ResultProvenance(
            source_class="external_research", capability="weather.read", provider="synthetic_weather",
            source_refs=[f"situation:{SID}:revision:1", "google_place:synthetic-city-v160"],
            observed_at=now.isoformat(), freshness="fresh",
            weather_valid_until=(now + timedelta(minutes=45)).isoformat(),
        ),
    )
    research = AgentEvidence(
        owner_id=OWNER, goal_id=goal.id, claim="Fonte sintetica di un intervallo empirico pertinente.",
        provenance=ResultProvenance(
            source_class="external_research", capability="web.research", provider="synthetic_research",
            source_refs=["research:synthetic_v160"], observed_at=now.isoformat(), freshness="fresh",
            research_sufficient=True, research_valid_until=(now + timedelta(hours=4)).isoformat(),
        ),
    )
    evidence = [weather] if action_reason == "early_risk" else [weather, research]
    for item in evidence:
        await service.evidence.record(item)
    raw = {
        "status": "action_now", "headline": "È il momento utile stimato.",
        "action_summary": ("Ritira adesso per il rischio di pioggia, anche se non sono ancora asciutti."
                           if action_reason == "early_risk" else
                           "Secondo la stima dovrebbero essere pronti: ritirali."),
        "basis": "estimate", "action_reason": action_reason,
        "valid_until": (now + timedelta(hours=1)).isoformat(),
        "evidence_ids": [item.id for item in evidence],
    }
    assessment = await validate_assessment(db, OWNER, goal, raw, evidence=evidence, now=now)
    assert assessment is not None
    goal.situation_outcome = assessment
    await service.repo.save_goal(goal)
    need = await service.needs.raise_need(CommunicationNeed(
        owner_id=OWNER, goal_id=goal.id, kind=kind,
        summary=assessment.action_summary, reason="Giudizio sintetico fondato su fonti sintetiche.",
        source_refs=outcome_refs(assessment.model_dump()), valid_until=assessment.valid_until,
    ))
    channel = FakePush()
    monkeypatch.setattr(provider, "get_provider", lambda: channel)
    monkeypatch.setattr(context, "build", AsyncMock(return_value={"app_state": "background"}))
    monkeypatch.setattr(DeliveryService, "_may_push", AsyncMock(return_value=(True, "")))
    monkeypatch.setattr(DeliveryService, "_arrange_wake", AsyncMock())
    decision = AsyncMock(return_value=push())
    monkeypatch.setattr(reasoning, "decide_delivery", decision)
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active")
    await service.repo.save_plan(plan)
    return db, service, goal, need, plan, channel, decision


async def finish(db, service, goal, plan):
    result = await service._close(OWNER, goal, plan, AgentRun(owner_id=OWNER, goal_id=goal.id),
                                  "completed", "Il momento utile stimato è stato individuato.")
    assert result["state"] == "completed"
    current = await SituationRepository(db).get(OWNER, SID)
    assert current.revision == 2 and current.status == "changed"
    assert current.resolved_at is None, "A result does not prove physical collection."
    return current


async def pending(db, need, decision):
    decision.return_value = push((datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
    result = await NeedService(db).offer_to_delivery(OWNER, need)
    assert result.plan is not None
    await db.delivery_plans.update_one({"id": result.plan.id}, {
        "$set": {"not_before": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
    })
    decision.return_value = push()
    return result.plan.id


@pytest.mark.asyncio
async def test_useful_result_can_reach_fake_transport_after_exact_monitor_settlement(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    result = await service.needs.offer_to_delivery(OWNER, need)
    assert result.plan.status == "delivered"
    assert len(channel.sent) == 1 and "dovrebbero" in channel.sent[0]["body"]
    assert (await DeliveryService(db).deliver_due(OWNER))["sent"] == 0
    assert len(channel.sent) == 1, "Replaying due processing cannot resend a delivered result."
    repeated = await service.needs.offer_to_delivery(OWNER, need)
    assert repeated.blocked_by == "agent_need_source_changed"
    assert len(channel.sent) == 1 and decision.await_count == 1
    state = await SituationRepository(db).get(OWNER, SID)
    assert state.status == "changed" and state.resolved_at is None


@pytest.mark.asyncio
async def test_queued_final_result_survives_settlement_and_ambient_rechecks_its_exact_source(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    delivery_id = await pending(db, need, decision)
    await finish(db, service, goal, plan)
    monkeypatch.setattr(AmbientService, "app_state", AsyncMock(return_value="background"))
    wake = AmbientWake(owner_id=OWNER, reason="delivery_recheck", delivery_plan_id=delivery_id,
                       source_ref=f"agent_need:{need.id}", scheduled_for=datetime.now(timezone.utc).isoformat())
    out = await AmbientService(db).recheck_delivery(wake)
    assert out.handled
    assert len(channel.sent) == 1
    assert (await DeliveryService(db).repo.get_plan(OWNER, delivery_id)).status == "delivered"
    assert decision.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "resolved", "cancelled", "revision", "foreign_source", "assessment_expired",
    "weather_expired", "superseded_evidence", "wrong_outcome_ref", "wrong_situation_ref",
    "new_cycle", "missing_assessment",
])
async def test_old_result_cannot_arrive_after_its_source_or_evidence_changes(monkeypatch, change):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    delivery_id = await pending(db, need, decision)
    await finish(db, service, goal, plan)
    if change in ("resolved", "cancelled"):
        await db.situations.update_one({"id": SID, "user_id": OWNER}, {"$set": {"status": change}})
    elif change == "revision":
        await db.situations.update_one({"id": SID}, {"$inc": {"revision": 1}})
    elif change == "foreign_source":
        await db.situations.update_one({"id": SID}, {"$set": {"user_id": "other-synthetic-owner"}})
    elif change == "assessment_expired":
        await db.agent_goals.update_one({"id": goal.id}, {"$set": {
            "situation_outcome.valid_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }})
    elif change == "weather_expired":
        await db.agent_evidence.update_many({"goal_id": goal.id, "provenance.capability": "weather.read"}, {"$set": {
            "provenance.weather_valid_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }})
    elif change == "superseded_evidence":
        await db.agent_evidence.update_many({"goal_id": goal.id}, {"$set": {"superseded": True}})
    elif change in ("wrong_outcome_ref", "wrong_situation_ref"):
        bad = "situation_outcome:another-result" if change == "wrong_outcome_ref" else "situation:another-source"
        refs = [bad if ref.startswith("situation_outcome:" if change == "wrong_outcome_ref" else "situation:") else ref
                for ref in need.source_refs]
        await db.agent_needs.update_one({"id": need.id}, {"$set": {"source_refs": refs}})
    elif change == "new_cycle":
        await db.agent_goals.update_one({"id": goal.id}, {"$set": {"source_situation.attention_epoch": "new-cycle"}})
    else:
        await db.agent_goals.update_one({"id": goal.id}, {"$set": {"situation_outcome": None}})

    out = await DeliveryService(db).deliver_due(OWNER)
    assert out == {"sent": 0, "cancelled": 1, "held": 0}
    assert channel.sent == []
    assert decision.await_count == 1, "An invalid source does not buy another delivery judgement."
    assert (await DeliveryService(db).repo.get_plan(OWNER, delivery_id)).status == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["needs_information", "needs_authority", "useful_result"])
async def test_completed_watch_does_not_reenable_old_questions_or_nonfinal_results(monkeypatch, kind):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch, kind=kind)
    await finish(db, service, goal, plan)
    result = await NeedService(db).offer_to_delivery(OWNER, need)
    assert result.blocked_by == "agent_need_source_changed"
    assert channel.sent == []
    decision.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["important_outcome", "needs_information"])
async def test_user_collection_fences_delivery_even_when_cancellation_fails(monkeypatch, kind):
    from situations import followup

    db, service, goal, need, plan, channel, decision = await setup(monkeypatch, kind=kind)
    delivery_id = await pending(db, need, decision)
    monkeypatch.setattr(followup, "cancel_dedicated_followup", AsyncMock(return_value=None))
    result = await SituationService(db).apply(
        user_id=OWNER, session_id="synthetic-user-response", reasoning_epoch="synthetic-collected",
        update=SituationUpdate(operation="resolve", situation_id=SID, expected_revision=1,
                               current_state_summary="L'utente ha già ritirato i panni.", source="user_conversation"),
    )
    assert result["status"] == "success"
    assert (await service.repo.get_goal(OWNER, goal.id)).is_open
    assert (await service.needs.get(OWNER, need.id)).is_open
    out = await DeliveryService(db).deliver_due(OWNER)
    assert out["sent"] == 0 and out["cancelled"] == 1
    assert channel.sent == []
    assert (await DeliveryService(db).repo.get_plan(OWNER, delivery_id)).status == "cancelled"


@pytest.mark.asyncio
async def test_user_collection_during_delivery_judgement_is_rechecked_before_send(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    delivery_id = await pending(db, need, decision)

    async def decide_then_collect(*args, **kwargs):
        # Emulate the source committing while the model is deciding; no
        # cancellation cascade is needed for the final send fence to work.
        await db.situations.update_one({"id": SID, "user_id": OWNER}, {
            "$set": {"status": "resolved"}, "$inc": {"revision": 1},
        })
        return push()

    decision.side_effect = decide_then_collect
    out = await DeliveryService(db).deliver_due(OWNER)
    assert out["sent"] == 0 and out["cancelled"] == 1
    assert channel.sent == []
    assert decision.await_count == 2
    assert (await DeliveryService(db).repo.get_plan(OWNER, delivery_id)).status == "cancelled"


@pytest.mark.asyncio
async def test_rain_precaution_is_deliverable_without_claiming_physical_readiness(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch, action_reason="early_risk")
    outcome = await current_outcome(db, OWNER, goal)
    assert outcome["action_reason"] == "early_risk" and outcome["basis"] == "estimate"
    assert "non sono ancora asciutti" in outcome["action_summary"]
    source = await DeliveryService(db)._current_agent_need(OWNER, need.id)
    assert "stima" in source.why_it_matters
    assert "non conferma" in source.why_now
    assert "non sono ancora asciutti" in source.semantic_summary
    # The transport words remain a scripted semantic decision, not a rule
    # converting precipitation probability into physical dryness.
    words = push()
    words["copy"]["body"] = outcome["action_summary"]
    decision.return_value = words
    await finish(db, service, goal, plan)
    result = await service.needs.offer_to_delivery(OWNER, need)
    assert result.plan.status == "delivered"
    assert "non sono ancora asciutti" in channel.sent[0]["body"]


@pytest.mark.asyncio
async def test_delivery_plan_owner_is_checked_before_reloading_a_need(monkeypatch):
    db, _, goal, need, _, channel, decision = await setup(monkeypatch)
    foreign_plan = DeliveryPlan(owner_id="another-synthetic-owner", source_type="agent_need",
                                source_id=need.id, mode="push")
    assert await DeliveryService(db)._current_subject_for_plan(OWNER, foreign_plan) is None
    assert channel.sent == []
    decision.assert_not_awaited()


async def show_result(service, goal):
    assessment = await current_outcome(service.db, OWNER, goal)
    decision = VisibilityDecision(
        goal_id=goal.id, outcome="inform_user", headline=assessment["headline"],
        reasoning=assessment["action_summary"], refs=outcome_refs(assessment),
        fingerprint=f"situation_outcome:{assessment['id']}",
    )
    assert await service.visibility._record(OWNER, decision)
    assert await service.visibility.show(OWNER, goal, decision)
    return assessment


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "expired_assessment", "resolved", "revision", "foreign_situation", "new_assessment",
    "superseded_evidence", "unbound_legacy", "unvalidated_headline", "expired_activity",
])
async def test_home_line_reloads_a_previously_shown_result_before_presenting_it(monkeypatch, change):
    db, service, goal, _, _, channel, delivery_decision = await setup(monkeypatch)
    assessment = await show_result(service, goal)
    line = await DeliveryService(db).ambient_line(OWNER)
    assert line and line["text"] == assessment["headline"]
    if change == "expired_assessment":
        await db.agent_goals.update_one({"id": goal.id}, {"$set": {
            "situation_outcome.valid_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }})
    elif change == "resolved":
        from situations import followup

        monkeypatch.setattr(followup, "cancel_dedicated_followup", AsyncMock(return_value=None))
        result = await SituationService(db).apply(
            user_id=OWNER, session_id="synthetic-home-response", reasoning_epoch="synthetic-collected",
            update=SituationUpdate(operation="resolve", situation_id=SID, expected_revision=1,
                                   current_state_summary="L'utente ha già ritirato i panni.",
                                   source="user_conversation"),
        )
        assert result["status"] == "success"
        assert (await service.repo.get_goal(OWNER, goal.id)).is_open
    elif change == "revision":
        await db.situations.update_one({"id": SID}, {"$inc": {"revision": 1}})
    elif change == "foreign_situation":
        await db.situations.update_one({"id": SID}, {"$set": {"user_id": "another-synthetic-owner"}})
    elif change == "new_assessment":
        await db.agent_goals.update_one({"id": goal.id}, {"$set": {
            "situation_outcome.id": "soa_new_synthetic_assessment",
        }})
    elif change == "superseded_evidence":
        await db.agent_evidence.update_many({"goal_id": goal.id}, {"$set": {"superseded": True}})
    elif change == "unbound_legacy":
        await db.ambient_activity.update_many({"owner_id": OWNER}, {"$set": {"source_refs": [goal.id]}})
    elif change == "unvalidated_headline":
        await db.ambient_activity.update_many({"owner_id": OWNER}, {"$set": {
            "summary": "Sono sicuramente asciutti: nessun dubbio.",
        }})
    else:
        await db.ambient_activity.update_many({"owner_id": OWNER}, {"$set": {
            "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
        }})

    assert await DeliveryService(db).ambient_line(OWNER) is None
    assert await db.ambient_activity.count_documents({"owner_id": OWNER}) == 1
    assert await db.agent_updates.count_documents({"owner_id": OWNER}) == 1
    assert await db.delivery_plans.count_documents({"owner_id": OWNER}) == 0
    assert channel.sent == []
    delivery_decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_home_result_keeps_its_binding_when_the_activity_truncates_evidence_refs(monkeypatch):
    db, service, goal, _, _, channel, delivery_decision = await setup(monkeypatch)
    rows = await db.agent_evidence.find(
        {"owner_id": OWNER, "goal_id": goal.id}, {"_id": 0, "expires_at": 0},
    ).to_list(6)
    evidence = [AgentEvidence.model_validate(row) for row in rows]
    for i in range(4):
        item = evidence[-1].model_copy(update={"id": f"evd_additional_home_v160_{i}"})
        await service.evidence.record(item)
        evidence.append(item)
    raw = goal.situation_outcome.model_dump()
    raw["evidence_ids"] = [item.id for item in evidence]
    goal.situation_outcome = await validate_assessment(db, OWNER, goal, raw, evidence=evidence)
    assert goal.situation_outcome is not None
    await service.repo.save_goal(goal)
    assessment = await show_result(service, goal)
    activity = await db.ambient_activity.find_one({"owner_id": OWNER})
    assert not set(assessment["evidence_ids"]).issubset(activity["source_refs"])
    assert (await DeliveryService(db).ambient_line(OWNER))["text"] == assessment["headline"]
    assert channel.sent == []
    delivery_decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_exact_completion_note_is_current_until_the_user_resolves_its_situation(monkeypatch):
    db, service, goal, _, plan, channel, delivery_decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    await AgentService._note_ambient(service, OWNER, "agent_goal_completed", goal)
    assessment = await current_outcome(db, OWNER, goal, allow_settled=True)
    assert (await DeliveryService(db).ambient_line(OWNER))["text"] == assessment["headline"]
    await db.situations.update_one({"id": SID}, {"$set": {"status": "resolved"}})
    assert await DeliveryService(db).ambient_line(OWNER) is None
    assert channel.sent == []
    delivery_decision.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["answered", "completed", "revision", "expired_goal"])
async def test_home_question_exists_only_while_its_owned_attention_is_waiting_for_it(monkeypatch, change):
    db, service, goal, _, _, channel, delivery_decision = await setup(monkeypatch)
    goal.situation_outcome = None
    goal.requires_user_input = True
    await service.repo.save_goal(goal)
    decision = VisibilityDecision(
        goal_id=goal.id, outcome="inform_user", headline="A che ora hai iniziato?",
        refs=[f"situation_revision:{SID}:1", "journal:synthetic-question"],
        fingerprint="synthetic-start-time-question-v160",
    )
    assert await service.visibility._record(OWNER, decision)
    assert await service.visibility.show(OWNER, goal, decision)
    assert (await DeliveryService(db).ambient_line(OWNER))["text"] == decision.headline
    if change == "answered":
        await db.agent_goals.update_one({"id": goal.id}, {"$set": {"requires_user_input": False}})
    elif change == "completed":
        await db.agent_goals.update_one({"id": goal.id}, {"$set": {"status": "completed"}})
    elif change == "revision":
        await db.situations.update_one({"id": SID}, {"$inc": {"revision": 1}})
    else:
        await db.agent_goals.update_one({"id": goal.id}, {"$set": {
            "valid_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }})
    assert await DeliveryService(db).ambient_line(OWNER) is None
    assert channel.sent == []
    delivery_decision.assert_not_awaited()
