"""Real read-only skill execution at an explicitly scheduled Situation wake.

Regression from the 20 October user pilot: three opportunity_revisit worker
cycles ended in_progress with no source-bound weather check. The scheduler
must carry the model's SELECTED skill to its due time and execute it before
open-ended reasoning. All weather and Places responses here are synthetic.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.checkpoint_source import run_due_checkpoint_source
from agent.models import AgentBudget, AutonomousGoal
from agent.service import AgentService
from situations.models import SituationEvent, SituationState
from situations.followup import goal_id_for, read_followup, arrange_followup
from situations.repository import SituationRepository

OWNER = "synthetic-proactive-20261020"
SID = "sit_131c2d203aaf4889"
ROME = ZoneInfo("Europe/Rome")


async def setup(monkeypatch, *, capability="weather.read", locality="Tarquinia"):
    import weather
    from home.service import HomeService
    from places import lookup

    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().proactive_checkpoint
    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=1)).isoformat()
    due = (now - timedelta(seconds=90)).isoformat()
    state = SituationState(
        id=SID, user_id=OWNER, summary="Synthetic new independent case",
        attention_intent="Controllare la fonte esterna al momento scelto",
        location_label=locality, started_at=start,
        history=[
            SituationEvent(
                revision=1, operation="create", source="user_conversation",
                changes={"location_label": locality},
                source_refs=["user_conversation"],
            ),
        ],
    )
    await SituationRepository(db).insert(state)
    goal = AutonomousGoal(
        id=goal_id_for(OWNER, SID), owner_id=OWNER, status="active",
        objective="Verificare una condizione meteo, senza simulare uno stato fisico",
        desired_outcome="Un controllo reale documentato, non una previsione inventata",
        source_kind="situation_followup", source_refs=[f"situation:{SID}"],
        source_situation={
            "situation_id": SID, "situation_revision": "1",
            "checkpoint_read_capability": capability,
            "checkpoint_due_at": due, "attention_started_at": start,
        },
        next_run_at=due,
    )
    service = AgentService(db)
    await service.repo.create_goal(goal)
    now_local = now.astimezone(ROME)
    suggest = AsyncMock(return_value={
        "available": True,
        "suggestions": [
            {"place_id": "synthetic-locality",
             "primary": locality, "text": locality + ", VT"},
        ],
    })
    resolve = AsyncMock(return_value={
        "available": True, "place_id": "synthetic-locality",
        "locality": locality, "address": locality + ", VT",
        "latitude": 42.255, "longitude": 11.761,
    })
    forecast = AsyncMock(return_value={
        "available": True, "provider": "synthetic-open-meteo",
        "place": locality, "timezone": "Europe/Rome",
        "utc_offset_seconds": int(now_local.utcoffset().total_seconds()),
        "observed_at": now_local.isoformat(),
        "retrieved_at": now.isoformat(),
        "condition_label": "Sereno sintetico",
        "temperature_c": 22, "humidity_pct": 64,
        "wind_kmh": 12, "precipitation_mm": 0.0,
        "hours": [], "days": [],
    })
    monkeypatch.setattr(lookup, "suggest", suggest)
    monkeypatch.setattr(lookup, "resolve", resolve)
    monkeypatch.setattr(weather, "capabilities",
                        lambda: {"available": True, "provider": "synthetic-open-meteo"})
    monkeypatch.setattr(weather, "forecast_at", forecast)
    monkeypatch.setattr(
        HomeService, "_where_they_are",
        AsyncMock(side_effect=AssertionError("Situation weather must not use device GPS")),
    )
    return db, service, goal, forecast


@pytest.mark.asyncio
async def test_explicit_real_source_executes_even_when_model_next_step_is_stalled(monkeypatch):
    db, service, goal, forecast = await setup(monkeypatch)
    monkeypatch.setattr(
        service, "_work", AsyncMock(return_value={"ok": True, "state": "in_progress"}),
    )
    monkeypatch.setattr(service, "_consider_visibility", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_legacy_event_alert_expired",
                        AsyncMock(return_value=False))
    monkeypatch.setattr(service.repo, "claim", AsyncMock(return_value=True))
    monkeypatch.setattr(service.repo, "release", AsyncMock(return_value=None))

    outcome = await service.advance(
        OWNER, goal.id, worker_id="ambient:one-synthetic-real-wake",
    )
    assert outcome["state"] == "in_progress", outcome
    # A stalled AI no longer implies zero actual source reads.
    forecast.assert_awaited_once()
    evidence = await db.agent_evidence.find(
        {"owner_id": OWNER, "goal_id": goal.id}, {"_id": 0},
    ).to_list(20)
    assert evidence
    assert all(e["provenance"]["capability"] == "weather.read" for e in evidence)
    assert any(f"situation:{SID}:revision:1" in e["provenance"]["source_refs"]
               and "google_place:synthetic-locality" in e["provenance"]["source_refs"]
               for e in evidence)
    assert "Leesburg" not in str(evidence)
    audit = await db.agent_journal.find(
        {"owner_id": OWNER, "goal_id": goal.id, "kind": "step_done"},
        {"_id": 0},
    ).to_list(10)
    assert len(audit) == 1
    assert audit[0]["detail"]["status"] == "succeeded"
    assert audit[0]["detail"]["really_happened"] is True
    assert audit[0]["detail"]["checkpoint_source"] is True
    read = await read_followup(db, OWNER, SID)
    assert read["last_checked_at"] is not None, read
    assert read["last_result_verification"] == "exact_step_geobound_evidence"
    assert read["last_result"] is not None
    activity = await db.ambient_activity.find(
        {"owner_id": OWNER}, {"_id": 0},
    ).to_list(5)
    assert len(activity) == 1
    assert activity[0]["visibility"] == "ambient"
    assert activity[0]["kind"] == "evidence_refreshed"
    assert activity[0]["cognitive_provenance"]["physical_outcome_not_observed"] is True
    assert "asciutti" not in activity[0]["summary"].lower()
    assert await db.delivery_plans.count_documents({}) == 0

    # Technical retry keeps the exact same scheduled capability and due
    # snapshot: it must NOT repeat the live provider read or create a new card.
    goal_again = await service.repo.get_goal(OWNER, goal.id)
    again = await run_due_checkpoint_source(
        service, OWNER, goal_again, budget=AgentBudget(),
    )
    assert again["state"] == "already_verified"
    forecast.assert_awaited_once()
    assert await db.ambient_activity.count_documents({"owner_id": OWNER}) == 1


@pytest.mark.asyncio
async def test_missing_capability_and_wrong_owner_do_not_read_or_notify(monkeypatch):
    db, service, goal, forecast = await setup(monkeypatch, capability="")
    result = await run_due_checkpoint_source(
        service, OWNER, goal, budget=AgentBudget(),
    )
    assert result["state"] == "no_explicit_due_source"
    forecast.assert_not_awaited()
    goal.source_situation["checkpoint_read_capability"] = "weather.read"
    result = await run_due_checkpoint_source(
        service, "other-owner", goal, budget=AgentBudget(),
    )
    assert result["state"] == "source_not_applicable"
    forecast.assert_not_awaited()
    assert await db.agent_evidence.count_documents({}) == 0
    assert await db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_wrong_locality_never_proves_a_read_for_the_named_situation(monkeypatch):
    db, service, goal, forecast = await setup(monkeypatch, locality="Tarquinia")
    from places import lookup
    monkeypatch.setattr(lookup, "resolve", AsyncMock(return_value={
        "available": True, "place_id": "synthetic-locality",
        "locality": "Leesburg", "address": "Leesburg",
        "latitude": 39.1, "longitude": -77.56,
    }))
    outcome = await run_due_checkpoint_source(
        service, OWNER, goal, budget=AgentBudget(),
    )
    assert outcome["state"] == "source_read_unavailable", outcome
    forecast.assert_not_awaited()
    assert await db.ambient_activity.count_documents({}) == 0
    assert await db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_expired_or_changed_situation_does_not_touch_provider(monkeypatch):
    db, service, goal, forecast = await setup(monkeypatch)
    await db.situations.update_one(
        {"id": SID, "user_id": OWNER},
        {"$set": {"revision": 2}},
    )
    result = await run_due_checkpoint_source(service, OWNER, goal, budget=AgentBudget())
    assert result["state"] == "source_not_current"
    forecast.assert_not_awaited()
    assert await db.agent_evidence.count_documents({}) == 0
    assert await db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_schedule_refuses_unknown_skills_and_saves_selected_weather_skill(monkeypatch):
    db, service, goal, _ = await setup(monkeypatch, capability="")
    # Explicitly scheduled callback updates the existing owned goal with
    # the person's opt-in read-only capability and exact due.
    check = (datetime.now(timezone.utc) + timedelta(minutes=12)).isoformat()
    unsafe = await arrange_followup(
        db, OWNER, situation_id=SID, expected_revision=1,
        check_at=check, purpose="Source check", notify_when="Only real risk",
        completion_when="Read the real source", read_capability="mail.send",
    )
    assert unsafe["ok"] is False
    assert unsafe["error"] == "unsupported_checkpoint_read_capability"
    # This fixture has an existing due goal but no planned provider read;
    # the schedule readback may reuse its existing due interval. What matters
    # is that unsafe capabilities never become a checkpoint read.
    assert (await service.repo.get_goal(OWNER, goal.id)).source_situation.get(
        "checkpoint_read_capability"
    ) in ("", None)


@pytest.mark.asyncio
async def test_fresh_user_checkpoint_rearms_exhausted_existing_goal_once(monkeypatch):
    db, service, goal, forecast = await setup(monkeypatch, capability="")
    goal.background_runs = 3
    goal.planning_attempts = 4
    goal.planning_unavailable = True
    goal.next_run_at = None  # an older cycle was exhausted
    await service.repo.save_goal(goal)
    at = (datetime.now(timezone.utc) + timedelta(minutes=12)).isoformat()
    result = await arrange_followup(
        db, OWNER, situation_id=SID, expected_revision=1,
        check_at=at, purpose="Read real source at this explicit check",
        notify_when="Only if new source evidence changes next action",
        completion_when="One evidence-backed next action",
        read_capability="weather.read",
    )
    assert result.get("ok") is True, result
    latest = await service.repo.get_goal(OWNER, goal.id)
    assert latest is not None
    assert latest.background_runs == 0
    assert latest.planning_attempts == 0
    assert latest.planning_unavailable is False
    assert latest.source_situation["checkpoint_read_capability"] == "weather.read"
    actual_due = latest.source_situation["checkpoint_due_at"]
    assert actual_due == latest.next_run_at
    assert datetime.fromisoformat(actual_due) > datetime.now(timezone.utc)
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}",
        "status": {"$in": ["pending", "claimed"]},
    }) == 1
    # Scheduling cannot pretend it already observed new weather or produce
    # a user-facing result before the wake actually fires.
    forecast.assert_not_awaited()
    assert await db.agent_evidence.count_documents({}) == 0
    assert await db.delivery_plans.count_documents({}) == 0

    # Asking about the *same* still-pending checkpoint reuses the due time,
    # rather than restoring the budget again or postponing it.
    latest.background_runs = 2
    await service.repo.save_goal(latest)
    repeat = await arrange_followup(
        db, OWNER, situation_id=SID, expected_revision=1,
        check_at=(datetime.now(timezone.utc)+timedelta(minutes=22)).isoformat(),
        purpose="Same checkpoint", notify_when="Only real risk",
        completion_when="One evidence-backed next action",
        read_capability="weather.read",
    )
    assert repeat.get("ok") is True and repeat.get("reused") is True, repeat
    reused = await service.repo.get_goal(OWNER, goal.id)
    assert reused.background_runs == 2
    assert reused.next_run_at == actual_due



@pytest.mark.asyncio
async def test_late_explicit_weather_opt_in_upgrades_existing_pending_wake_without_moving_it(monkeypatch):
    """Pilot regression: a real source request must not be swallowed by 'reused'."""
    db, service, goal, forecast = await setup(monkeypatch, capability="")
    goal.next_run_at = None
    await service.repo.save_goal(goal)
    first = await arrange_followup(
        db, OWNER, situation_id=SID, expected_revision=1,
        check_at=(datetime.now(timezone.utc) + timedelta(minutes=12)).isoformat(),
        purpose="Existing general checkpoint",
        notify_when="Only an actual urgent risk",
        completion_when="One useful next action",
    )
    assert first.get("ok") is True and first["status"] == "scheduled", first
    original = await service.repo.get_goal(OWNER, goal.id)
    original_due = original.next_run_at
    assert original_due
    assert not original.source_situation.get("checkpoint_read_capability")
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}",
        "status": {"$in": ["pending", "claimed"]},
    }) == 1

    # User now authorizes a real weather read, but the already promised 12m
    # checkpoint must remain the only alarm and the budget must not reset.
    original.background_runs = 2
    await service.repo.save_goal(original)
    upgraded = await arrange_followup(
        db, OWNER, situation_id=SID, expected_revision=1,
        check_at=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
        purpose="Explicitly read live weather at the existing checkpoint",
        notify_when="Only an actual urgent risk",
        completion_when="One evidence-backed next action",
        read_capability="weather.read",
    )
    assert upgraded.get("ok") is True and upgraded.get("reused") is True, upgraded
    current = await service.repo.get_goal(OWNER, goal.id)
    assert current.next_run_at == original_due
    assert current.source_situation["checkpoint_due_at"] == original_due
    assert current.source_situation["checkpoint_read_capability"] == "weather.read"
    assert current.background_runs == 2
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}",
        "status": {"$in": ["pending", "claimed"]},
    }) == 1
    forecast.assert_not_awaited()
    assert await db.agent_evidence.count_documents({}) == 0
    assert await db.delivery_plans.count_documents({}) == 0

    # A duplicate message cannot shift the same checkpoint or mint new work.
    repeated = await arrange_followup(
        db, OWNER, situation_id=SID, expected_revision=1,
        check_at=(datetime.now(timezone.utc) + timedelta(minutes=35)).isoformat(),
        purpose="Repeat the same check",
        notify_when="Only an actual urgent risk",
        completion_when="One evidence-backed next action",
        read_capability="weather.read",
    )
    assert repeated.get("ok") is True and repeated.get("reused") is True, repeated
    after = await service.repo.get_goal(OWNER, goal.id)
    assert after.next_run_at == original_due
    assert after.background_runs == 2
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal.id}",
        "status": {"$in": ["pending", "claimed"]},
    }) == 1


@pytest.mark.asyncio
async def test_home_update_shows_documented_source_instead_of_only_working(monkeypatch):
    db, service, goal, forecast = await setup(monkeypatch)
    result = await run_due_checkpoint_source(
        service, OWNER, goal, budget=AgentBudget(),
    )
    assert result["state"] == "source_verified"
    card = await service._open_card(OWNER, goal)
    assert not card.get("stale"), card
    assert card["state"] == "Fonte verificata; esito ancora da valutare", card
    assert card["has_real_activity"] is True
    assert "meteo" in card["already_done"].lower()
    assert "non ho ancora" in card["next_step"].lower()
    assert "asciutti" not in str(card).lower()
    forecast.assert_awaited_once()


@pytest.mark.asyncio
async def test_home_update_never_labels_three_exhausted_passes_as_working(monkeypatch):
    db, service, goal, forecast = await setup(monkeypatch, capability="")
    goal.background_runs = 3
    goal.next_run_at = None
    await service.repo.save_goal(goal)
    card = await service._open_card(OWNER, goal)
    assert not card.get("stale"), card
    assert card["state"] == "Controllo automatico interrotto"
    assert "senza un nuovo controllo" in card["problem"]
    assert "non sta proseguendo" in card["next_step"]
    assert card["has_real_activity"] is False
    forecast.assert_not_awaited()
