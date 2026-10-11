"""Admission survives concurrent delivery, cancellation and renewed attention."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionPlan, AutonomousGoal
from agent.repository import AgentRepository
from agent.service import AgentService
from ambient.repository import AmbientRepository
from ambient.service import AmbientService
from opportunities.discovery import OpportunityDiscovery
from situations.admission import ensure_initial_review
from situations.followup import (
    INITIAL_KIND, KIND, arrange_followup, attention_withdrawal_confirmed,
    cancel_dedicated_followup, goal_id_for, read_followup,
)
from situations.models import SituationEvent, SituationState, SituationUpdate
from situations.repository import SituationRepository
from situations.service import SituationService

OWNER = "admission-integrity-owner"
SID = "sit_admission_integrity"


async def world(monkeypatch, *, attention=True):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setattr(OpportunityDiscovery, "note", AsyncMock(return_value={"outcome": "accepted"}))
    db = AsyncMongoMockClient().admission_integrity
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index(
        "identity", unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "claimed"]}},
    )
    state = SituationState(
        id=SID, user_id=OWNER, summary="Situazione con un esito da verificare",
        attention_intent="Rileggere le fonti al momento utile" if attention else None,
        next_check_summary="Verificare se serve intervenire" if attention else None,
        history=[SituationEvent(
            revision=1, operation="create", source="user_conversation",
            changes={"attention_intent": "Rileggere le fonti"} if attention else {},
        )],
    )
    await SituationRepository(db).insert(state)
    return db


async def revoke(db):
    await db.situations.update_one(
        {"user_id": OWNER, "id": SID},
        {"$set": {"attention_intent": None, "next_check_summary": None,
                  "status": "changed"}, "$inc": {"revision": 1}},
    )


def check_args():
    return {
        "situation_id": SID, "expected_revision": 1,
        "check_at": (datetime.now(timezone.utc) + timedelta(minutes=32)).isoformat(),
        "purpose": "Rileggere le condizioni verificate alla prossima variazione utile",
        "completion_when": "Comunicare quando le fonti giustificano l'intervento",
        "notify_when": "Un rischio documentato richiede di agire prima",
    }


@pytest.mark.asyncio
async def test_parallel_admission_has_one_durable_goal_and_one_executable_review(monkeypatch):
    db = await world(monkeypatch)
    outcomes = await asyncio.gather(*[ensure_initial_review(db, OWNER, SID) for _ in range(3)])
    assert any(out["status"] == "review_queued" for out in outcomes)
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert await db.ambient_wakes.count_documents({"owner_id": OWNER, "status": "pending"}) == 1
    state = await read_followup(db, OWNER, SID)
    assert state["status"] == "review_pending"
    assert state["next_check_at"] is None
    goal = await AgentRepository(db).get_goal(OWNER, state["goal_id"])
    assert goal.source_situation["situation_revision"] == "1"
    assert goal.source_situation["attention_expected"] == "true"
    assert goal.next_run_at == state["assessment_at"]


@pytest.mark.asyncio
async def test_revocation_that_finishes_before_goal_insert_cannot_resurrect_work(monkeypatch):
    db = await world(monkeypatch)
    original = AgentRepository.create_goal

    async def racing_insert(self, goal):
        await revoke(db)
        await cancel_dedicated_followup(db, OWNER, SID)
        return await original(self, goal)

    monkeypatch.setattr(AgentRepository, "create_goal", racing_insert)
    out = await ensure_initial_review(db, OWNER, SID)
    assert out["status"] == "no_attention"
    assert await attention_withdrawal_confirmed(db, OWNER, SID)
    assert await db.ambient_wakes.count_documents({"status": {"$in": ["pending", "claimed"]}}) == 0


@pytest.mark.asyncio
async def test_revocation_while_wake_is_being_persisted_is_cleaned_up(monkeypatch):
    db = await world(monkeypatch)
    original = AmbientService.schedule

    async def racing_schedule(self, *args, **kwargs):
        wake = await original(self, *args, **kwargs)
        await revoke(db)
        return wake

    monkeypatch.setattr(AmbientService, "schedule", racing_schedule)
    out = await ensure_initial_review(db, OWNER, SID)
    assert out["status"] == "no_attention"
    assert await attention_withdrawal_confirmed(db, OWNER, SID)


@pytest.mark.asyncio
async def test_generic_goal_without_any_continuation_is_not_stolen_or_an_admission_blocker(monkeypatch):
    db = await world(monkeypatch)
    generic = AutonomousGoal(
        id="generic-owned-work", owner_id=OWNER, status="active",
        objective="Altro lavoro collegato", desired_outcome="Valutare un altro aspetto",
        source_kind="opportunity", source_refs=[f"situation:{SID}"],
    )
    await AgentRepository(db).create_goal(generic)
    before = await db.agent_goals.find_one({"id": generic.id})
    out = await ensure_initial_review(db, OWNER, SID)
    assert out["status"] == "review_queued"
    assert out["goal_id"] == goal_id_for(OWNER, SID)
    assert await db.agent_goals.find_one({"id": generic.id}) == before
    result = await arrange_followup(db, OWNER, **check_args())
    assert result["status"] == "scheduled"
    assert result["goal_id"] == goal_id_for(OWNER, SID)
    assert await db.agent_goals.find_one({"id": generic.id}) == before


@pytest.mark.asyncio
async def test_existing_executable_generic_work_is_preserved_without_claiming_a_monitor(monkeypatch):
    db = await world(monkeypatch)
    due = datetime.now(timezone.utc) + timedelta(minutes=20)
    generic = AutonomousGoal(
        id="generic-with-check", owner_id=OWNER, status="waiting",
        objective="Lavoro collegato già eseguibile", desired_outcome="Esito indipendente",
        source_kind="opportunity", source_refs=[f"situation:{SID}"], next_run_at=due.isoformat(),
    )
    await AgentRepository(db).create_goal(generic)
    await AmbientService(db).schedule(
        OWNER, reason="opportunity_revisit", when=due, source_ref=f"goal:{generic.id}",
    )
    out = await ensure_initial_review(db, OWNER, SID)
    assert out["status"] == "already_pursuing"
    assert await db.agent_goals.count_documents({}) == 1
    requested = await arrange_followup(db, OWNER, **check_args())
    assert requested["ok"] is False
    assert requested["error"] == "legacy_goal_pursuing"
    assert await db.agent_goals.count_documents({}) == 1


@pytest.mark.asyncio
async def test_typed_legacy_watch_is_reused_and_its_wakes_can_be_withdrawn(monkeypatch):
    db = await world(monkeypatch)
    legacy = AutonomousGoal(
        id="legacy-situation-watch", owner_id=OWNER, status="active",
        objective="Rivedere la situazione", desired_outcome="Un esito verificabile",
        source_kind=KIND, source_refs=[f"situation:{SID}"],
    )
    await AgentRepository(db).create_goal(legacy)
    out = await ensure_initial_review(db, OWNER, SID)
    assert out["goal_id"] == legacy.id
    assert out["status"] == "review_queued"
    assert await db.agent_goals.count_documents({}) == 1
    await revoke(db)
    assert not await attention_withdrawal_confirmed(db, OWNER, SID)
    await cancel_dedicated_followup(db, OWNER, SID)
    assert await attention_withdrawal_confirmed(db, OWNER, SID)


@pytest.mark.asyncio
async def test_stopped_goal_does_not_restart_from_the_same_stored_intent(monkeypatch):
    db = await world(monkeypatch)
    await ensure_initial_review(db, OWNER, SID)
    await AgentService(db).cancel(OWNER, goal_id_for(OWNER, SID))
    out = await ensure_initial_review(db, OWNER, SID)
    assert out["status"] == "already_stopped"
    assert await db.ambient_wakes.count_documents({"status": "pending"}) == 0


@pytest.mark.asyncio
async def test_new_explicit_attention_reuses_id_but_not_old_evidence_or_plan(monkeypatch):
    db = await world(monkeypatch)
    await ensure_initial_review(db, OWNER, SID)
    gid = goal_id_for(OWNER, SID)
    repo = AgentRepository(db)
    await repo.save_plan(ActionPlan(owner_id=OWNER, goal_id=gid, status="active", steps=[]))
    await db.agent_evidence.insert_one({"owner_id": OWNER, "goal_id": gid, "superseded": False})
    await repo.journal(OWNER, gid, kind="step_done", note="Una vecchia lettura",
                       detail={"really_happened": True, "status": "succeeded"})
    service = SituationService(db)
    await service.apply(
        user_id=OWNER, session_id="fixture", reasoning_epoch="withdraw",
        update=SituationUpdate(operation="update", situation_id=SID, expected_revision=1,
                               attention_intent="", next_check_summary=""),
    )
    assert await attention_withdrawal_confirmed(db, OWNER, SID)
    assert (await read_followup(db, OWNER, SID))["status"] == "stopped"
    await service.apply(
        user_id=OWNER, session_id="fixture", reasoning_epoch="renew",
        update=SituationUpdate(operation="update", situation_id=SID, expected_revision=2,
                               attention_intent="Riprendi a controllare le condizioni", source="user_conversation"),
    )
    current = await repo.get_goal(OWNER, gid)
    assert current.status == "active"
    assert current.source_kind == INITIAL_KIND
    assert current.source_situation["attention_epoch"] == "3"
    assert await db.agent_goals.count_documents({}) == 1
    assert await repo.plan_for(OWNER, gid) is None
    assert (await db.agent_evidence.find_one({"goal_id": gid}))["superseded"] is True
    state = await read_followup(db, OWNER, SID)
    assert state["status"] == "review_pending"
    assert state["last_checked_at"] is None


@pytest.mark.asyncio
async def test_first_checkpoint_keeps_the_chosen_purpose_outcome_and_exact_time(monkeypatch):
    db = await world(monkeypatch)
    await ensure_initial_review(db, OWNER, SID)
    args = check_args()
    result = await arrange_followup(db, OWNER, **args)
    assert result["status"] == "scheduled"
    assert result["next_check_at"] == args["check_at"]
    assert result["purpose"] == args["purpose"]
    assert result["completion_when"] == args["completion_when"]
    assert result["notify_when"] == args["notify_when"]
    assert await db.ambient_wakes.count_documents({"status": {"$in": ["pending", "claimed"]}}) == 1


@pytest.mark.asyncio
async def test_explicit_checkpoint_without_prior_attention_remains_supported(monkeypatch):
    db = await world(monkeypatch, attention=False)
    result = await arrange_followup(db, OWNER, **check_args())
    assert result["status"] == "scheduled"
    goal = await AgentRepository(db).get_goal(OWNER, result["goal_id"])
    assert goal.source_situation["attention_expected"] == "false"


@pytest.mark.asyncio
async def test_cancel_racing_with_first_checkpoint_cannot_report_scheduled(monkeypatch):
    db = await world(monkeypatch)
    await ensure_initial_review(db, OWNER, SID)
    original = AmbientService.schedule

    async def racing_schedule(self, *args, **kwargs):
        wake = await original(self, *args, **kwargs)
        await revoke(db)
        return wake

    monkeypatch.setattr(AmbientService, "schedule", racing_schedule)
    result = await arrange_followup(db, OWNER, **check_args())
    assert result["ok"] is False
    assert result["error"] == "situation_changed"
    assert await attention_withdrawal_confirmed(db, OWNER, SID)


@pytest.mark.asyncio
async def test_withdrawal_requires_job_and_wake_readback_and_keeps_other_owner_untouched(monkeypatch):
    db = await world(monkeypatch)
    await ensure_initial_review(db, OWNER, SID)
    await revoke(db)
    assert not await attention_withdrawal_confirmed(db, OWNER, SID)
    gid = goal_id_for(OWNER, SID)
    await db.agent_goals.update_one({"id": gid}, {"$set": {"status": "cancelled"}})
    assert not await attention_withdrawal_confirmed(db, OWNER, SID), "An orphan wake still exists"
    await AmbientService(db).schedule(
        "unrelated-owner", reason="opportunity_revisit",
        when=datetime.now(timezone.utc) + timedelta(minutes=5), source_ref=f"goal:{gid}",
    )
    await AmbientRepository(db).cancel_for(OWNER, source_ref=f"goal:{gid}")
    assert await attention_withdrawal_confirmed(db, OWNER, SID)
    assert not await attention_withdrawal_confirmed(db, "unrelated-owner", SID)
    assert await db.ambient_wakes.count_documents({"owner_id": "unrelated-owner", "status": "pending"}) == 1
