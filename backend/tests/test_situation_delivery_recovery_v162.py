"""Durable delivery judgement and recoverable source reads, with no real push.

The existing Situation/goal/Need/Delivery stores and worker run in mongomock.
Weather, model decisions and notification transport are synthetic fixtures;
these tests do not prove physical dryness or receipt on a device.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from agent.needs import NeedService
from agent.models import AutonomousGoal, CommunicationNeed
from agent.repository import AgentRepository
from ambient.runtime import _serve_delivery_admission
from delivery import admission
from delivery.models import DeliveryPlan, DeliveryResult
from delivery.service import DeliveryService
from places.models import Coordinates
from places.service import PlacesService
from situations.outcomes import current_outcome
from situations.models import SituationUpdate
from situations.repository import SituationRepository
from situations.service import SituationService

from test_situation_outcome_delivery_v160 import (
    OWNER, SID, finish, pending, push, setup,
)


@pytest.fixture
def delivery_need_already_materialised(monkeypatch):
    """These Delivery cases start after Visibility has already made a Need.

    Their helper closes a goal directly, bypassing that preceding judgement.
    Exclude only its new completion queue so this fixture cannot request an
    unmocked Visibility judgement. The three-queue tests below do not use this
    fixture; completion integration tests cover the complete preceding path.
    """
    from agent import completion_handoff

    monkeypatch.setattr(completion_handoff, "next_due", AsyncMock(return_value=None))


def advance_admission_clock(monkeypatch, moment):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment if tz else moment.replace(tzinfo=None)

    monkeypatch.setattr(admission, "datetime", Clock)


async def bind_saved_place(db):
    place = await PlacesService(db).save_place(
        OWNER, label="Luogo sintetico per il bucato", role="other",
        locality="Tarquinia", coordinates=Coordinates(latitude=42.249, longitude=11.756),
    )
    await db.situations.update_one({"id": SID, "user_id": OWNER}, {
        "$set": {"linked_object_refs": [f"place:{place.id}"]},
    })
    await db.agent_evidence.update_one({
        "owner_id": OWNER, "provenance.capability": "weather.read",
    }, {"$set": {"provenance.source_refs": [
        f"situation:{SID}:revision:1", f"place:{place.id}",
        f"place_snapshot:{place.id}:{place.updated_at}",
    ]}})
    return place


async def open_question(db, owner=OWNER):
    goal = AutonomousGoal(
        owner_id=owner, status="waiting", objective="Preparare un passaggio sintetico",
        desired_outcome="Aspettare una risposta necessaria", requires_user_authority=True,
    )
    await AgentRepository(db).create_goal(goal)
    return await NeedService(db).raise_need(CommunicationNeed(
        owner_id=owner, goal_id=goal.id, kind="needs_authority",
        summary="La preparazione sintetica richiede il tuo consenso.",
        reason="Non eseguire un effetto esterno senza consenso.",
        requires_response=True, response_kind="authority",
    ))


@pytest.mark.asyncio
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_unavailable_final_judgement_is_recovered_by_existing_worker_after_reload(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    decision.return_value = None

    unavailable = await service.needs.offer_to_delivery(OWNER, need)
    assert unavailable.unavailable
    assert not channel.sent and await db.delivery_plans.count_documents({}) == 0
    assert (await service.repo.get_goal(OWNER, goal.id)).status == "completed"

    # No open goal, foreground request or new message is needed to recover.
    decision.return_value = push()
    advance_admission_clock(monkeypatch, datetime.now(timezone.utc) + timedelta(minutes=2))
    await _serve_delivery_admission(db)

    assert len(channel.sent) == 1
    assert "dovrebbero" in channel.sent[0]["body"]
    assert decision.await_count == 2
    await _serve_delivery_admission(db)
    assert decision.await_count == 2 and len(channel.sent) == 1
    assert (await NeedService(db).get(OWNER, need.id)).is_open
    state = await SituationRepository(db).get(OWNER, SID)
    assert state.status == "changed" and state.resolved_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["silence", "in_app"])
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_an_explicit_quiet_decision_does_not_become_an_automatic_retry(monkeypatch, mode):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    decision.return_value = {"mode": mode}
    result = await service.needs.offer_to_delivery(OWNER, need)
    assert result.mode == mode and not result.unavailable

    decision.return_value = push()
    advance_admission_clock(monkeypatch, datetime.now(timezone.utc) + timedelta(minutes=10))
    assert await _serve_delivery_admission(db) == 0
    assert decision.await_count == 1 and not channel.sent
    assert await db.delivery_plans.count_documents({}) == 0
    assert (await service.needs.get(OWNER, need.id)).is_open


@pytest.mark.asyncio
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_unavailable_is_bounded_and_reoffering_does_not_reset_exhaustion(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    start = datetime.now(timezone.utc)
    decision.return_value = None
    await service.needs.offer_to_delivery(OWNER, need)
    assert await _serve_delivery_admission(db) == 0
    for minutes in (2, 8):
        advance_admission_clock(monkeypatch, start + timedelta(minutes=minutes))
        assert await _serve_delivery_admission(db) == 1
    row = await db.agent_needs.find_one({"owner_id": OWNER, "id": need.id})
    assert row["delivery_review_attempts"] == admission.MAX_ATTEMPTS == 3
    assert row["delivery_review_state"] == "paused" and row["delivery_review_due"] is None
    decision.return_value = push()
    advance_admission_clock(monkeypatch, start + timedelta(minutes=15))
    assert await _serve_delivery_admission(db) == 0
    assert (await NeedService(db).offer_to_delivery(OWNER, need)).unavailable
    assert decision.await_count == 3 and not channel.sent
    assert (await NeedService(db).get(OWNER, need.id)).is_open


@pytest.mark.asyncio
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_cancelled_worker_keeps_the_intent_and_expired_lease_is_reclaimable(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    decision.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await service.needs.offer_to_delivery(OWNER, need)
    row = await db.agent_needs.find_one({"owner_id": OWNER, "id": need.id})
    assert row["delivery_review_state"] == "pending" and row["delivery_review_token"]
    assert await _serve_delivery_admission(db) == 0
    decision.side_effect = None
    decision.return_value = push()
    advance_admission_clock(monkeypatch, datetime.fromisoformat(row["delivery_review_lease_until"]) + timedelta(seconds=1))
    assert await _serve_delivery_admission(db) == 1
    assert decision.await_count == 2 and len(channel.sent) == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_repeated_worker_crashes_do_not_gain_an_extra_attempt_after_the_cap(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    decision.side_effect = asyncio.CancelledError
    for _ in range(admission.MAX_ATTEMPTS):
        with pytest.raises(asyncio.CancelledError):
            await NeedService(db).offer_to_delivery(OWNER, need)
        row = await db.agent_needs.find_one({"id": need.id, "owner_id": OWNER})
        advance_admission_clock(monkeypatch, datetime.fromisoformat(row["delivery_review_lease_until"]) + timedelta(seconds=1))
    # A final recovery-only claim may look for a material handoff, but cannot
    # buy another judgement when all three attempts have been spent.
    assert await _serve_delivery_admission(db) == 1
    assert await _serve_delivery_admission(db) == 0
    row = await db.agent_needs.find_one({"id": need.id, "owner_id": OWNER})
    assert row["delivery_review_state"] == "paused" and row["delivery_review_due"] is None
    assert decision.await_count == 3 and not channel.sent


@pytest.mark.asyncio
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_concurrent_workers_cannot_claim_one_judgement_twice(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    decision.return_value = None
    await service.needs.offer_to_delivery(OWNER, need)
    advance_admission_clock(monkeypatch, datetime.now(timezone.utc) + timedelta(minutes=2))
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        entered.set()
        await release.wait()
        return push()

    decision.side_effect = slow
    running = asyncio.create_task(admission.drain_needs(db, owner_id=OWNER, limit=1))
    await asyncio.wait_for(entered.wait(), 1)
    assert await admission.drain_needs(db, owner_id=OWNER, limit=1) == 0
    release.set()
    assert await running == 1
    assert decision.await_count == 2 and len(channel.sent) == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_a_late_unavailable_result_cannot_acknowledge_another_workers_lease(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def first_waits(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return None

    decision.side_effect = first_waits
    old = asyncio.create_task(service.needs.offer_to_delivery(OWNER, need))
    await asyncio.wait_for(entered.wait(), 1)
    row = await db.agent_needs.find_one({"id": need.id, "owner_id": OWNER})
    advance_admission_clock(monkeypatch, datetime.fromisoformat(row["delivery_review_lease_until"]) + timedelta(seconds=1))
    assert await admission.drain_needs(db, owner_id=OWNER, limit=1) == 1
    newer = await db.agent_needs.find_one({"id": need.id, "owner_id": OWNER})
    release.set()
    await old
    after = await db.agent_needs.find_one({"id": need.id, "owner_id": OWNER})
    assert after == newer
    assert after["delivery_review_attempts"] == 2 and not channel.sent


@pytest.mark.asyncio
@pytest.mark.parametrize("when", [None, "future"])
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_crash_after_saving_pending_plan_repairs_existing_wake_without_redoing_admission(monkeypatch, when):
    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    need = await open_question(db)
    for index in range(22):
        await DeliveryService(db).repo.save_plan(DeliveryPlan(
            owner_id=OWNER, source_type="agent_need", source_id=need.id, mode="push",
            status="cancelled", created_at=(datetime.now(timezone.utc) - timedelta(hours=1, seconds=index)).isoformat(),
        ))
    decision.return_value = push((datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat() if when else None)
    method = "_arrange_wake" if when else "_send"
    with patch.object(DeliveryService, method, AsyncMock(side_effect=asyncio.CancelledError)):
        with pytest.raises(asyncio.CancelledError):
            await NeedService(db).offer_to_delivery(OWNER, need)
    plans = await DeliveryService(db).repo.open_plans(OWNER)
    assert len(plans) == 1 and plans[0].status == "pending" and not channel.sent
    assert await db.ambient_wakes.count_documents({"delivery_plan_id": plans[0].id}) == 0
    row = await db.agent_needs.find_one({"id": need.id, "owner_id": OWNER})
    advance_admission_clock(monkeypatch, datetime.fromisoformat(row["delivery_review_lease_until"]) + timedelta(seconds=1))
    assert await _serve_delivery_admission(db) == 1
    assert decision.await_count == 1 and not channel.sent
    wake = await db.ambient_wakes.find_one({
        "owner_id": OWNER, "delivery_plan_id": plans[0].id, "reason": "delivery_recheck", "status": "pending",
    })
    assert wake is not None
    assert await _serve_delivery_admission(db) == 0
    assert await db.delivery_plans.count_documents({"source_id": need.id, "status": "pending"}) == 1
    assert await db.ambient_wakes.count_documents({"delivery_plan_id": plans[0].id, "status": "pending"}) == 1

    # The repaired alarm performs the ordinary fresh judgement, not a blind send.
    from ambient.models import AmbientWake
    from ambient.service import AmbientService
    monkeypatch.setattr(AmbientService, "app_state", AsyncMock(return_value="background"))
    decision.return_value = push()
    out = await AmbientService(db).recheck_delivery(AmbientWake.model_validate(wake))
    assert out.handled and len(channel.sent) == 1 and decision.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted", [True, False])
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_crash_after_a_question_transport_result_does_not_send_again_before_queue_ack(monkeypatch, accepted):
    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    need = await open_question(db)
    original_send = DeliveryService._send
    if not accepted:
        original_transport = channel.send

        async def unconfirmed_transport(**kwargs):
            await original_transport(**kwargs)
            return {"ok": False, "provider": channel.name}

        monkeypatch.setattr(channel, "send", unconfirmed_transport)

    async def sent_then_crash(self, owner, plan):
        await original_send(self, owner, plan)
        raise asyncio.CancelledError

    with patch.object(DeliveryService, "_send", sent_then_crash):
        with pytest.raises(asyncio.CancelledError):
            await NeedService(db).offer_to_delivery(OWNER, need)
    assert len(channel.sent) == 1 and (await NeedService(db).get(OWNER, need.id)).is_open
    row = await db.agent_needs.find_one({"id": need.id, "owner_id": OWNER})
    advance_admission_clock(monkeypatch, datetime.fromisoformat(row["delivery_review_lease_until"]) + timedelta(seconds=1))
    assert await _serve_delivery_admission(db) == 1
    assert await _serve_delivery_admission(db) == 0
    assert decision.await_count == 1 and len(channel.sent) == 1
    assert await db.delivery_plans.count_documents({"source_id": need.id}) == 1
    assert (await db.delivery_plans.find_one({"source_id": need.id}))["status"] == ("delivered" if accepted else "held")
    assert (await NeedService(db).get(OWNER, need.id)).is_open


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["collected", "cancelled", "revision", "assessment_expired", "foreign_source"])
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_retry_cannot_revive_a_closed_changed_expired_or_foreign_situation(monkeypatch, change):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    decision.return_value = None
    await service.needs.offer_to_delivery(OWNER, need)
    if change == "collected":
        result = await SituationService(db).apply(
            user_id=OWNER, session_id="synthetic-collection", reasoning_epoch="synthetic-collected-after-result",
            update=SituationUpdate(operation="resolve", situation_id=SID, expected_revision=2,
                                   current_state_summary="Panni già ritirati.", source="user_conversation"),
        )
        assert result["status"] == "success"
    elif change == "cancelled":
        await NeedService(db).cancel(OWNER, need.id, how="Non serve più avvisare.", by="user")
    elif change == "revision":
        await db.situations.update_one({"id": SID, "user_id": OWNER}, {"$inc": {"revision": 1}})
    elif change == "assessment_expired":
        await db.agent_goals.update_one({"id": goal.id, "owner_id": OWNER}, {"$set": {
            "situation_outcome.valid_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }})
    else:
        await db.situations.update_one({"id": SID, "user_id": OWNER}, {"$set": {"user_id": "other-synthetic-owner"}})
    decision.return_value = push()
    advance_admission_clock(monkeypatch, datetime.now(timezone.utc) + timedelta(minutes=2))
    await _serve_delivery_admission(db)
    assert decision.await_count == 1 and not channel.sent
    assert await db.delivery_plans.count_documents({}) == 0
    assert await _serve_delivery_admission(db) == 0
    assert (await service.repo.get_goal(OWNER, goal.id)).status == "completed"


@pytest.mark.asyncio
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_owner_mismatch_cannot_consume_or_reset_another_owners_pending_review(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    decision.return_value = None
    await service.needs.offer_to_delivery(OWNER, need)
    before = await db.agent_needs.find_one({"id": need.id})
    assert await NeedService(db).offer_to_delivery("other-synthetic-owner", need) is None
    assert await admission.drain_needs(db, owner_id="other-synthetic-owner", now=datetime.now(timezone.utc) + timedelta(minutes=5)) == 0
    assert await db.agent_needs.find_one({"id": need.id}) == before
    assert decision.await_count == 1 and not channel.sent


@pytest.mark.asyncio
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_source_closes_during_retried_model_judgement_and_last_provider_check_blocks_send(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    decision.return_value = None
    await service.needs.offer_to_delivery(OWNER, need)

    async def closed_while_deciding(*args, **kwargs):
        await db.situations.update_one({"id": SID, "user_id": OWNER}, {"$set": {"status": "resolved"}})
        return push()

    decision.side_effect = closed_while_deciding
    advance_admission_clock(monkeypatch, datetime.now(timezone.utc) + timedelta(minutes=2))
    assert await _serve_delivery_admission(db) == 1
    assert decision.await_count == 2 and not channel.sent
    assert (await db.delivery_plans.find_one({"source_id": need.id}))["status"] == "cancelled"
    assert await _serve_delivery_admission(db) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing", "dismissed", "snapshot", "owner"])
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_real_place_change_after_transient_outage_permanently_cancels_the_old_plan(monkeypatch, change):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    place = await bind_saved_place(db)
    original = await db.life_places.find_one({"id": place.id})
    delivery_id = await pending(db, need, decision)
    await finish(db, service, goal, plan)
    with patch.object(PlacesService, "get_place", AsyncMock(side_effect=TimeoutError)):
        assert (await DeliveryService(db).deliver_due(OWNER))["held"] == 1
    if change == "missing":
        await db.life_places.delete_one({"id": place.id})
    else:
        values = ({"state": "dismissed"} if change == "dismissed" else
                  {"updated_at": "2026-10-12T00:00:00+00:00"} if change == "snapshot" else
                  {"user_id": "other-synthetic-owner"})
        await db.life_places.update_one({"id": place.id}, {"$set": values})
    current = await DeliveryService(db).repo.get_plan(OWNER, delivery_id)
    from delivery import service as delivery_service
    monkeypatch.setattr(delivery_service, "_now", lambda: datetime.fromisoformat(current.not_before) + timedelta(seconds=1))
    assert (await DeliveryService(db).deliver_due(OWNER))["cancelled"] == 1
    assert not channel.sent and decision.await_count == 1
    # Restoring a source does not restore a cancelled intention to notify.
    await db.life_places.replace_one({"id": place.id}, original, upsert=True)
    assert await current_outcome(db, OWNER, goal, allow_settled=True)
    assert (await DeliveryService(db).deliver_due(OWNER))["sent"] == 0
    assert (await DeliveryService(db).repo.get_plan(OWNER, delivery_id)).status == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize(("needs", "opportunities"), [(2, 0), (0, 2), (2, 2)])
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_existing_two_review_slots_are_work_conserving_and_fair_between_sources(monkeypatch, needs, opportunities):
    from opportunities.models import Opportunity
    from opportunities.repository import OpportunityRepository

    db, _, _, _, _, channel, _ = await setup(monkeypatch)
    evaluate_need = AsyncMock(return_value=DeliveryResult(unavailable=True))
    evaluate_opportunity = AsyncMock(return_value=DeliveryResult(mode="in_app"))
    monkeypatch.setattr(DeliveryService, "evaluate_subject", evaluate_need)
    monkeypatch.setattr(DeliveryService, "evaluate", evaluate_opportunity)
    for index in range(needs):
        # Source-category preference applies after owner fairness. Keep the
        # mixed case on one owner; the next test covers another owner in
        # either queue taking precedence over that category preference.
        owner = OWNER if index == 0 or opportunities else "other-synthetic-owner"
        need = await open_question(db, owner)
        await NeedService(db).offer_to_delivery(owner, need)
    for index in range(opportunities):
        await OpportunityRepository(db).save(Opportunity(
            owner_id=OWNER, identity_key=f"synthetic-laundry-admission:{index}", status="active",
            semantic_summary="Una questione sintetica", why_it_matters="Riesame richiesto", initiative="inform",
        ))
    evaluate_need.reset_mock()
    evaluate_need.return_value = DeliveryResult(mode="in_app")
    advance_admission_clock(monkeypatch, datetime.now(timezone.utc) + timedelta(minutes=2))
    assert await _serve_delivery_admission(db) == 2
    assert evaluate_need.await_count + evaluate_opportunity.await_count == 2
    if needs and opportunities:
        assert evaluate_need.await_count == evaluate_opportunity.await_count == 1
    elif needs:
        assert {call.args[0] for call in evaluate_need.await_args_list} == {OWNER, "other-synthetic-owner"}
    assert not channel.sent


@pytest.mark.asyncio
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_temporary_place_read_failure_holds_the_real_plan_then_retries_current_source(monkeypatch):
    arrange_wake = DeliveryService._arrange_wake
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    monkeypatch.setattr(DeliveryService, "_arrange_wake", arrange_wake)
    await bind_saved_place(db)
    delivery_id = await pending(db, need, decision)
    await finish(db, service, goal, plan)
    assert await current_outcome(db, OWNER, goal, allow_settled=True)

    with patch.object(PlacesService, "get_place", AsyncMock(side_effect=TimeoutError)):
        result = await DeliveryService(db).deliver_due(OWNER)

    assert result == {"sent": 0, "cancelled": 0, "held": 1}
    current = await DeliveryService(db).repo.get_plan(OWNER, delivery_id)
    assert current.status == "pending"
    assert not channel.sent and decision.await_count == 1
    assert await db.ambient_wakes.find_one({
        "owner_id": OWNER, "delivery_plan_id": delivery_id, "status": "pending",
    })
    assert await current_outcome(db, OWNER, goal, allow_settled=True)

    # Advance the clock of the real delivery pass, without changing the source.
    from delivery import service as delivery_service
    moment = datetime.fromisoformat(current.not_before) + timedelta(seconds=1)
    monkeypatch.setattr(delivery_service, "_now", lambda: moment)
    result = await DeliveryService(db).deliver_due(OWNER)
    assert result["sent"] == 1 and len(channel.sent) == 1
    assert (await DeliveryService(db).repo.get_plan(OWNER, delivery_id)).status == "delivered"
    assert (await DeliveryService(db).deliver_due(OWNER))["sent"] == 0
    assert decision.await_count == 2 and len(channel.sent) == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_late_push_decision_after_takeover_cannot_materialise_a_second_question_plan(monkeypatch):
    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    need = await open_question(db)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def first_waits(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return push()

    decision.side_effect = first_waits
    old = asyncio.create_task(NeedService(db).offer_to_delivery(OWNER, need))
    await asyncio.wait_for(entered.wait(), 1)
    row = await db.agent_needs.find_one({"id": need.id, "owner_id": OWNER})
    advance_admission_clock(monkeypatch, datetime.fromisoformat(row["delivery_review_lease_until"]) + timedelta(seconds=1))
    assert await _serve_delivery_admission(db) == 1
    assert len(channel.sent) == 1
    release.set()
    await old
    assert len(channel.sent) == 1
    assert await db.delivery_plans.count_documents({"owner_id": OWNER, "source_id": need.id}) == 1
    assert (await NeedService(db).get(OWNER, need.id)).is_open


@pytest.mark.asyncio
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_crash_on_last_judgement_repairs_pending_plan_without_a_fourth_model_call(monkeypatch):
    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    need = await open_question(db)
    start = datetime.now(timezone.utc)
    decision.return_value = None
    await NeedService(db).offer_to_delivery(OWNER, need)
    advance_admission_clock(monkeypatch, start + timedelta(minutes=2))
    assert await _serve_delivery_admission(db) == 1
    advance_admission_clock(monkeypatch, start + timedelta(minutes=8))
    decision.return_value = push()
    with patch.object(DeliveryService, "_send", AsyncMock(side_effect=asyncio.CancelledError)):
        with pytest.raises(asyncio.CancelledError):
            await _serve_delivery_admission(db)
    row = await db.agent_needs.find_one({"owner_id": OWNER, "id": need.id})
    assert row["delivery_review_attempts"] == 3 and decision.await_count == 3
    plan = await db.delivery_plans.find_one({"owner_id": OWNER, "source_id": need.id})
    assert plan["status"] == "pending"
    advance_admission_clock(monkeypatch, datetime.fromisoformat(row["delivery_review_lease_until"]) + timedelta(seconds=1))
    assert await _serve_delivery_admission(db) == 1
    assert await db.ambient_wakes.find_one({"owner_id": OWNER, "delivery_plan_id": plan["id"], "status": "pending"})
    assert decision.await_count == 3 and not channel.sent
    assert (await db.agent_needs.find_one({"id": need.id}))["delivery_review_attempts"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["cancelled", "expired", "delivered"])
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_old_terminal_history_is_not_a_handoff_for_a_new_unavailable_judgement(monkeypatch, status):
    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    need = await open_question(db)
    before = datetime.now(timezone.utc) - timedelta(hours=1)
    for index in range(22):
        await DeliveryService(db).repo.save_plan(DeliveryPlan(
            owner_id=OWNER, source_type="agent_need", source_id=need.id, mode="push",
            status=status, created_at=(before + timedelta(seconds=index)).isoformat(),
            delivered_at=before.isoformat() if status == "delivered" else None,
        ))
    decision.return_value = None
    await NeedService(db).offer_to_delivery(OWNER, need)
    decision.return_value = {"mode": "in_app"}
    advance_admission_clock(monkeypatch, datetime.now(timezone.utc) + timedelta(minutes=2))
    assert await _serve_delivery_admission(db) == 1
    assert decision.await_count == 2 and not channel.sent
    assert await db.delivery_plans.count_documents({"source_id": need.id}) == 22


@pytest.mark.asyncio
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_expired_need_is_consumed_as_closed_without_another_model_call(monkeypatch):
    db, service, goal, need, plan, channel, decision = await setup(monkeypatch)
    await finish(db, service, goal, plan)
    decision.return_value = None
    await service.needs.offer_to_delivery(OWNER, need)
    await db.agent_needs.update_one({"owner_id": OWNER, "id": need.id}, {"$set": {"status": "expired"}})
    advance_admission_clock(monkeypatch, datetime.now(timezone.utc) + timedelta(minutes=2))
    assert await _serve_delivery_admission(db) == 1
    assert decision.await_count == 1 and not channel.sent
    row = await db.agent_needs.find_one({"owner_id": OWNER, "id": need.id})
    assert row["delivery_review_due"] is None and row["delivery_review_state"] == "settled"


@pytest.mark.asyncio
@pytest.mark.parametrize("second_owner_queue", ["opportunity", "need"])
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_mixed_queue_prefers_a_second_owner_before_reusing_the_first_owners_slot(monkeypatch, second_owner_queue):
    from opportunities.models import Opportunity
    from opportunities.repository import OpportunityRepository

    db, _, _, _, _, channel, _ = await setup(monkeypatch)
    evaluate_need = AsyncMock(return_value=DeliveryResult(unavailable=True))
    evaluate_opportunity = AsyncMock(return_value=DeliveryResult(mode="in_app"))
    monkeypatch.setattr(DeliveryService, "evaluate_subject", evaluate_need)
    monkeypatch.setattr(DeliveryService, "evaluate", evaluate_opportunity)
    owners = [OWNER, "second-owner"] if second_owner_queue == "need" else [OWNER]
    for owner in owners:
        need = await open_question(db, owner)
        await NeedService(db).offer_to_delivery(owner, need)
    owners = [OWNER, "second-owner"] if second_owner_queue == "opportunity" else [OWNER]
    for owner in owners:
        await OpportunityRepository(db).save(Opportunity(
            owner_id=owner, identity_key=f"synthetic-mixed-fair:{owner}", status="active",
            semantic_summary="Questione sintetica", why_it_matters="Riesame", initiative="inform",
        ))
    evaluate_need.reset_mock()
    evaluate_need.return_value = DeliveryResult(mode="in_app")
    advance_admission_clock(monkeypatch, datetime.now(timezone.utc) + timedelta(minutes=2))
    assert await _serve_delivery_admission(db) == 2
    reviewed_owners = [call.args[0] for call in evaluate_need.await_args_list + evaluate_opportunity.await_args_list]
    assert sorted(reviewed_owners) == sorted([OWNER, "second-owner"])
    assert not channel.sent


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "held"])
@pytest.mark.usefixtures("delivery_need_already_materialised")
async def test_expired_open_plan_is_not_a_handoff_when_the_need_is_still_current(monkeypatch, status):
    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    need = await open_question(db)
    plan = await DeliveryService(db).repo.save_plan(DeliveryPlan(
        owner_id=OWNER, source_type="agent_need", source_id=need.id, mode="push", status=status,
        not_after=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    ))
    decision.return_value = None
    await NeedService(db).offer_to_delivery(OWNER, need)
    decision.return_value = {"mode": "in_app"}
    advance_admission_clock(monkeypatch, datetime.now(timezone.utc) + timedelta(minutes=2))
    assert await _serve_delivery_admission(db) == 1
    assert decision.await_count == 2 and not channel.sent
    assert (await DeliveryService(db).repo.get_plan(OWNER, plan.id)).status == "expired"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["silence", "in_app"])
async def test_registration_only_is_durable_without_a_judgement_and_never_restarts_a_settled_one(monkeypatch, mode):
    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    need = await open_question(db)
    assert await admission.register_need(db, OWNER, need.id)
    first = await db.agent_needs.find_one({"id": need.id, "owner_id": OWNER})
    assert first["delivery_review_attempts"] == 0
    assert first["delivery_review_state"] == "pending" and first["delivery_review_due"]
    assert "delivery_review_token" not in first
    assert await admission.register_need(db, OWNER, need.id)
    assert await db.agent_needs.find_one({"id": need.id, "owner_id": OWNER}) == first
    decision.assert_not_awaited()

    decision.return_value = {"mode": mode}
    assert await _serve_delivery_admission(db) == 1
    settled = await db.agent_needs.find_one({"id": need.id, "owner_id": OWNER})
    assert settled["delivery_review_state"] == "settled"
    # Replay of a completion checkpoint acknowledges the existing judgement;
    # it must not turn model-chosen silence into a fresh request to notify.
    assert await admission.register_need(db, OWNER, need.id)
    assert await db.agent_needs.find_one({"id": need.id, "owner_id": OWNER}) == settled
    assert await _serve_delivery_admission(db) == 0
    assert decision.await_count == 1 and not channel.sent


@pytest.mark.asyncio
async def test_registration_readback_is_owned_and_preserves_paused_or_closed_intentions(monkeypatch):
    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    need = await open_question(db)
    assert not await admission.register_need(db, "other-owner", need.id)
    assert not await admission.register_need(db, OWNER, "missing-need")
    assert await admission.register_need(db, OWNER, need.id)
    await db.agent_needs.update_one({"id": need.id}, {"$set": {
        "delivery_review_state": "paused", "delivery_review_attempts": 3,
        "delivery_review_due": None,
    }})
    paused = await db.agent_needs.find_one({"id": need.id})
    assert await admission.register_need(db, OWNER, need.id)
    assert await db.agent_needs.find_one({"id": need.id}) == paused
    await db.agent_needs.update_one({"id": need.id}, {"$set": {"status": "cancelled"}})
    assert await admission.register_need(db, OWNER, need.id)
    another = await open_question(db)
    await db.agent_needs.update_one({"id": another.id}, {"$set": {"status": "cancelled"}})
    assert not await admission.register_need(db, OWNER, another.id)
    decision.assert_not_awaited()
    assert not channel.sent


async def queue_review_fixture(db, kind, owner, due):
    """A pending checkpoint; queue tests replace only its bounded processor."""
    from opportunities.models import Opportunity
    from opportunities.repository import OpportunityRepository

    stamp = due.isoformat()
    if kind == "completion":
        goal = AutonomousGoal(owner_id=owner, status="completed", completed_at=stamp,
                              objective="Esito sintetico già completato",
                              desired_outcome="Comunicare l'esito sintetico")
        await AgentRepository(db).create_goal(goal)
        await db.agent_goals.update_one({"id": goal.id, "owner_id": owner}, {"$set": {
            "completion_visibility": {"id": f"handoff:{goal.id}", "pending": True,
                                      "due_at": stamp, "attempts": 0},
        }})
        return {"id": goal.id, "owner_id": owner, "due_at": stamp}
    if kind == "need":
        item = await open_question(db, owner)
        collection = db.agent_needs
    else:
        item = await OpportunityRepository(db).save(Opportunity(
            owner_id=owner, identity_key=f"queue:{owner}:{stamp}", status="active",
            semantic_summary="Questione sintetica", why_it_matters="Un esito utile", initiative="inform",
        ))
        collection = db.opportunities
    await collection.update_one({"id": item.id, "owner_id": owner}, {"$set": {
        "delivery_review_due": stamp, "delivery_review_started_at": stamp,
        "delivery_review_revision": f"revision:{item.id}", "delivery_review_state": "pending",
        "delivery_review_attempts": 0, "delivery_review_language": "it",
    }})
    return {"id": item.id, "owner_id": owner, "due_at": stamp}


def observe_queue_processors(monkeypatch):
    from agent import completion_handoff

    calls = []

    async def need(self, owner, subject, **kwargs):
        calls.append(("need", owner, subject.id))
        return DeliveryResult(mode="in_app")

    async def opportunity(self, owner, source_id, **kwargs):
        calls.append(("opportunity", owner, source_id))
        return DeliveryResult(mode="in_app")

    async def complete(db, row, **kwargs):
        calls.append(("completion", row["owner_id"], row["id"]))
        await db.agent_goals.update_one({"id": row["id"], "owner_id": row["owner_id"]}, {
            "$set": {"completion_visibility.pending": False, "completion_visibility.due_at": None},
        })

    # The real atomic queue claims run; only the expensive bounded work is
    # substituted. Full completion/source checks have their own integration
    # tests, and no model or notification is called by these scheduling tests.
    monkeypatch.setattr(DeliveryService, "evaluate_subject", need)
    monkeypatch.setattr(DeliveryService, "evaluate", opportunity)
    monkeypatch.setattr(completion_handoff, "_process", complete)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["need", "opportunity", "completion"])
async def test_completion_recovery_shares_two_slots_and_the_oldest_due_work_goes_first(monkeypatch, first):
    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    calls = observe_queue_processors(monkeypatch)
    moment = datetime.now(timezone.utc)
    order = [first] + [kind for kind in ("need", "opportunity", "completion") if kind != first]
    for index, kind in enumerate(order):
        await queue_review_fixture(db, kind, OWNER, moment - timedelta(minutes=3 - index))
    assert await _serve_delivery_admission(db) == 2
    assert [call[0] for call in calls] == order[:2]
    assert await _serve_delivery_admission(db) == 1
    assert [call[0] for call in calls] == order
    decision.assert_not_awaited()
    assert not channel.sent


@pytest.mark.asyncio
@pytest.mark.parametrize("second_queue", ["need", "opportunity", "completion"])
async def test_completion_queue_does_not_break_second_owner_priority_in_any_queue(monkeypatch, second_queue):
    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    calls = observe_queue_processors(monkeypatch)
    moment = datetime.now(timezone.utc)
    await queue_review_fixture(db, "completion", OWNER, moment - timedelta(minutes=5))
    for index, kind in enumerate(("need", "opportunity", "completion")):
        await queue_review_fixture(db, kind, OWNER, moment - timedelta(minutes=4) + timedelta(seconds=index))
    await queue_review_fixture(db, second_queue, "second-owner", moment - timedelta(minutes=1))
    assert await _serve_delivery_admission(db) == 2
    assert [(kind, owner) for kind, owner, _ in calls] == [
        ("completion", OWNER), (second_queue, "second-owner"),
    ]
    decision.assert_not_awaited()
    assert not channel.sent


@pytest.mark.asyncio
async def test_completion_only_work_can_use_both_existing_slots(monkeypatch):
    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    calls = observe_queue_processors(monkeypatch)
    moment = datetime.now(timezone.utc)
    for index in range(3):
        await queue_review_fixture(db, "completion", OWNER, moment - timedelta(minutes=3 - index))
    assert await _serve_delivery_admission(db) == 2
    assert len(calls) == 2 and {call[0] for call in calls} == {"completion"}
    assert await _serve_delivery_admission(db) == 1
    assert len(calls) == 3
    decision.assert_not_awaited()
    assert not channel.sent


@pytest.mark.asyncio
async def test_completion_registration_can_use_the_remaining_slot_without_a_nested_judgement(monkeypatch):
    from agent import completion_handoff

    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    calls = observe_queue_processors(monkeypatch)
    moment = datetime.now(timezone.utc)
    await queue_review_fixture(db, "completion", OWNER, moment - timedelta(minutes=1))

    async def complete_and_register(db, row, **kwargs):
        calls.append(("completion", row["owner_id"], row["id"]))
        need = await open_question(db, row["owner_id"])
        assert await admission.register_need(db, row["owner_id"], need.id)
        assert [kind for kind, _, _ in calls] == ["completion"]
        await db.agent_goals.update_one({"id": row["id"], "owner_id": row["owner_id"]}, {
            "$set": {"completion_visibility.pending": False, "completion_visibility.due_at": None},
        })

    monkeypatch.setattr(completion_handoff, "_process", complete_and_register)
    assert await _serve_delivery_admission(db) == 2
    assert [kind for kind, _, _ in calls] == ["completion", "need"]
    assert await _serve_delivery_admission(db) == 0
    decision.assert_not_awaited()
    assert not channel.sent


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["need", "opportunity", "completion"])
async def test_a_lost_exact_candidate_claim_cannot_take_another_record_or_spend_its_budget(monkeypatch, kind):
    from agent import completion_handoff

    db, _, _, _, _, channel, decision = await setup(monkeypatch)
    calls = observe_queue_processors(monkeypatch)
    moment = datetime.now(timezone.utc)
    selected = await queue_review_fixture(db, kind, OWNER, moment - timedelta(minutes=2))
    next_one = await queue_review_fixture(db, kind, "second-owner", moment - timedelta(minutes=1))
    collection = db.agent_goals if kind == "completion" else db.agent_needs if kind == "need" else db.opportunities
    lease = "completion_visibility.lease_until" if kind == "completion" else "delivery_review_lease_until"
    await collection.update_one({"id": selected["id"]}, {"$set": {
        lease: (moment + timedelta(minutes=2)).isoformat(),
    }})
    selected_before = await collection.find_one({"id": selected["id"]})
    next_before = await collection.find_one({"id": next_one["id"]})
    runner = completion_handoff.drain if kind == "completion" else admission.drain_needs if kind == "need" else admission.drain
    assert await runner(db, now=moment, limit=1, candidate=selected) == 0
    assert await collection.find_one({"id": selected["id"]}) == selected_before
    assert await collection.find_one({"id": next_one["id"]}) == next_before
    assert not calls and not channel.sent
    decision.assert_not_awaited()
