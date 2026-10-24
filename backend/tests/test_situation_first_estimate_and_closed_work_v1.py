"""Production 23/10/2026 end-to-end probe on the owner's account.

1. "Ho appena steso i panni": the model chose a first check 180 minutes away
   with no estimate, so nothing useful could reach Aggiornamenti for hours.
2. A generic goal tied to an already cancelled laundry Situation kept asking
   for "the exact address" on Home.

Synthetic Mongo only; no provider call, notification or real account.
"""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AutonomousGoal
from agent.repository import AgentRepository
from agent.service import AgentService
from situations.followup import FIRST_ESTIMATE_MAX_MINUTES, read_followup, schedule_situation_check
from situations.models import SituationEvent, SituationState
from situations.repository import SituationRepository

OWNER = "user_first_estimate"
SID = "sit_first_estimate"


async def fixture(monkeypatch, name):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = getattr(AsyncMongoMockClient(), name)
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index("identity", unique=True)
    await SituationRepository(db).insert(SituationState(
        id=SID, user_id=OWNER, location_label="Località sintetica",
        summary="Attività sintetica all'aperto", started_at=datetime.now(timezone.utc).isoformat(),
        attention_intent="Valutare il momento utile",
        history=[SituationEvent(revision=1, operation="create", source="user_conversation",
                                changes={}, source_refs=["user_conversation"])],
    ))
    return db


async def schedule(db, minutes, message="Ho appena iniziato un'attività sintetica all'aperto."):
    return await schedule_situation_check({
        "situation_id": SID, "expected_revision": 1, "delay_minutes": minutes,
        "purpose": "Rivedere le condizioni per stimare il momento utile.",
        "completion_when": "Dare una stima utile.", "notify_when": "Segnalare un rischio imminente.",
        "read_capability": "weather.read",
    }, {"db": db, "user_id": OWNER, "user_message": message})


def minutes_until(state, before):
    due = datetime.fromisoformat(state["next_check_at"].replace("Z", "+00:00"))
    return (due - before).total_seconds() / 60


@pytest.mark.asyncio
async def test_model_chosen_far_first_check_is_capped_until_an_estimate_exists(monkeypatch):
    db = await fixture(monkeypatch, "first_cap")
    before = datetime.now(timezone.utc)
    answer = await schedule(db, 180)
    assert answer.status == "ok", answer.payload
    state = await read_followup(db, OWNER, SID)
    assert FIRST_ESTIMATE_MAX_MINUTES - 1 <= minutes_until(state, before) <= FIRST_ESTIMATE_MAX_MINUTES + 1


@pytest.mark.asyncio
async def test_without_an_estimate_even_a_short_model_interval_becomes_a_first_look(monkeypatch):
    db = await fixture(monkeypatch, "first_short")
    before = datetime.now(timezone.utc)
    assert (await schedule(db, 35)).status == "ok"
    assert minutes_until(await read_followup(db, OWNER, SID), before) <= FIRST_ESTIMATE_MAX_MINUTES + 1


@pytest.mark.asyncio
async def test_an_interval_within_the_first_look_is_kept(monkeypatch):
    db = await fixture(monkeypatch, "first_within")
    before = datetime.now(timezone.utc)
    assert (await schedule(db, 2)).status == "ok"
    assert 1 <= minutes_until(await read_followup(db, OWNER, SID), before) <= 3


@pytest.mark.asyncio
async def test_interval_stated_by_the_person_is_never_capped(monkeypatch):
    db = await fixture(monkeypatch, "first_person")
    before = datetime.now(timezone.utc)
    answer = await schedule(db, 120, message="Ricontrolla tra 120 minuti, per favore.")
    assert answer.status == "ok", answer.payload
    assert 119 <= minutes_until(await read_followup(db, OWNER, SID), before) <= 121


@pytest.mark.asyncio
async def test_work_tied_only_to_a_closed_situation_leaves_home_and_detail(monkeypatch):
    db = await fixture(monkeypatch, "closed_work")
    repo = AgentRepository(db)
    now = datetime.now(timezone.utc).isoformat()
    goal = AutonomousGoal(
        id="gol_generic_closed", owner_id=OWNER, status="waiting", origin="agent_initiated",
        objective="Ottenere un dettaglio sintetico", desired_outcome="Dettaglio sintetico",
        source_refs=[f"situation:{SID}", "q_synthetic"], requires_user_input=True,
        created_at=now, updated_at=now,
    )
    await repo.create_goal(goal)
    service = AgentService(db)
    assert await service._only_closed_situations(OWNER, goal) is False
    await db.situations.update_one({"id": SID}, {"$set": {"status": "cancelled"}})
    assert await service._only_closed_situations(OWNER, goal) is True
    assert all(card.get("id") != goal.id for card in await service.for_home(OWNER))
    assert await service.for_detail(OWNER, goal.id) is None
    # Nothing is deleted: the goal record is still there.
    assert await repo.get_goal(OWNER, goal.id) is not None


@pytest.mark.asyncio
async def test_goal_without_situation_reference_is_unaffected(monkeypatch):
    db = await fixture(monkeypatch, "no_situation_ref")
    goal = AutonomousGoal(owner_id=OWNER, objective="Lavoro senza Situazione",
                          desired_outcome="Esito sintetico", source_refs=["q_synthetic"])
    assert await AgentService(db)._only_closed_situations(OWNER, goal) is False
