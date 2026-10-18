"""Regression: 'Come mai?' needs the cause of missing monitoring, not a loop.

All tests use synthetic owner-scoped Mongo; none claim live weather, physical
laundry outcome or push delivery.
"""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from ambient.eligibility import EligibilityService
from conversation_engine.ai_core.models import CognitiveDecision, ContextFact
from situations.followup import (
    arrange_followup, read_followup, schedule_situation_check,
    get_situation_followup, repair_missing_dedicated_wakes,
)
from situations.models import SituationState
from situations.repository import SituationRepository
from situations.turn_followup import FollowupTurnGate, verified_readbacks

OWNER = "followup_v149_owner"
SID = "sit_followup_v149"


async def setup(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().test
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    # Match production's partial uniqueness: a failed alarm releases its
    # identity and a new durable alarm may be created for that checkpoint.
    await db.ambient_wakes.create_index(
        "identity", unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "claimed"]}},
    )
    s = SituationState(
        id=SID, user_id=OWNER, session_id="ces_original",
        summary="Panni stesi all'aperto",
        attention_intent="Segnalare quando il meteo indica un rischio",
        next_check_summary="Verificare le condizioni quando serve",
    )
    await SituationRepository(db).insert(s)
    return db


def args(**overrides):
    payload = dict(
        situation_id=SID, expected_revision=1,
        check_at=(datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
        purpose="Rileggere le condizioni con fonti aggiornate.",
        completion_when="Quando una verifica indica un momento utile.",
        notify_when="Quando le condizioni suggeriscono di agire prima.",
    )
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_no_registered_schedule_explains_not_guesses(monkeypatch):
    db = await setup(monkeypatch)
    state = await read_followup(db, OWNER, SID)
    assert state["status"] == "not_scheduled"
    assert state["attention_saved"] is True
    assert "non risulta un controllo con data e ora" in state["diagnosis"]
    assert state.get("last_schedule_error") is None
    obs = await get_situation_followup({"situation_id": SID}, {"db": db, "user_id": OWNER})
    evidence = obs.model_dump()
    readbacks = verified_readbacks([evidence])
    assert len(readbacks) == 1
    assert readbacks[0]["ref"] == f"situation:{SID}"
    assert "non risulta un controllo" in readbacks[0]["text"]
    assert not any("asciutti" in str(v) for v in readbacks[0].values())


@pytest.mark.asyncio
@pytest.mark.parametrize("attention,checkpoint", [("", ""), ("  ", "\n")])
async def test_note_without_saved_attention_has_a_distinct_read_only_diagnosis(monkeypatch, attention, checkpoint):
    db = await setup(monkeypatch)
    await db.situations.update_one(
        {"user_id": OWNER, "id": SID},
        {"$set": {
            "attention_intent": attention,
            "next_check_summary": checkpoint,
            "expected_outcome_summary": "Nel corso della giornata",
            "tracking_summary": "Stato temporaneo annotato",
        }},
    )
    before = await db.situations.find_one({"user_id": OWNER, "id": SID})
    state = await read_followup(db, OWNER, SID)
    assert state["status"] == "not_scheduled"
    assert state["attention_saved"] is False
    assert "non una richiesta di seguirla nel tempo" in state["diagnosis"]
    assert state["next_check_at"] is None
    assert state["last_checked_at"] is None
    assert state.get("last_schedule_error") is None
    assert await db.situations.find_one({"user_id": OWNER, "id": SID}) == before
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0
    other = await read_followup(db, "other_owner", SID)
    assert other["status"] == "unavailable"
    assert other["attention_saved"] is None
    assert "non una richiesta" not in other["diagnosis"]


@pytest.mark.asyncio
async def test_failed_schedule_explains_the_actual_validation_error(monkeypatch):
    db = await setup(monkeypatch)
    invalid = args(check_at="domani pomeriggio")
    outcome = await schedule_situation_check(invalid, {"db": db, "user_id": OWNER})
    assert outcome.status == "error"
    state = await read_followup(db, OWNER, SID)
    assert state["status"] == "not_scheduled"
    assert state["last_schedule_error"] == "timezone_aware_checkpoint_within_72h_required"
    assert "orario valido con fuso" in state["diagnosis"]
    assert state.get("last_schedule_attempt_at")
    assert await db.ambient_wakes.count_documents({}) == 0
    assert await db.agent_journal.count_documents({"owner_id": OWNER, "kind": "situation_schedule_failed"}) == 1
    other = await read_followup(db, "other_owner", SID)
    assert other["status"] == "unavailable"
    assert other.get("last_schedule_error") is None


@pytest.mark.asyncio
async def test_come_mai_is_a_verifiable_status_answer_not_a_new_mission(monkeypatch):
    db = await setup(monkeypatch)
    gate = FollowupTurnGate(db, OWNER)
    await gate.refresh([ContextFact(source="situation", ref=f"situation:{SID}")])
    assert len(gate.pending) == 1
    assert "get_situation_followup" in gate.instruction()
    tool = await get_situation_followup({"situation_id": SID}, {"db": db, "user_id": OWNER})
    obs = tool.model_dump()
    decision = CognitiveDecision(
        response_mode="answer",
        message_to_user="La situazione è registrata, ma manca il checkpoint salvato.",
        situation_followup={
            "disposition": "status_only",
            "reason": "La persona domanda perché non c'è un controllo",
            "evidence_refs": [f"situation:{SID}"],
        },
    )
    assert gate.accepts_final(decision, "Come mai?", [obs])
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0
    gate = FollowupTurnGate(db, OWNER)
    await gate.refresh([ContextFact(source="situation", ref=f"situation:{SID}")])
    assert not gate.accepts_final(
        CognitiveDecision(response_mode="answer", message_to_user="Non risulta confermato"),
        "Come mai?", [],
    )
    fallback = gate.failure_text()
    assert "Panni stesi" in fallback
    assert "non risulta un controllo con data e ora" in fallback
    assert "Non sono riuscita a completarne la valutazione operativa in questo turno" not in fallback


@pytest.mark.asyncio
async def test_lost_existing_wake_is_detected_and_rearmed_without_new_deadline(monkeypatch):
    db = await setup(monkeypatch)
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    first = await arrange_followup(db, OWNER, **args(check_at=due))
    assert first["status"] == "scheduled"
    gid = first["goal_id"]
    await db.ambient_wakes.update_one(
        {"owner_id": OWNER, "source_ref": f"goal:{gid}"},
        {"$set": {"status": "failed", "last_error": "worker_retries_exhausted"}},
    )
    lost = await read_followup(db, OWNER, SID)
    assert lost["status"] == "recovery_pending"
    assert lost["goal_source_kind"] == "situation_followup"
    assert "aveva registrato un orario" in lost["diagnosis"]
    assert await EligibilityService(db)._has_unattended_situation(OWNER)
    repaired = await repair_missing_dedicated_wakes(db, OWNER)
    assert repaired["repaired"] == 1
    second = await read_followup(db, OWNER, SID)
    assert second["status"] == "scheduled"
    assert second["goal_id"] == gid
    assert second["next_check_at"] == due
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{gid}", "status": "pending",
    }) == 1
    assert (await repair_missing_dedicated_wakes(db, OWNER))["repaired"] == 0


@pytest.mark.asyncio
async def test_no_original_checkpoint_means_no_invented_recovery_alarm(monkeypatch):
    db = await setup(monkeypatch)
    await db.agent_goals.insert_one({
        "id": "goal_unplanned", "owner_id": OWNER, "status": "active",
        "source_kind": "situation_followup", "source_refs": [f"situation:{SID}"],
        "next_run_at": None,
    })
    assert await EligibilityService(db)._has_unattended_situation(OWNER)
    assert (await repair_missing_dedicated_wakes(db, OWNER))["repaired"] == 0
    assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_disabled_runtime_is_explained_without_claiming_schedule(monkeypatch):
    db = await setup(monkeypatch)
    monkeypatch.setenv("AMBIENT_RUNTIME", "0")
    state = await read_followup(db, OWNER, SID)
    assert "motore dei controlli automatici non risulta attivo" in state["diagnosis"]
    error = await schedule_situation_check(args(), {"db": db, "user_id": OWNER})
    assert error.status == "error"
    assert (await read_followup(db, OWNER, SID))["last_schedule_error"] == "runtime_disabled"
    assert await db.ambient_wakes.count_documents({}) == 0


def test_initial_review_and_actual_checkpoint_have_different_failure_diagnosis():
    """A consumed first AI wake does not imply an approved future check."""
    from situations.followup import followup_diagnosis, INITIAL_KIND, KIND
    initial = followup_diagnosis({
        "status": "recovery_pending", "goal_source_kind": INITIAL_KIND,
        "runtime_enabled": True,
    })
    dedicated = followup_diagnosis({
        "status": "recovery_pending", "goal_source_kind": KIND,
        "runtime_enabled": True,
    })
    assert "prima valutazione" in initial
    assert "monitoraggio confermato" in initial
    assert "aveva registrato un orario" not in initial
    assert "aveva registrato un orario" in dedicated
    assert followup_diagnosis({
        "status": "not_scheduled", "goal_source_kind": INITIAL_KIND,
        "runtime_enabled": True,
    }).startswith("La memoria della situazione esiste")


@pytest.mark.asyncio
async def test_new_attention_epoch_does_not_recycle_prior_schedule_failure(monkeypatch):
    from agent.models import AutonomousGoal
    from situations.followup import goal_id_for, INITIAL_KIND

    db = await setup(monkeypatch)
    now = datetime.now(timezone.utc)
    # The owner may establish a cycle in Italian local time. The journal is
    # stored in UTC; filtering ISO strings without normalising would drop
    # valid newer records in the hour overlapping the two offsets.
    cycle_start = (now - timedelta(minutes=4)).astimezone(
        timezone(timedelta(hours=2))
    ).isoformat()
    old_time = (now - timedelta(days=3)).isoformat()
    new_time = (now - timedelta(minutes=1)).isoformat()
    gid = goal_id_for(OWNER, SID)
    goal = AutonomousGoal(
        id=gid, owner_id=OWNER, status="active",
        objective="Review current Situation without assuming past schedule",
        desired_outcome="Give a grounded useful action recommendation",
        source_kind=INITIAL_KIND,
        source_refs=[f"situation:{SID}"],
        source_situation={
            "situation_id": SID, "situation_revision": "1",
            "attention_started_at": cycle_start,
        },
    )
    await db.agent_goals.insert_one(goal.model_dump())
    await db.agent_journal.insert_one({
        "owner_id": OWNER, "goal_id": gid, "kind": "situation_schedule_failed",
        "at": old_time, "detail": {
            "error_code": "timezone_aware_checkpoint_within_72h_required",
        },
    })
    state = await read_followup(db, OWNER, SID)
    assert state["status"] == "not_scheduled"
    assert state["goal_source_kind"] == INITIAL_KIND
    assert not state.get("last_schedule_error"), (
        "A failed schedule in an old cycle cannot explain the current one"
    )
    assert "Ultimo tentativo" not in state["diagnosis"]

    await db.agent_journal.insert_one({
        "owner_id": OWNER, "goal_id": gid, "kind": "situation_schedule_failed",
        "at": new_time, "detail": {
            "error_code": "bounded_purpose_and_notification_condition_required",
        },
    })
    current = await read_followup(db, OWNER, SID)
    assert current["last_schedule_error"] == (
        "bounded_purpose_and_notification_condition_required"
    )
    assert current["last_schedule_attempt_at"] == new_time
    assert current["status"] == "not_scheduled"

    # Another owner's failed time never contaminates this state.
    await db.agent_journal.insert_one({
        "owner_id": "other-person", "goal_id": gid, "kind": "situation_schedule_failed",
        "at": (now + timedelta(minutes=1)).isoformat(),
        "detail": {"error_code": "timezone_aware_checkpoint_within_72h_required"},
    })
    again = await read_followup(db, OWNER, SID)
    assert again["last_schedule_error"] == current["last_schedule_error"]
    assert (await read_followup(db, "other-person", SID))["status"] == "unavailable"

    # Once stopped, a historical failure is never a request for reactivation.
    await db.situations.update_one(
        {"user_id": OWNER, "id": SID}, {"$set": {"status": "resolved"}},
    )
    closed = await read_followup(db, OWNER, SID)
    assert closed["status"] == "stopped"
    assert closed.get("last_schedule_error") is None
    assert await db.agent_journal.count_documents({"owner_id": OWNER}) == 2


def test_review_pending_explains_current_failed_proposal_without_fake_success():
    from situations.followup import followup_diagnosis
    diagnostic = followup_diagnosis({
        "status": "review_pending", "runtime_enabled": True,
        "assessment_label": "oggi alle 15:00",
        "last_schedule_error": "timezone_aware_checkpoint_within_72h_required",
    })
    assert "non ha ancora fissato un controllo" in diagnostic
    assert "Ultima proposta di controllo rifiutata" in diagnostic
    assert "orario valido con fuso" in diagnostic
    assert "Risulta programmato un controllo" not in diagnostic
