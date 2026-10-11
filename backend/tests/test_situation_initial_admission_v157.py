"""v157: a temporary Situation requiring attention gets a durable INITIAL REVIEW.

This is not a provider observation, weather prediction or promised alert.
All tests use owned synthetic Mongo and no external-world action.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionPlan, AgentEvidence, AgentRun, ResultProvenance
from agent.service import AgentService
from ambient.eligibility import EligibilityService
from opportunities.discovery import OpportunityDiscovery
from situations.followup import (
    KIND, INITIAL_KIND, arrange_followup, read_followup, goal_id_for,
)
from situations.models import SituationUpdate
from situations.service import SituationService

OWNER = "initial-review-owner"


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    # Situation change always submits a normal opportunity signal as well.
    # Isolate that accelerator to test the new direct Agent admission.
    monkeypatch.setattr(OpportunityDiscovery, "note", AsyncMock(return_value={
        "outcome": "accepted",
    }))
    db = AsyncMongoMockClient().situation_initial_review_v157
    return db


async def indices(db):
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index(
        "identity", unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "claimed"]}},
    )


async def create(db, *, owner=OWNER, attention=True, epoch="initial-001"):
    result = await SituationService(db).apply(
        user_id=owner, session_id="ces_fixture",
        reasoning_epoch=epoch,
        update=SituationUpdate(
            operation="create", summary="Oggetto all'aperto con esito da attendere",
            semantic_kind="stato temporaneo",
            attention_intent=(
                "Controllare le condizioni esterne e comunicare il momento utile."
                if attention else None
            ),
            next_check_summary=(
                "Rivalutare la situazione con dati verificabili"
                if attention else None
            ),
            expected_outcome_summary="Sapere quando intervenire",
            source="user_conversation",
        ),
    )
    return result["situation"]["id"]


@pytest.mark.asyncio
async def test_persisted_attention_creates_one_review_not_a_fake_weather_check(setup):
    db = setup
    await indices(db)
    sid = await create(db)
    gid = goal_id_for(OWNER, sid)
    goal = await db.agent_goals.find_one({"id": gid, "owner_id": OWNER}, {"_id": 0})
    assert goal is not None and goal["source_kind"] == INITIAL_KIND
    assert goal["status"] == "active"
    assert goal["decision_provenance"] == "model"
    wake = await db.ambient_wakes.find_one({
        "owner_id": OWNER, "source_ref": f"goal:{gid}", "status": "pending",
    }, {"_id": 0})
    assert wake and wake["reason"] == "opportunity_revisit"

    state = await read_followup(db, OWNER, sid)
    assert state["status"] == "review_pending", state
    assert state["goal_id"] == gid
    assert state["assessment_at"] is not None
    assert state["next_check_at"] is None, "initial assessment is NOT an actual monitoring checkpoint"
    assert "non ha ancora fissato un controllo" in state["diagnosis"]
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1

    # Replaying the same decision must NOT move the first wake or fork a goal.
    replayed = await SituationService(db).apply(
        user_id=OWNER, session_id="ces_fixture",
        reasoning_epoch="initial-001",
        update=SituationUpdate(operation="create", summary="Oggetto all'aperto con esito da attendere"),
    )
    assert replayed["deduped"] is True
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert await db.ambient_wakes.count_documents({"owner_id": OWNER, "status": "pending"}) == 1
    assert (await read_followup(db, "unrelated-owner", sid))["status"] == "unavailable"


@pytest.mark.asyncio
async def test_model_selected_checkpoint_promotes_initial_review_without_duplicates(setup):
    db = setup
    await indices(db)
    sid = await create(db)
    before = await read_followup(db, OWNER, sid)
    due = (datetime.now(timezone.utc) + timedelta(minutes=32)).isoformat()
    scheduled = await arrange_followup(
        db, OWNER, situation_id=sid, expected_revision=1,
        check_at=due,
        purpose="Rileggere nuove condizioni verificabili.",
        notify_when="Un rischio concreto richiede intervento anticipato.",
        completion_when="Quando è giustificato concludere il monitoraggio.",
    )
    assert scheduled["status"] == "scheduled", scheduled
    assert scheduled["next_check_at"] == due
    assert (await db.agent_goals.find_one({"id": before["goal_id"]}))["source_kind"] == KIND
    opened = await db.ambient_wakes.find({
        "owner_id": OWNER, "status": {"$in": ["pending", "claimed"]},
    }).to_list(10)
    assert len(opened) == 1
    assert opened[0]["source_ref"] == f"goal:{before['goal_id']}"
    assert opened[0]["scheduled_for"] == due
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1


@pytest.mark.asyncio
async def test_agent_wait_promotes_only_when_it_has_chosen_recheck(setup, monkeypatch):
    db = setup
    await indices(db)
    sid = await create(db)
    gid = goal_id_for(OWNER, sid)
    service = AgentService(db)
    goal = await service.repo.get_goal(OWNER, gid)
    assert goal and goal.source_kind == INITIAL_KIND
    plan = ActionPlan(owner_id=OWNER, goal_id=gid, status="active", steps=[])
    run = AgentRun(owner_id=OWNER, goal_id=gid, background=True)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())
    await service.evidence.record(AgentEvidence(
        owner_id=OWNER, goal_id=gid, claim="La fonte di prova indica condizioni da ricontrollare.",
        provenance=ResultProvenance(source_class="connected_provider", capability="weather.read",
                                    source_refs=["weather:synthetic-source"], freshness="fresh"),
    ))
    out = await service._wait(
        OWNER, goal, plan, None, run, minutes=20,
        note="Riesame scelto dopo aver consultato fonti pertinenti",
        model_decision=True,
    )
    assert out["state"] == "waiting", out
    assert (await service.repo.get_goal(OWNER, gid)).source_kind == KIND
    assert (await read_followup(db, OWNER, sid))["status"] == "scheduled"
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1


@pytest.mark.asyncio
async def test_resolving_one_situation_cancels_its_initial_wake_without_harming_another(setup):
    db = setup
    await indices(db)
    sid = await create(db, epoch="first")
    other_sid = await create(db, epoch="second")
    out = await SituationService(db).apply(
        user_id=OWNER, session_id="ces_fixture", reasoning_epoch="closed-1",
        update=SituationUpdate(operation="cancel", situation_id=sid, expected_revision=1),
    )
    assert out["status"] == "success"
    own = await db.agent_goals.find_one({"id": goal_id_for(OWNER, sid)})
    another = await db.agent_goals.find_one({"id": goal_id_for(OWNER, other_sid)})
    assert own["status"] == "cancelled"
    assert another["status"] == "active"
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal_id_for(OWNER, sid)}",
        "status": {"$in": ["pending", "claimed"]},
    }) == 0
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal_id_for(OWNER, other_sid)}",
        "status": "pending",
    }) == 1


@pytest.mark.asyncio
async def test_disabled_runtime_or_non_monitorable_state_never_claims_active_watch(setup, monkeypatch):
    db = setup
    await indices(db)
    monkeypatch.setenv("AMBIENT_RUNTIME", "0")
    sid = await create(db, epoch="runtime-off")
    assert (await read_followup(db, OWNER, sid))["status"] == "not_scheduled"
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    other_sid = await create(db, attention=False, epoch="no-attention")
    assert (await read_followup(db, OWNER, other_sid))["status"] == "not_scheduled"
    assert await db.agent_goals.count_documents({}) == 0


@pytest.mark.asyncio
async def test_initial_wake_lost_is_recovered_without_inventing_a_new_time(setup):
    db = setup
    await indices(db)
    sid = await create(db)
    gid = goal_id_for(OWNER, sid)
    original = await db.agent_goals.find_one({"id": gid}, {"_id": 0})
    await db.ambient_wakes.update_one(
        {"owner_id": OWNER, "source_ref": f"goal:{gid}", "status": "pending"},
        {"$set": {"status": "failed", "last_error": "synthetic_outage"}},
    )
    after = await read_followup(db, OWNER, sid)
    assert after["status"] == "recovery_pending", after
    assert "situation_unattended" in await EligibilityService(db).reasons_to_look_again(OWNER)
    from situations.followup import repair_missing_dedicated_wakes
    result = await repair_missing_dedicated_wakes(db, OWNER)
    assert result["repaired"] == 1
    again = await read_followup(db, OWNER, sid)
    assert again["status"] == "review_pending", again
    assert await db.agent_goals.count_documents({}) == 1
    goal = await db.agent_goals.find_one({"id": gid})
    assert goal["source_kind"] == INITIAL_KIND
    assert goal["next_run_at"] == original["next_run_at"] or goal["next_run_at"]


@pytest.mark.asyncio
async def test_old_unadmitted_attention_is_admitted_once_on_fallback_sweep(setup):
    db = setup
    await indices(db)
    from situations.models import SituationState
    from situations.repository import SituationRepository
    from situations.admission import recover_unadmitted_attention

    sid = "sit_old_active_unattended"
    await SituationRepository(db).insert(SituationState(
        id=sid, user_id=OWNER, summary="Stato aperto già conosciuto",
        attention_intent="Verificare se serve intervenire più tardi",
        next_check_summary="Rileggere una fonte pertinente",
    ))
    assert await db.agent_goals.count_documents({}) == 0
    out = await recover_unadmitted_attention(db, OWNER)
    assert out["queued"] == 1
    second = await recover_unadmitted_attention(db, OWNER)
    assert second["queued"] == 0
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert (await read_followup(db, OWNER, sid))["status"] == "review_pending"
    assert await db.agent_goals.count_documents({"owner_id": "other_owner"}) == 0


@pytest.mark.asyncio
async def test_unattended_intent_recovers_after_an_unrelated_recent_fallback(setup, monkeypatch):
    db = setup
    await indices(db)
    from ambient import eligibility
    from situations.models import SituationState
    from situations.repository import SituationRepository

    monkeypatch.setattr(eligibility, "PER_USER_INTERVAL_HOURS", 12)
    monkeypatch.setattr(eligibility, "URGENT_FALLBACK_INTERVAL_HOURS", 0.5)
    now = datetime.now(timezone.utc)
    await SituationRepository(db).insert(SituationState(
        id="sit_unadmitted_after_other_review", user_id=OWNER,
        summary="Situazione sintetica ancora aperta",
        attention_intent="Verificare quando serve intervenire",
    ))
    await db.ambient_fallback_state.insert_one({
        "owner_id": OWNER,
        "last_checked_at": (now - timedelta(hours=3)).isoformat(),
        "last_reasons": ["delivery_pending"],
    })
    service = EligibilityService(db)
    await service.ensure_indexes()
    assert await service.reasons_to_look_again(OWNER) == ["situation_unattended"]
    assert await db.agent_goals.count_documents({}) == 0

    out = await service.sweep(now=now)

    assert out["scheduled"] == 1 and out["skipped"] == 0, out
    wakes = await db.ambient_wakes.find({"owner_id": OWNER}).to_list(10)
    assert len(wakes) == 1
    assert wakes[0]["reason"] == "ambient_review"
    assert wakes[0]["source_ref"] == "situation_unattended"
    assert wakes[0]["status"] == "pending"
    assert await db.agent_goals.count_documents({}) == 0, "the existing review owns admission"
    assert await service._due_for_fallback(
        OWNER, now + timedelta(minutes=20), reasons=["situation_unattended"],
    ) is False, "urgent recovery still has a per-person throttle"


@pytest.mark.asyncio
@pytest.mark.parametrize("attention,checkpoint", [(None, None), ("", ""), ("  ", "\n")])
async def test_expected_outcome_without_attention_does_not_trigger_recovery_sweep(setup, attention, checkpoint):
    db = setup
    await indices(db)
    from situations.admission import ensure_initial_review, recover_unadmitted_attention
    from situations.models import SituationState
    from situations.repository import SituationRepository

    now = datetime.now(timezone.utc)
    await SituationRepository(db).insert(SituationState(
        id="sit_outcome_without_attention", user_id=OWNER,
        summary="Stato sintetico senza richiesta di monitoraggio",
        expected_outcome_summary="Sapere come finisce",
        attention_intent=attention, next_check_summary=checkpoint,
    ))
    await db.ambient_fallback_state.insert_one({
        "owner_id": OWNER,
        "last_checked_at": (now - timedelta(hours=3)).isoformat(),
        "last_reasons": ["delivery_pending"],
    })
    service = EligibilityService(db)
    await service.ensure_indexes()
    assert await service.reasons_to_look_again(OWNER) == []
    assert await service._candidates(now, 200) == []

    out = await service.sweep(now=now)

    assert out["scheduled"] == 0 and out["eligible"] == 0, out
    assert (await ensure_initial_review(db, OWNER, "sit_outcome_without_attention"))["status"] == "no_attention"
    assert await recover_unadmitted_attention(db, OWNER) == {"queued": 0}
    assert await db.ambient_wakes.count_documents({}) == 0
    assert await db.agent_goals.count_documents({}) == 0


@pytest.mark.asyncio
async def test_ordinary_fallback_keeps_its_twelve_hour_cooldown(setup, monkeypatch):
    db = setup
    await indices(db)
    from ambient import eligibility

    monkeypatch.setattr(eligibility, "PER_USER_INTERVAL_HOURS", 12)
    now = datetime.now(timezone.utc)
    previous = now - timedelta(hours=3)
    await db.delivery_plans.insert_one({"id": "plan_synthetic", "owner_id": OWNER, "status": "pending"})
    await db.ambient_fallback_state.insert_one({
        "owner_id": OWNER, "last_checked_at": previous.isoformat(),
        "last_reasons": ["delivery_pending"],
    })
    service = EligibilityService(db)
    await service.ensure_indexes()
    assert await service.reasons_to_look_again(OWNER) == ["delivery_pending"]

    recent = await service.sweep(now=now)
    assert recent["scheduled"] == 0 and recent["skipped"] == 1, recent
    assert await db.ambient_wakes.count_documents({}) == 0

    due = await service.sweep(now=previous + timedelta(hours=12))
    assert due["scheduled"] == 1 and due["skipped"] == 0, due
    wake = await db.ambient_wakes.find_one({"owner_id": OWNER})
    assert wake["reason"] == "ambient_review"
    assert wake["source_ref"] == "delivery_pending"


@pytest.mark.asyncio
async def test_withdrawing_attention_stops_initial_goal_and_prevents_recovery(setup):
    db = setup
    await indices(db)
    sid = await create(db)
    gid = goal_id_for(OWNER, sid)
    result = await SituationService(db).apply(
        user_id=OWNER, session_id="ces_fixture", reasoning_epoch="explicit-no-monitor",
        update=SituationUpdate(
            operation="update", situation_id=sid, expected_revision=1,
            attention_intent="", next_check_summary="",
            source="user_conversation",
        ),
    )
    assert result["status"] == "success"
    situation = await db.situations.find_one({"id": sid, "user_id": OWNER})
    assert situation.get("attention_intent") is None
    assert situation.get("next_check_summary") is None
    goal = await db.agent_goals.find_one({"id": gid, "owner_id": OWNER})
    assert goal["status"] == "cancelled"
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{gid}",
        "status": {"$in": ["pending", "claimed"]},
    }) == 0
    assert "situation_unattended" not in (
        await EligibilityService(db).reasons_to_look_again(OWNER)
    )
    from situations.admission import recover_unadmitted_attention
    assert (await recover_unadmitted_attention(db, OWNER))["queued"] == 0
