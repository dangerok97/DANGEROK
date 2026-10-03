import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionStep, AutonomousGoal, ExecutionReceipt
from home import manual_event as manual_calendar
from home.manual_event import create_manual_event, get_manual_event, home_event_times


async def _event(db):
    day = (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=8)).date().isoformat()
    start, end = home_event_times(day, "10:15", "Europe/Rome")
    public = await create_manual_event(
        db, "alice", title="Appuntamento con il tecnico",
        start=start, end=end, tz_name="Europe/Rome",
    )
    return day, public, await get_manual_event(db, "alice", public["id"])


@pytest.mark.asyncio
async def test_external_confirmation_prepares_bound_phone_call_without_dial(monkeypatch):
    from agent.calendar_conflict import external_confirmation_step_from_answer
    from telephone.binding import binding_for
    from telephone.service import TelephoneService

    db = AsyncMongoMockClient().test
    monkeypatch.setattr(manual_calendar, "_wake", AsyncMock())
    day, event, node = await _event(db)
    new_start, new_end = home_event_times(day, "12:00", "Europe/Rome")
    goal = AutonomousGoal(
        owner_id="alice", objective="Risolvere il conflitto",
        desired_outcome="Appuntamento confermato alle 12", status="active",
    )
    prior = ActionStep(
        intent="Ottenere conferma esterna", step_type="ask_user",
        parameters={
            "conflict_followup": "external_channel",
            "target_ref": "calendar:" + event["id"],
            "title": event["title"], "day": day, "requested_time": "12:00",
            "start_datetime": new_start, "end_datetime": new_end,
            "timezone": "Europe/Rome", "expected_revision": node["updated_at"],
            "external_contact_reply": "Deve confermare il tecnico.",
        },
    )

    step, why = await external_confirmation_step_from_answer(
        db, "alice", goal, prior, "Chiamalo al 333 123 4567"
    )
    assert why == "" and step is not None
    assert step.step_type == "execute" and step.capability_needed == "phone.call"
    assert step.reaches_somebody_else is True

    call = await TelephoneService(db).get("alice", step.parameters["call_id"])
    assert call is not None and call.state == "authorised"
    assert not call.provider_ref  # Preparation has not crossed the carrier gate.
    binding = await binding_for(db, call.id)
    assert binding is not None and binding.target.entity_id == event["id"]
    assert binding.expected["storage"] == "home_manual"
    assert binding.expected["updated_at"] == node["updated_at"]


@pytest.mark.asyncio
async def test_phone_confirmation_applies_exact_home_event_and_refuses_stale_revision(monkeypatch):
    from telephone.application import apply_the_outcome
    from telephone.binding import bind_a_calendar_event
    from telephone.mission import CallMissionOutcome
    from telephone.models import Mandate
    from telephone.service import TelephoneService

    db = AsyncMongoMockClient().test
    monkeypatch.setattr(manual_calendar, "_wake", AsyncMock())

    # Successful exact application.
    day, event, _ = await _event(db)
    new_start, _ = home_event_times(day, "12:00", "Europe/Rome")
    call = await TelephoneService(db).prepare(
        "alice", to_number="3331234567", calling_whom="tecnico",
        mandate=Mandate(
            why_calling=f"Spostare {event['title']} al {day} alle 12:00",
            may_agree_to=[f"{day} alle 12:00"],
        ),
    )
    binding, why, question = await bind_a_calendar_event(
        db, call=call, calendar_ref=event["id"],
        desired_datetime=new_start, desired_minutes=60, same_day_only=True,
    )
    assert binding is not None and not why and question is False
    outcome = CallMissionOutcome(
        mission_id=binding.mission_id, status="success",
        confirmed_changes={"appointment_date": day, "old_time": "10:15", "new_time": "12:00"},
    )
    applied = await apply_the_outcome(db, call, outcome)
    assert applied is not None and applied.application_status == "applied"
    moved = await get_manual_event(db, "alice", event["id"])
    assert datetime.fromisoformat(moved["attributes"]["starts_at"]).strftime("%H:%M") == "12:00"
    again = await apply_the_outcome(db, call, outcome)
    assert again is not None and again.idempotency_key == applied.idempotency_key
    assert await db.call_mission_applications.count_documents({}) == 1

    # A newer revision wins over an older phone mission even if the start time
    # itself did not change.
    day2 = (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=9)).date().isoformat()
    start2, end2 = home_event_times(day2, "10:15", "Europe/Rome")
    second = await create_manual_event(
        db, "alice", title="Secondo tecnico", start=start2, end=end2,
        tz_name="Europe/Rome",
    )
    before = await get_manual_event(db, "alice", second["id"])
    desired2, _ = home_event_times(day2, "12:00", "Europe/Rome")
    call2 = await TelephoneService(db).prepare(
        "alice", to_number="3331234567", calling_whom="secondo tecnico",
        mandate=Mandate(
            why_calling=f"Spostare {second['title']} al {day2} alle 12:00",
            may_agree_to=[f"{day2} alle 12:00"],
        ),
    )
    binding2, _, _ = await bind_a_calendar_event(
        db, call=call2, calendar_ref=second["id"],
        desired_datetime=desired2, desired_minutes=60, same_day_only=True,
    )
    await manual_calendar.update_manual_event(
        db, "alice", second["id"], {"location": "Nuovo luogo"},
        expected_updated_at=before["updated_at"],
    )
    stale = CallMissionOutcome(
        mission_id=binding2.mission_id, status="success",
        confirmed_changes={"appointment_date": day2, "old_time": "10:15", "new_time": "12:00"},
    )
    refused = await apply_the_outcome(db, call2, stale)
    assert refused is not None and refused.application_status == "conflict"
    current = await get_manual_event(db, "alice", second["id"])
    assert datetime.fromisoformat(current["attributes"]["starts_at"]).strftime("%H:%M") == "10:15"


@pytest.mark.asyncio
async def test_only_verified_phone_application_wakes_same_agent_goal(monkeypatch):
    from agent.phone_bridge import on_call_finished
    from ambient.service import AmbientService
    from telephone.application import apply_the_outcome
    from telephone.binding import bind_a_calendar_event
    from telephone.mission import CallMissionOutcome
    from telephone.models import Mandate
    from telephone.service import TelephoneService

    db = AsyncMongoMockClient().test
    monkeypatch.setattr(manual_calendar, "_wake", AsyncMock())
    scheduled = AsyncMock()
    monkeypatch.setattr(AmbientService, "schedule", scheduled)

    day, event, _ = await _event(db)
    new_start, _ = home_event_times(day, "12:00", "Europe/Rome")
    goal = AutonomousGoal(
        owner_id="alice", objective="Risolvere il conflitto",
        desired_outcome="Il tecnico ha confermato e l'appuntamento è alle 12",
        status="waiting",
    )
    await db.agent_goals.insert_one(goal.model_dump())
    call = await TelephoneService(db).prepare(
        "alice", to_number="3331234567", calling_whom="tecnico",
        mandate=Mandate(
            why_calling=f"Spostare {event['title']} al {day} alle 12:00",
            may_agree_to=[f"{day} alle 12:00"],
        ),
    )
    binding, _, _ = await bind_a_calendar_event(
        db, call=call, calendar_ref=event["id"],
        desired_datetime=new_start, desired_minutes=60, same_day_only=True,
    )
    receipt = ExecutionReceipt(
        owner_id="alice", goal_id=goal.id, action_intent_id="act_phone",
        idempotency_key="phone-effect", capability="phone.call",
        provider="vonage", external_ref=call.id, provider_status="accepted",
    )
    await db.agent_receipts.insert_one(receipt.model_dump())

    assert await on_call_finished(db, call) is False
    assert (await db.agent_receipts.find_one({"id": receipt.id}))["provider_status"] == "accepted"

    outcome = CallMissionOutcome(
        mission_id=binding.mission_id, status="success",
        confirmed_changes={"appointment_date": day, "old_time": "10:15", "new_time": "12:00"},
    )
    assert (await apply_the_outcome(db, call, outcome)).application_status == "applied"
    assert await on_call_finished(db, call) is True
    updated = await db.agent_receipts.find_one({"id": receipt.id})
    assert updated["provider_status"] == "succeeded"
    woke = await db.agent_goals.find_one({"id": goal.id})
    assert woke["status"] == "active" and woke["next_run_at"]
    evidence = await db.agent_evidence.find(
        {"owner_id": "alice", "goal_id": goal.id}, {"_id": 0}
    ).to_list(10)
    assert any("12:00" in row["claim"] for row in evidence)
    scheduled.assert_awaited()
