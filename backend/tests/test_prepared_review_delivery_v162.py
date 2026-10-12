"""A negative prepared-result review survives every communication boundary.

The reader/preparer, stores, visibility outbox and Delivery are production
code over owned synthetic records. Model replies and the channel are fakes;
one case uses the installed Gemini SDK over fake HTTP. No external effects.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent import reasoning
from agent.execution import StepExecutor
from agent.models import ActionStep, AgentBudget, AgentRun, GoalVerification, VisibilityDecision
from agent.needs import NeedService
from agent.prepared_review import capture_prepared_result, persist_prepared_review, prepared_result_ref
from agent.service import AgentService
from agent.visibility import VisibilityService
from delivery.models import DeliverySubject
from delivery.service import DeliveryService
from scripts import autonomy_completion_eval_v162 as gate
from test_agent_completed_result_delivery_v162 import FakePush, push
from test_agent_preparation_dependency_v162 import OWNER, MEMORY, RESULT, fake_gemini
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401
from test_preparation_recovery_v162 import seed_recovery
from test_verification_recovery_v162 import prepared_with_missed_defect


def visible(outcome="inform_user"):
    return {"outcome": outcome, "headline": "Il confronto è pronto da leggere.",
            "reasoning": "Il risultato può essere utile.", "about": "confronto annotato"}


def past():
    return (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()


async def setup(monkeypatch, *, prepared=True, mock_visibility=True):
    db, goal, plan, source, text = (
        await prepared_with_missed_defect(RESULT) if prepared else await seed_recovery()
    )
    service, delivery = AgentService(db), DeliveryService(db)
    await service.visibility.ensure_indexes()
    await service.needs.ensure_indexes()
    await delivery.repo.ensure_indexes()
    from delivery import context, provider, reasoning as delivery_reasoning

    channel, decide = FakePush(), AsyncMock(return_value=push())
    monkeypatch.setattr(provider, "get_provider", lambda: channel)
    monkeypatch.setattr(context, "build", AsyncMock(return_value={"app_state": "background"}))
    monkeypatch.setattr(delivery_reasoning, "decide_delivery", decide)
    monkeypatch.setattr(DeliveryService, "_may_push", AsyncMock(return_value=(True, "")))
    monkeypatch.setattr(DeliveryService, "_arrange_wake", AsyncMock())
    visibility = AsyncMock(return_value=visible())
    if mock_visibility:
        monkeypatch.setattr(reasoning, "decide_visibility", visibility)
    return SimpleNamespace(db=db, goal=goal, plan=plan, source=source, text=text,
                           service=service, delivery=delivery, channel=channel,
                           decide=decide, visibility=visibility)


async def review(h, outcome="partially_achieved"):
    current = await AgentService(h.db).repo.get_goal(OWNER, h.goal.id)
    verification = GoalVerification(goal_id=current.id, outcome=outcome,
        what_is_missing="Una premessa del confronto deve essere verificata.",
        reasoning="Una conclusione non è sostenuta dalla fonte letta.")
    assert await persist_prepared_review(
        h.db, OWNER, current, capture_prepared_result(current), verification,
    )
    return current


async def decide(h, *, goal=None):
    goal = goal or await AgentService(h.db).repo.get_goal(OWNER, h.goal.id)
    facts = await h.service._run_facts(OWNER, goal, AgentRun(owner_id=OWNER, goal_id=goal.id))
    decision = await h.service.visibility.consider(OWNER, goal, what_happened=facts)
    return goal, facts, decision


async def queue(h):
    goal, facts, decision = await decide(h)
    assert decision.is_visible
    h.decide.return_value = push((datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    need = await h.service._raise_need(OWNER, goal, decision, facts)
    assert need is not None
    plan, = await h.delivery.repo.plans_for(OWNER, need.id, source_type="agent_need")
    assert plan.status == "pending" and not h.channel.sent
    return goal, facts, decision, need, plan


async def prepare_again(h, *, text=RESULT):
    current = await AgentService(h.db).repo.get_goal(OWNER, h.goal.id)
    before = prepared_result_ref(current)
    replies = AsyncMock(side_effect=[
        {"content": text, "evidence_ids": [h.source.id]},
        {"verified": True, "content": text, "evidence_ids": [h.source.id]},
    ])
    step = ActionStep(step_type="prepare", capability_needed="document.create",
        input_refs=[MEMORY], intent="Preparare il confronto dalle prove correnti.")
    with patch.object(reasoning, "_ask_model", replies):
        result = await StepExecutor(h.db).run(OWNER, current, step, may_touch_the_world=False)
    assert result.status == "succeeded" and replies.await_count == 2
    assert prepared_result_ref(current) != before
    return current


def goal_read_outage(monkeypatch, db):
    collection = type(db.agent_goals)
    original = collection.find_one

    async def read(self, *args, **kwargs):
        if self.name == "agent_goals":
            raise ConnectionError("synthetic goal archive unavailable")
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(collection, "find_one", read)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["quiet_update", "inform_user", "requires_attention", "ask_user"])
@pytest.mark.parametrize("negative", ["partially_achieved", "uncertain"])
async def test_negative_review_quietens_non_questions_without_interpreting_headline(monkeypatch, outcome, negative):
    h = await setup(monkeypatch)
    await review(h, negative)
    h.visibility.return_value = visible(outcome)
    goal, facts, decision = await decide(h)
    assert facts["prepared_review"]["outcome"] == ("partial" if negative == "partially_achieved" else "uncertain")
    assert decision.outcome == "silent" and decision.decided_by == "code"
    assert not await h.service.visibility.show(OWNER, goal, decision)
    assert await h.service._raise_need(OWNER, goal, decision, facts) is None
    assert h.visibility.await_count == 1
    assert await h.db.agent_updates.count_documents({}) == 0
    assert await h.db.agent_needs.count_documents({}) == 0
    assert await h.db.ambient_activity.count_documents({"visibility": "ambient"}) == 0
    assert await h.db.delivery_plans.count_documents({}) == 0
    assert not h.channel.sent and h.decide.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["information", "authority"])
async def test_real_question_and_approval_draft_remain_available(monkeypatch, kind):
    h = await setup(monkeypatch)
    await review(h)
    await h.db.agent_goals.update_one({"id": h.goal.id, "owner_id": OWNER}, {"$set": {
        "status": "waiting", "requires_user_input": kind == "information",
        "requires_user_authority": kind == "authority",
    }})
    # Being legitimately blocked does not authorise an unrelated ready-result
    # announcement. The model must actually choose to ask for the person.
    _, _, unasked = await decide(h)
    assert unasked.outcome == "silent"
    h.visibility.return_value = {**visible("ask_user"), "headline": "Mi serve una tua indicazione per proseguire."}
    goal, facts, decision = await decide(h)
    assert decision.is_visible and goal.prepared_text == RESULT
    assert await h.service.visibility.show(OWNER, goal, decision)
    need = await h.service._raise_need(OWNER, goal, decision, facts)
    assert need.requires_response and need.response_kind == kind
    assert need.prepared_result_ref == prepared_result_ref(goal)
    assert need.kind == f"needs_{kind}"
    assert len(h.channel.sent) == 1
    assert await h.delivery.ambient_line(OWNER)
    import deps
    from agent.router import need as read_need
    monkeypatch.setattr(deps, "db", h.db)
    opened = await read_need(need.id, user={"user_id": OWNER})
    assert opened["says"] == need.summary and opened["needs_you"] is True


@pytest.mark.asyncio
async def test_question_cannot_borrow_a_no_longer_needed_user_blocker(monkeypatch):
    h = await setup(monkeypatch)
    await review(h)
    await h.db.agent_goals.update_one({"id": h.goal.id, "owner_id": OWNER},
        {"$set": {"status": "waiting", "requires_user_authority": True}})
    h.visibility.return_value = visible("ask_user")
    goal, facts, decision, need, plan = await queue(h)
    await h.db.agent_goals.update_one({"id": h.goal.id, "owner_id": OWNER},
        {"$set": {"requires_user_authority": False, "requires_user_input": True}})
    assert await h.service._raise_need(OWNER, goal, decision, facts) is None
    await h.delivery._send(OWNER, plan)
    assert not h.channel.sent
    assert (await h.delivery.repo.get_plan(OWNER, plan.id)).status == "cancelled"


@pytest.mark.asyncio
async def test_late_negative_review_stops_materialization_and_outbox_replay(monkeypatch):
    h = await setup(monkeypatch)
    goal, facts, decision = await decide(h)
    assert decision.is_visible
    await review(h)
    assert not await h.service.visibility.show(OWNER, goal, decision)
    assert await h.service._raise_need(OWNER, goal, decision, facts) is None
    row = await h.db.agent_updates.find_one({"owner_id": OWNER, "fingerprint": decision.fingerprint})
    assert row["home_pending"] is False and row["home_skipped"] == "preparation_no_longer_current"
    assert (await h.service.visibility.recover_pending_home())["checked"] == 0
    assert await h.db.ambient_activity.count_documents({}) == 0
    assert await h.db.agent_needs.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["owner", "decision_goal"])
async def test_need_materialization_checks_the_same_owner_and_decided_goal(monkeypatch, mismatch):
    h = await setup(monkeypatch)
    goal, facts, decision = await decide(h)
    owner = "other-synthetic-owner" if mismatch == "owner" else OWNER
    if mismatch == "decision_goal":
        decision.goal_id = "gol_other_synthetic_preparation"
    assert await h.service._raise_need(owner, goal, decision, facts) is None
    assert await h.db.agent_needs.count_documents({}) == 0 and not h.channel.sent


@pytest.mark.asyncio
async def test_pending_outbox_reloads_negative_review_after_process_state_is_lost(monkeypatch):
    h = await setup(monkeypatch)
    await decide(h)
    await review(h)
    result = await VisibilityService(h.db).recover_pending_home()
    assert result == {"checked": 1, "shown": 0, "deferred": 0, "stale": 1}
    assert await h.db.ambient_activity.count_documents({}) == 0


@pytest.mark.asyncio
async def test_home_read_drops_negative_review_and_old_line_after_identical_new_preparation(monkeypatch):
    h = await setup(monkeypatch)
    goal, _, decision = await decide(h)
    assert await h.service.visibility.show(OWNER, goal, decision)
    assert await h.delivery.ambient_line(OWNER)
    await review(h)
    assert await DeliveryService(h.db).ambient_line(OWNER) is None
    assert await h.service.visibility.recent(OWNER) == []
    newer = await prepare_again(h)
    assert newer.prepared_text == goal.prepared_text
    assert await DeliveryService(h.db).ambient_line(OWNER) is None
    assert not await VisibilityService(h.db).show(OWNER, newer, decision)
    _, _, fresh = await decide(h, goal=newer)
    assert fresh.is_visible and fresh.fingerprint != decision.fingerprint
    assert await VisibilityService(h.db).show(OWNER, newer, fresh)
    assert await DeliveryService(h.db).ambient_line(OWNER)


@pytest.mark.asyncio
async def test_negative_review_during_activity_insert_is_not_acknowledged_or_read(monkeypatch):
    h = await setup(monkeypatch)
    goal, _, decision = await decide(h)
    original = DeliveryService.note_activity

    async def insert_then_review(self, *args, **kwargs):
        activity = await original(self, *args, **kwargs)
        await review(h)
        return activity

    monkeypatch.setattr(DeliveryService, "note_activity", insert_then_review)
    assert not await h.service.visibility.show(OWNER, goal, decision)
    assert await h.db.ambient_activity.count_documents({}) == 1  # History, not a current Home claim.
    assert await h.delivery.ambient_line(OWNER) is None
    row = await h.db.agent_updates.find_one({"owner_id": OWNER, "fingerprint": decision.fingerprint})
    assert "home_delivered_at" not in row and row["home_skipped"] == "preparation_no_longer_current"


@pytest.mark.asyncio
async def test_slow_visibility_cannot_bind_to_a_new_preparation(monkeypatch):
    h = await setup(monkeypatch)

    async def late_answer(*args, **kwargs):
        await prepare_again(h)
        return visible()

    h.visibility.side_effect = late_answer
    _, _, decision = await decide(h, goal=h.goal)
    assert decision.outcome == "silent" and decision.decided_by == "code"
    assert await h.db.agent_updates.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["evaluate", "due", "send"])
async def test_queued_need_rereads_negative_review_at_every_delivery_boundary(monkeypatch, boundary):
    h = await setup(monkeypatch)
    _, _, _, need, plan = await queue(h)
    h.decide.reset_mock()
    await review(h)
    if boundary == "evaluate":
        result = await h.delivery.evaluate_subject(OWNER, DeliverySubject.model_validate(need.as_subject()))
        assert result.blocked_by == "agent_need_source_changed"
    elif boundary == "due":
        await h.db.delivery_plans.update_one({"id": plan.id}, {"$set": {"not_before": past()}})
        assert await h.delivery.deliver_due(OWNER) == {"sent": 0, "cancelled": 1, "held": 0}
    else:
        await h.delivery._send(OWNER, plan)
    assert not h.channel.sent and h.decide.await_count == 0
    assert (await h.delivery.repo.get_plan(OWNER, plan.id)).status == "cancelled"


@pytest.mark.asyncio
async def test_review_arriving_after_channel_judgement_is_checked_before_provider(monkeypatch):
    h = await setup(monkeypatch)
    goal, facts, decision = await decide(h)

    async def review_after_permission(*args, **kwargs):
        await review(h)
        return True, ""

    monkeypatch.setattr(DeliveryService, "_may_push", review_after_permission)
    need = await h.service._raise_need(OWNER, goal, decision, facts)
    assert need is not None and h.decide.await_count == 1
    plan, = await h.delivery.repo.plans_for(OWNER, need.id, source_type="agent_need")
    assert plan.status == "cancelled" and not h.channel.sent


@pytest.mark.asyncio
async def test_send_rereads_review_after_awaiting_other_source_checks(monkeypatch):
    h = await setup(monkeypatch)
    _, _, _, _, plan = await queue(h)
    from delivery import service as delivery_module
    original = delivery_module.memory_result_current

    async def source_then_review(*args, **kwargs):
        current = await original(*args, **kwargs)
        await review(h)
        return current

    monkeypatch.setattr(delivery_module, "memory_result_current", source_then_review)
    await h.delivery._send(OWNER, plan)
    assert not h.channel.sent
    assert (await h.delivery.repo.get_plan(OWNER, plan.id)).status == "cancelled"


@pytest.mark.asyncio
async def test_same_text_new_identity_cannot_resurrect_old_need_or_update_its_binding(monkeypatch):
    h = await setup(monkeypatch)
    _, _, _, old, old_plan = await queue(h)
    old_ref = old.prepared_result_ref
    await review(h)
    newer = await prepare_again(h)
    assert newer.prepared_text == h.goal.prepared_text and prepared_result_ref(newer) != old_ref
    _, facts, decision = await decide(h, goal=newer)
    with patch.object(NeedService, "offer_to_delivery", AsyncMock()):
        fresh = await h.service._raise_need(OWNER, newer, decision, facts)
    assert fresh.id != old.id and fresh.fingerprint != old.fingerprint
    assert fresh.prepared_result_ref == prepared_result_ref(newer)
    assert (await h.service.needs.get(OWNER, old.id)).prepared_result_ref == old_ref
    await DeliveryService(h.db)._send(OWNER, old_plan)
    assert not h.channel.sent
    assert (await h.delivery.repo.get_plan(OWNER, old_plan.id)).status == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_need_created_without_an_artifact_cannot_inherit_the_first_preparation(monkeypatch, legacy):
    h = await setup(monkeypatch, prepared=False)
    _, _, _, need, plan = await queue(h)
    assert need.prepared_result_ref == ""
    if legacy:
        await h.db.agent_needs.update_one({"owner_id": OWNER, "id": need.id},
            {"$unset": {"prepared_result_ref": ""}})
    newer = await prepare_again(h)
    assert newer.prepared_result_id
    await h.delivery._send(OWNER, plan)
    assert not h.channel.sent
    assert (await h.delivery.repo.get_plan(OWNER, plan.id)).status == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize("replace", [False, True])
async def test_old_need_link_rechecks_review_and_exact_artifact(monkeypatch, replace):
    from fastapi import HTTPException
    import deps
    from agent.router import need as read_need

    h = await setup(monkeypatch)
    _, _, _, need, _ = await queue(h)
    monkeypatch.setattr(deps, "db", h.db)
    assert (await read_need(need.id, user={"user_id": OWNER}))["says"] == need.summary
    await review(h)
    if replace:
        await prepare_again(h)
    with pytest.raises(HTTPException) as stopped:
        await read_need(need.id, user={"user_id": OWNER})
    assert stopped.value.status_code == 410
    assert (await h.service.needs.get(OWNER, need.id)).is_open
    assert not h.channel.sent


@pytest.mark.asyncio
async def test_need_link_archive_outage_is_retryable_and_does_not_revoke_the_need(monkeypatch):
    from fastapi import HTTPException
    import deps
    from agent.router import need as read_need

    h = await setup(monkeypatch)
    _, _, _, need, plan = await queue(h)
    monkeypatch.setattr(deps, "db", h.db)
    with monkeypatch.context() as outage:
        goal_read_outage(outage, h.db)
        with pytest.raises(HTTPException) as unavailable:
            await read_need(need.id, user={"user_id": OWNER})
        assert unavailable.value.status_code == 503
        assert unavailable.value.detail == "source_check_unavailable"
    assert (await h.service.needs.get(OWNER, need.id)).is_open
    assert (await h.delivery.repo.get_plan(OWNER, plan.id)).status == "pending"
    assert (await read_need(need.id, user={"user_id": OWNER}))["says"] == need.summary
    assert not h.channel.sent


async def calendar_question(monkeypatch):
    from home.manual_event import create_manual_event
    from opportunities.models import EvidenceRef, Opportunity
    from opportunities.repository import OpportunityRepository

    h = await setup(monkeypatch, prepared=False)
    h.decide.return_value = {"mode": "in_app"}
    start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(
        hour=9, minute=0, second=0, microsecond=0,
    )
    events = []
    for index, minutes in enumerate((0, 30)):
        at = start + timedelta(minutes=minutes)
        events.append(await create_manual_event(h.db, OWNER, title=f"Impegno sintetico {index + 1}",
            start=at.isoformat(), end=(at + timedelta(hours=1)).isoformat(), tz_name="UTC",
            request_id=f"prepared-review-calendar-{index}", location="", description=""))
    refs = [f"calendar:{event['id']}" for event in events]
    opportunity = Opportunity(owner_id=OWNER, identity_key="synthetic:bound-calendar-question",
        status="active", semantic_summary="Due impegni sintetici risultano sovrapposti.",
        why_it_matters="Serve una scelta prima di modificare uno dei due impegni sintetici.",
        initiative="prepare", evidence=[EvidenceRef(kind="calendar_event", ref=ref) for ref in refs])
    await OpportunityRepository(h.db).save(opportunity)
    created = await h.service.consider(OWNER, situation={}, opportunity_id=opportunity.id,
        source_kind="opportunity", source_refs=refs)
    goal = await h.service.repo.goal_for_opportunity(OWNER, opportunity.id)
    assert created["outcome"] == "create_goal" and goal.prepared_result_id and goal.prepared_text
    need, = await h.service.needs.open_for_goal(OWNER, goal.id)
    return h, goal, need, refs


@pytest.mark.asyncio
async def test_prepared_calendar_conflict_direct_question_captures_exact_artifact(monkeypatch):
    h, goal, need, _ = await calendar_question(monkeypatch)
    assert need.prepared_result_ref == prepared_result_ref(goal)
    assert need.kind == "needs_information" and need.requires_response
    assert await h.delivery._current_agent_need(OWNER, need.id) is not None
    assert h.decide.await_count == 1 and not h.channel.sent
    assert await h.db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_calendar_answer_next_question_keeps_current_artifact_binding(monkeypatch):
    h, goal, first, refs = await calendar_question(monkeypatch)
    monkeypatch.setattr(reasoning, "interpret_calendar_conflict_choice", AsyncMock(return_value={
        "target_ref": refs[1], "requested_time": "", "requested_date": "",
    }))
    result = await h.service.answer(OWNER, goal.id, reply="Voglio spostare il secondo impegno.")
    assert result["state"] == "waiting_for_person"
    latest = await h.service.repo.get_goal(OWNER, goal.id)
    second, = await h.service.needs.open_for_goal(OWNER, goal.id)
    assert second.id != first.id and second.fingerprint != first.fingerprint
    assert second.prepared_result_ref == prepared_result_ref(latest)
    assert second.prepared_result_ref == first.prepared_result_ref
    assert latest.prepared_result_id == goal.prepared_result_id and latest.prepared_text == goal.prepared_text
    assert await h.delivery._current_agent_need(OWNER, second.id) is not None
    assert (await h.service.needs.get(OWNER, first.id)).status == "satisfied"
    assert not h.channel.sent and await h.db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_legacy_unbound_result_does_not_invent_verification_and_obeys_current_negative(monkeypatch):
    h = await setup(monkeypatch)
    await h.db.agent_goals.update_one({"owner_id": OWNER, "id": h.goal.id},
        {"$unset": {"prepared_result_id": "", "prepared_review": ""}})
    goal, _, decision = await decide(h)
    assert goal.prepared_result_id == "" and goal.prepared_review is None
    await h.db.agent_updates.update_one({"owner_id": OWNER, "fingerprint": decision.fingerprint},
        {"$unset": {"prepared_result_ref": ""}})
    decision.prepared_result_ref = None
    assert await h.service.visibility.show(OWNER, goal, decision)
    assert await h.delivery.ambient_line(OWNER)
    await review(h)
    assert await h.delivery.ambient_line(OWNER) is None
    assert not await h.service.visibility.show(OWNER, goal, decision)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["source_revoked", "foreign_owner", "cancelled", "citations_changed"])
async def test_existing_owner_and_source_fences_still_dominate_review_binding(monkeypatch, change):
    h = await setup(monkeypatch)
    goal, facts, decision, _, plan = await queue(h)
    if change == "source_revoked":
        await h.db.memories.update_one({"user_id": OWNER, "id": MEMORY}, {"$set": {"status": "forgotten"}})
    else:
        mutation = {"foreign_owner": {"owner_id": "other-synthetic-owner"},
                    "cancelled": {"status": "cancelled"},
                    "citations_changed": {"prepared_sources": []}}[change]
        await h.db.agent_goals.update_one({"id": goal.id, "owner_id": OWNER}, {"$set": mutation})
    assert not await h.service.visibility.show(OWNER, goal, decision)
    assert await h.service._raise_need(OWNER, goal, decision, facts) is None
    await h.delivery._send(OWNER, plan)
    assert not h.channel.sent
    assert (await h.delivery.repo.get_plan(OWNER, plan.id)).status == "cancelled"


@pytest.mark.asyncio
async def test_home_archive_outage_keeps_pending_handoff_for_recovery(monkeypatch):
    h = await setup(monkeypatch)
    goal, _, decision = await decide(h)
    with monkeypatch.context() as outage:
        goal_read_outage(outage, h.db)
        assert not await h.service.visibility.show(OWNER, goal, decision)
        row = await h.db.agent_updates.find_one({"owner_id": OWNER, "fingerprint": decision.fingerprint})
        assert row["home_pending"] is True and "home_skipped" not in row
    await h.db.agent_updates.update_one({"owner_id": OWNER, "fingerprint": decision.fingerprint},
        {"$set": {"home_due_at": past()}})
    assert await VisibilityService(h.db).recover_pending_home() == {
        "checked": 1, "shown": 1, "deferred": 0, "stale": 0,
    }
    with monkeypatch.context() as outage:
        goal_read_outage(outage, h.db)
        assert await DeliveryService(h.db).ambient_line(OWNER) is None
    assert await DeliveryService(h.db).ambient_line(OWNER)
    assert not h.channel.sent


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["evaluate", "due", "send"])
async def test_delivery_archive_outage_preserves_same_plan_and_retries_current_artifact(monkeypatch, boundary):
    h = await setup(monkeypatch)
    _, _, _, need, plan = await queue(h)
    await h.db.delivery_plans.update_one({"id": plan.id}, {"$set": {"not_before": past()}})
    h.decide.reset_mock()
    with monkeypatch.context() as outage:
        goal_read_outage(outage, h.db)
        if boundary == "evaluate":
            result = await h.delivery.evaluate_subject(OWNER, DeliverySubject.model_validate(need.as_subject()))
            assert result.unavailable and result.blocked_by == "source_check_unavailable"
        elif boundary == "due":
            assert await h.delivery.deliver_due(OWNER) == {"sent": 0, "cancelled": 0, "held": 1}
        else:
            await h.delivery._send(OWNER, plan)
        pending = await h.delivery.repo.get_plan(OWNER, plan.id)
        assert pending.status == "pending" and pending.not_before > past()
        assert not h.channel.sent and h.decide.await_count == 0
    h.decide.return_value = push()
    await h.db.delivery_plans.update_one({"id": plan.id}, {"$set": {"not_before": past()}})
    assert await DeliveryService(h.db).deliver_due(OWNER) == {"sent": 1, "cancelled": 0, "held": 0}
    assert len(h.channel.sent) == 1 and h.channel.sent[0]["plan_id"] == plan.id


@pytest.mark.asyncio
async def test_real_verifier_review_reaches_visibility_sdk_and_ready_copy_is_quietened(monkeypatch):
    h = await setup(monkeypatch, mock_visibility=False)

    def reply(_system, payload):
        if "what_was_done" in payload:
            return {"outcome": "partially_achieved", "what_is_missing": "Una premessa resta da controllare.",
                    "reasoning": "Il risultato non è ancora confermato."}
        if "what_happened" in payload:
            return {"decision": "continue", "reasoning": "Rivedere la premessa nella preparazione."}
        assert payload["what_ora_did"]["prepared_review"]["outcome"] == "partial"
        assert "_prepared_result_ref" not in payload["what_ora_did"]
        return visible()

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(h.db, mode="live") as probe:
        run = AgentRun(owner_id=OWNER, goal_id=h.goal.id)
        result = await h.service._finish(OWNER, h.goal, h.plan, run, AgentBudget(), language="it")
        assert result["state"] == "in_progress"
        goal = await AgentService(h.db).repo.get_goal(OWNER, h.goal.id)
        assert goal.prepared_review.outcome == "partial" and goal.prepared_text == RESULT
        facts = await h.service._run_facts(OWNER, goal, run)
        decision = await h.service.visibility.consider(OWNER, goal, what_happened=facts)
        assert decision.outcome == "silent" and decision.decided_by == "code"
        assert await h.service._raise_need(OWNER, goal, decision, facts) is None
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 3
        assert await h.db.agent_updates.count_documents({}) == 0
        assert await h.db.agent_needs.count_documents({}) == 0
        assert await h.db.delivery_plans.count_documents({}) == 0
        assert not probe.blocked_effects and not probe.network.blocked and probe.push_attempts == 0
