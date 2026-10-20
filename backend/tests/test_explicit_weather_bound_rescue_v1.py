"""Test 5C: exact user weather command survives an AI skill-plan step bound.

Uses the actual Situation/Agent/Ambient stores (synthetic Mongo only).
There is no real weather call, external notification, or real account mutation.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.models import ConversationSession
from situations.explicit_weather_recovery import recover_explicit_weather_schedule
from situations.followup import read_followup, arrange_followup
from situations.models import SituationEvent, SituationState
from situations.repository import SituationRepository

OWNER = "pilot_weather_rescue"
SID = "sit_131c2d203aaf4889"


async def fixture(monkeypatch, *, owner=OWNER, label="Tarquinia"):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().pilot_weather_rescue
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index("identity", unique=True)
    now = datetime.now(timezone.utc)
    state = SituationState(
        id=SID, user_id=owner, location_label=label,
        summary="Nuovo carico di panni steso a Tarquinia (simulazione di test)",
        started_at=now.isoformat(),
        attention_intent="Valutare il momento utile per ritirare i panni",
        history=[SituationEvent(
            revision=1, operation="create", source="user_conversation",
            changes={"location_label": label},
            source_refs=["user_conversation"],
        )],
    )
    await SituationRepository(db).insert(state)
    return db, now


def user_command(*, sid=SID, when="fra 5 minuti", date=""):
    return (
        f"ORA, riprendi esclusivamente la Situazione {sid} relativa "
        f"ai panni stesi a Tarquinia {date}. Non crearne una nuova. "
        f"Programma {when} un controllo reale del meteo a Tarquinia, "
        "utilizzando weather.read. Verifica il controllo salvato "
        "e comunicami l'orario italiano."
    )


@pytest.mark.asyncio
async def test_model_bound_recovers_exact_schedule_and_real_checkpoint_capability(monkeypatch):
    db, _ = await fixture(monkeypatch)
    session = ConversationSession(
        user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}},
    )
    calls = []

    async def indecisive_model(system, payload):
        calls.append(payload)
        return {
            "response_mode": "answer",
            "reasoning_status": "enough_information",
            "user_intent_summary": "Fissare il controllo meteo esplicito",
            "message_to_user": "Ok.",
            "skill_plan": {
                "objective": "Programmare il controllo reale",
                "required_capabilities": ["schedule_situation_check"],
            },
        }

    result = await run_cognitive_loop(
        sess=session, db=db, user_message=user_command(),
        decision_fn=indecisive_model, max_steps=3,
    )
    assert result.ok is True
    assert len(calls) == 3
    assert result.tool_calls == 1
    assert "Ho programmato e verificato un controllo" in result.ora_text
    assert SID in result.ora_text
    assert "weather.read" in result.ora_text
    assert "meteo non è stato ancora letto" in result.ora_text
    state = await read_followup(db, OWNER, SID)
    assert state["status"] == "scheduled", state
    assert state["next_check_at"] and state["last_checked_at"] is None
    assert state["next_check_label"] in result.ora_text
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "status": {"$in": ["pending", "claimed"]},
    }) == 1
    goals = await db.agent_goals.find(
        {"owner_id": OWNER}, {"_id": 0},
    ).to_list(10)
    assert len(goals) == 1
    assert goals[0]["source_situation"]["checkpoint_read_capability"] == "weather.read"
    assert goals[0]["source_situation"]["checkpoint_due_at"] == state["next_check_at"]
    assert await db.agent_evidence.count_documents({}) == 0
    assert await db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_exact_weather_command_reuses_existing_check_without_second_wake(monkeypatch):
    db, _ = await fixture(monkeypatch)
    first = await arrange_followup(
        db, OWNER, situation_id=SID, expected_revision=1,
        check_at=(datetime.now(timezone.utc) + timedelta(minutes=12)).isoformat(),
        purpose="Controllo generico già programmato",
        completion_when="Capire il prossimo passo utile",
        notify_when="Un rischio urgente",
    )
    assert first.get("ok")
    original_due = first["next_check_at"]
    repaired = await recover_explicit_weather_schedule(
        db, OWNER, user_command(), model_selected_capability=True,
    )
    assert repaired and repaired["ok"], repaired
    assert original_due in repaired["observation"].payload["next_check_at"]
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "status": {"$in": ["pending", "claimed"]},
    }) == 1
    assert await db.agent_evidence.count_documents({}) == 0


@pytest.mark.asyncio
async def test_no_weather_rescue_on_mismatched_date_place_or_foreign_owner(monkeypatch):
    db, _ = await fixture(monkeypatch)
    wrong_date = await recover_explicit_weather_schedule(
        db, OWNER, user_command(date="il 19 ottobre 2024"),
        model_selected_capability=True,
    )
    assert wrong_date and not wrong_date["ok"]
    assert "data originale" in wrong_date["text"]

    wrong_place = await recover_explicit_weather_schedule(
        db, OWNER,
        user_command().replace("a Tarquinia", "a Viterbo")
                      .replace("stesi a Tarquinia", "stesi a Viterbo"),
        model_selected_capability=True,
    )
    assert wrong_place and not wrong_place["ok"]

    foreign = await recover_explicit_weather_schedule(
        db, "foreign_user", user_command(), model_selected_capability=True,
    )
    assert foreign and not foreign["ok"]

    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_no_weather_rescue_on_status_negation_ambiguous_id_or_unselected_skill(monkeypatch):
    db, _ = await fixture(monkeypatch)
    variants = [
        f"Come è andato il controllo di {SID}? Non programmare nulla.",
        f"Non programmare un controllo meteo fra 5 minuti per {SID} a Tarquinia",
        user_command() + " " + user_command(sid="sit_aaaaaaaaaaaaaaaa"),
        f"Programma fra 5 minuti un controllo meteo a Tarquinia",  # no ID
    ]
    for msg in variants:
        assert await recover_explicit_weather_schedule(
            db, OWNER, msg, model_selected_capability=True,
        ) is None
    assert await recover_explicit_weather_schedule(
        db, OWNER, user_command(), model_selected_capability=False,
    ) is None
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0
