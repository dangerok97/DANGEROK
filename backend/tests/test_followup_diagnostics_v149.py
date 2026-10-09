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
    assert (await read_followup(db, OWNER, SID))["status"] == "recovery_pending"
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
