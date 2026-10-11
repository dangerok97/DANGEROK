"""A Situation result survives Home handoff failures without replaying stale advice.

All records, evidence and model replies are synthetic; no account, provider,
notification transport or external model is used.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AgentBudget, AgentEvidence, AgentRun, ResultProvenance, VisibilityDecision
from agent.service import AgentService
from delivery.service import DeliveryService
from situations.admission import _review_goal
from situations.followup import settle_completed_followup
from situations.models import SituationState
from situations.outcomes import current_outcome, outcome_refs
from situations.service import SituationService


OWNER = "visibility-v160-synthetic"


async def scenario(monkeypatch, *, status="estimated", assessed=True):
    db = AsyncMongoMockClient().situation_visibility_v160
    service = AgentService(db)
    await service.visibility.ensure_indexes()
    now = datetime.now(timezone.utc)
    state = SituationState(
        id="sit_visibility_v160", user_id=OWNER,
        summary="Attività sintetica in corso", attention_intent="Rivalutare il momento utile",
        desired_outcome="Sapere quando intervenire", started_at=(now - timedelta(minutes=30)).isoformat(),
    )
    await db.situations.insert_one(state.model_dump())
    goal = _review_goal(OWNER, state, "gol_visibility_v160")
    await service.repo.create_goal(goal)
    evidence = AgentEvidence(
        id="evd_visibility_v160", owner_id=OWNER, goal_id=goal.id,
        claim="Calcolo sintetico con una base verificabile per il momento utile.",
        provenance=ResultProvenance(
            source_class="deterministic_computation", provider="synthetic-fixture",
            capability="calculation", source_refs=["fixture:baseline"], freshness="fresh",
        ),
    )
    await service.evidence.record(evidence)
    run = AgentRun(owner_id=OWNER, goal_id=goal.id, at=(now - timedelta(seconds=1)).isoformat())
    raw = {
        "status": status, "headline": "Finestra utile stimata con fonti verificate.",
        "action_summary": "Attendi il prossimo riesame della valutazione.", "basis": "estimate",
        "action_reason": None, "window_start": (now + timedelta(hours=2)).isoformat(),
        "window_end": (now + timedelta(hours=3)).isoformat(),
        "valid_until": (now + timedelta(hours=1)).isoformat(), "evidence_ids": [evidence.id],
    }
    if status == "action_now":
        raw.update(headline="Puoi intervenire adesso, in base alla stima verificata.",
                   action_summary="Intervieni e controlla il risultato.", action_reason="outcome_ready",
                   window_start=None, window_end=None)
    if assessed:
        assert await service._record_situation_outcome(OWNER, goal, raw, run)
    answer = AsyncMock(return_value={
        "outcome": "inform_user", "headline": "Riepilogo meteo NON VALIDATO del modello",
        "reasoning": "Motivo NON VALIDATO", "about": "momento utile della stessa attività",
    })
    monkeypatch.setattr("agent.reasoning.decide_visibility", answer)
    monkeypatch.setattr(SituationService, "_note_opportunity_change", AsyncMock())
    return db, service, state, goal, run, evidence, raw, answer


async def consider(service, goal, run):
    return await service.visibility.consider(
        OWNER, goal, what_happened=await service._run_facts(OWNER, goal, run),
    )


@pytest.mark.asyncio
async def test_rejected_situation_update_never_enters_the_replayable_outbox(monkeypatch):
    db, service, _, goal, run, _, _, _ = await scenario(monkeypatch, assessed=False)
    decision = await service._consider_visibility(OWNER, goal.id, run, AgentBudget())
    assert decision is None or not decision.is_visible
    assert await db.agent_updates.count_documents({}) == 0
    assert await service.visibility.recover_pending_home() == {
        "checked": 0, "shown": 0, "deferred": 0, "stale": 0,
    }
    assert await db.ambient_activity.count_documents({}) == 0


@pytest.mark.asyncio
async def test_home_handoff_failure_recovers_the_exact_validated_result(monkeypatch):
    db, service, _, goal, run, _, _, answer = await scenario(monkeypatch)
    assessment = await current_outcome(db, OWNER, goal)
    decision = await consider(service, goal, run)
    row = await db.agent_updates.find_one({"owner_id": OWNER})
    assert row["headline"] == assessment["headline"]
    assert row["reasoning"] == assessment["action_summary"]
    assert row["refs"] == outcome_refs(assessment)
    assert "NON VALIDATO" not in str(row)

    original = DeliveryService.note_activity
    writes = 0

    async def fail_once(self, *args, **kwargs):
        nonlocal writes
        writes += 1
        if writes == 1:
            raise ConnectionError("synthetic Home write failure")
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(DeliveryService, "note_activity", fail_once)
    assert not await service.visibility.show(OWNER, goal, decision)
    await db.agent_updates.update_one({"owner_id": OWNER}, {"$set": {
        "home_due_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    }})
    recovered = await service.visibility.recover_pending_home()
    assert recovered == {"checked": 1, "shown": 1, "deferred": 0, "stale": 0}
    activity = await db.ambient_activity.find_one({"owner_id": OWNER})
    assert activity["summary"] == assessment["headline"]
    assert f"situation_outcome:{assessment['id']}" in activity["source_refs"]
    assert answer.await_count == 1
    assert await db.agent_needs.count_documents({}) == 0
    assert await db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "revision", "resolved", "cancelled_goal", "superseded_evidence", "expired_assessment",
    "foreign_situation", "new_assessment",
])
async def test_pending_home_result_is_not_replayed_after_its_binding_changes(monkeypatch, change):
    db, service, state, goal, run, evidence, raw, _ = await scenario(monkeypatch)
    assert (await consider(service, goal, run)).is_visible
    if change == "revision":
        await db.situations.update_one({"id": state.id}, {"$inc": {"revision": 1}})
    elif change == "resolved":
        await db.situations.update_one({"id": state.id}, {"$set": {"status": "resolved"}})
    elif change == "cancelled_goal":
        await db.agent_goals.update_one({"id": goal.id}, {"$set": {"status": "cancelled"}})
    elif change == "superseded_evidence":
        await db.agent_evidence.update_one({"id": evidence.id}, {"$set": {"superseded": True}})
    elif change == "expired_assessment":
        await db.agent_goals.update_one({"id": goal.id}, {"$set": {
            "situation_outcome.valid_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }})
    elif change == "foreign_situation":
        await db.situations.update_one({"id": state.id}, {"$set": {"user_id": "other-synthetic-owner"}})
    else:
        assert await service._record_situation_outcome(
            OWNER, goal, {**raw, "headline": "Una nuova valutazione diversa."}, run,
        )
    recovered = await service.visibility.recover_pending_home()
    assert recovered == {"checked": 1, "shown": 0, "deferred": 0, "stale": 1}
    assert await db.ambient_activity.count_documents({}) == 0
    assert (await db.agent_updates.find_one({"owner_id": OWNER}))["home_pending"] is False


@pytest.mark.asyncio
async def test_source_change_during_visibility_judgement_cannot_borrow_a_new_result(monkeypatch):
    db, service, _, goal, run, _, raw, _ = await scenario(monkeypatch)
    facts = await service._run_facts(OWNER, goal, run)

    async def revise_during_judgement(*args, **kwargs):
        assert await service._record_situation_outcome(
            OWNER, goal, {**raw, "headline": "Valutazione successiva alla decisione."}, run,
        )
        return {"outcome": "inform_user", "headline": "Vecchia decisione", "about": "stesso tema"}

    monkeypatch.setattr("agent.reasoning.decide_visibility", revise_during_judgement)
    decision = await service.visibility.consider(OWNER, goal, what_happened=facts)
    assert not decision.is_visible
    assert await db.agent_updates.count_documents({}) == 0


@pytest.mark.asyncio
async def test_same_topic_deduplicates_estimates_but_preserves_changed_window_and_final_action(monkeypatch):
    db, service, _, goal, run, _, raw, _ = await scenario(monkeypatch)
    first = await consider(service, goal, run)
    assert first.is_visible
    assert await service._record_situation_outcome(OWNER, goal, raw, run)
    assert not (await consider(service, goal, run)).is_visible

    later = (datetime.fromisoformat(raw["window_end"]) + timedelta(hours=1)).isoformat()
    assert await service._record_situation_outcome(OWNER, goal, {**raw, "window_end": later}, run)
    moved = await consider(service, goal, run)
    assert moved.is_visible and moved.fingerprint != first.fingerprint
    action = {**raw, "status": "action_now", "headline": "Ora puoi intervenire.",
              "action_reason": "outcome_ready", "window_start": None, "window_end": None}
    assert await service._record_situation_outcome(OWNER, goal, action, run)
    final = await consider(service, goal, run)
    assert final.is_visible and final.fingerprint not in (first.fingerprint, moved.fingerprint)
    assert await db.agent_updates.count_documents({}) == 3


@pytest.mark.asyncio
async def test_completed_watch_keeps_its_exact_settled_final_result_replayable(monkeypatch):
    db, service, _, goal, run, _, _, _ = await scenario(monkeypatch, status="action_now")
    decision = await consider(service, goal, run)
    goal.status = "completed"
    await service.repo.save_goal(goal)
    assert await settle_completed_followup(db, OWNER, goal)
    assessment = await current_outcome(db, OWNER, goal, allow_settled=True)
    assert assessment and assessment["situation_revision"] == assessment["assessment_revision"] + 1
    assert await service.visibility.recover_pending_home() == {
        "checked": 1, "shown": 1, "deferred": 0, "stale": 0,
    }
    assert (await db.ambient_activity.find_one({"owner_id": OWNER}))["summary"] == decision.headline


@pytest.mark.asyncio
async def test_pending_question_is_bound_to_current_attention_and_stops_when_answered(monkeypatch):
    db, service, state, goal, run, _, _, _ = await scenario(monkeypatch, assessed=False)
    goal.requires_user_input = True
    goal.status = "waiting"
    await service.repo.save_goal(goal)
    decision = await consider(service, goal, run)
    assert decision.is_visible
    assert f"situation_revision:{state.id}:1" in decision.refs
    await db.agent_goals.update_one({"id": goal.id}, {"$set": {"requires_user_input": False}})
    assert (await service.visibility.recover_pending_home())["stale"] == 1
    assert await db.ambient_activity.count_documents({}) == 0


@pytest.mark.asyncio
async def test_old_unbound_situation_outbox_records_are_not_replayed(monkeypatch):
    db, service, _, goal, _, _, _, _ = await scenario(monkeypatch, assessed=False)
    old = VisibilityDecision(
        goal_id=goal.id, outcome="inform_user", headline="Vecchio esito non validato",
        refs=["journal:synthetic-old"], fingerprint="synthetic-pre-v160-outbox",
    )
    assert await service.visibility._record(OWNER, old)
    assert (await service.visibility.recover_pending_home())["stale"] == 1
    assert await db.ambient_activity.count_documents({}) == 0
