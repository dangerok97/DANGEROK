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
async def test_successfully_saved_checkpoint_survives_unrelated_unseen_plan_step(monkeypatch):
    """A real schedule must not disappear behind generic partial-plan copy."""
    db, _ = await fixture(monkeypatch)
    session = ConversationSession(user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}})
    due = (datetime.now(timezone.utc) + timedelta(minutes=8)).isoformat()
    model_calls = 0

    async def model(system, payload):
        nonlocal model_calls
        model_calls += 1
        planned = {
            "objective": "Programmare, poi leggere una fonte sul risultato",
            "required_capabilities": [
                "schedule_situation_check", "get_weather_forecast",
            ],
        }
        if model_calls == 1:
            return {
                "response_mode": "tool",
                "reasoning_status": "needs_tool",
                "skill_plan": planned,
                "tool_call": {
                    "capability": "schedule_situation_check",
                    "arguments": {
                        "situation_id": SID, "expected_revision": 1,
                        "check_at": due,
                        "purpose": "One actual checkpoint at requested time",
                        "completion_when": "A source-backed next action",
                        "notify_when": "Only an urgent risk",
                        "read_capability": "weather.read",
                    },
                },
            }
        return {
            "response_mode": "answer",
            "reasoning_status": "enough_information",
            "message_to_user": "Fatto.",
            "skill_plan": planned,
        }

    result = await run_cognitive_loop(
        sess=session, user_message=user_command(), db=db,
        decision_fn=model, max_steps=3,
    )
    assert result.ok
    assert result.tool_calls == 1, result
    state = await read_followup(db, OWNER, SID)
    assert state["status"] == "scheduled", state
    assert state["next_check_label"] in result.ora_text
    assert "Altri passaggi" in result.ora_text
    assert "non risultano confermati" in result.ora_text
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "status": {"$in": ["pending", "claimed"]},
    }) == 1
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


@pytest.mark.asyncio
async def test_natural_laundry_request_lets_ai_choose_relative_checkpoint_no_iso(monkeypatch):
    """No technical clock data in the person's words; model picks interval."""
    from situations.followup import schedule_situation_check
    db, _ = await fixture(monkeypatch)
    before = datetime.now(timezone.utc)
    answer = await schedule_situation_check({
        "situation_id": SID,
        "expected_revision": 1,
        "delay_minutes": 35,
        "purpose": "Rivedere le condizioni esterne per decidere quando ritirare i panni.",
        "completion_when": "Dare una stima utile del momento di ritiro.",
        "notify_when": "Segnalare un rischio meteo imminente.",
        "read_capability": "weather.read",
    }, {"db": db, "user_id": OWNER,
        "user_message": "Ho steso i panni a Tarquinia."})
    assert answer.status == "ok", answer.payload
    state = await read_followup(db, OWNER, SID)
    assert state["status"] == "scheduled"
    due = datetime.fromisoformat(state["next_check_at"].replace("Z", "+00:00"))
    assert timedelta(minutes=34) <= due - before <= timedelta(minutes=36)
    assert state["last_checked_at"] is None
    assert state["next_check_label"]
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "status": "pending",
    }) == 1
    goal = await db.agent_goals.find_one({"owner_id": OWNER}, {"_id": 0})
    assert goal["source_situation"]["checkpoint_read_capability"] == "weather.read"
    assert await db.agent_evidence.count_documents({}) == 0
    assert await db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_malformed_iso_recovers_explicit_five_minute_instruction(monkeypatch):
    """This is the real 21 Oct error: model called schedule with a wall clock."""
    from situations.followup import schedule_situation_check
    db, _ = await fixture(monkeypatch)
    before = datetime.now(timezone.utc)
    answer = await schedule_situation_check({
        "situation_id": SID, "expected_revision": 1,
        "check_at": "21 ottobre alle 09:05",  # not ISO with timezone
        "purpose": "Rileggere il meteo alla prossima verifica.",
        "completion_when": "Capire quando è consigliabile ritirare i panni.",
        "notify_when": "Rischio di pioggia prima dell'asciugatura.",
        "read_capability": "weather.read",
    }, {"db": db, "user_id": OWNER,
        "user_message": (
            f"ORA, programma fra 5 minuti un controllo meteo a Tarquinia "
            f"per la Situazione {SID}."
        )})
    assert answer.status == "ok", answer.payload
    state = await read_followup(db, OWNER, SID)
    assert state["status"] == "scheduled"
    due = datetime.fromisoformat(state["next_check_at"].replace("Z", "+00:00"))
    assert timedelta(minutes=3) <= due - before <= timedelta(minutes=6)
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "status": "pending",
    }) == 1
    assert await db.agent_evidence.count_documents({}) == 0


@pytest.mark.asyncio
async def test_ambiguous_or_negated_relative_time_does_not_schedule(monkeypatch):
    from situations.followup import schedule_situation_check
    db, _ = await fixture(monkeypatch)
    arguments = {
        "situation_id": SID, "expected_revision": 1,
        "check_at": "alle nove e dieci",
        "purpose": "Un controllo",
        "completion_when": "Una stima",
        "notify_when": "Un rischio",
        "read_capability": "weather.read",
    }
    for words in (
        "Non programmare fra 5 minuti un controllo meteo.",
        "Programma fra 5 minuti e fra 10 minuti un controllo meteo.",
        "Controlla il meteo, nessun orario indicato.",
    ):
        result = await schedule_situation_check(arguments, {
            "db": db, "user_id": OWNER, "user_message": words,
        })
        assert result.status == "error"
        assert result.payload.get("error") == "timezone_aware_checkpoint_within_72h_required"
    assert await db.ambient_wakes.count_documents({}) == 0
    assert await db.agent_goals.count_documents({}) == 0


@pytest.mark.asyncio
async def test_bad_model_delay_fails_closed_even_if_it_could_guess_from_prose(monkeypatch):
    from situations.followup import schedule_situation_check
    db, _ = await fixture(monkeypatch)
    response = await schedule_situation_check({
        "situation_id": SID, "expected_revision": 1,
        "delay_minutes": 0, "check_at": "tomorrow maybe",
        "purpose": "Verifica", "completion_when": "Consiglio",
        "notify_when": "Rischio",
        "read_capability": "weather.read",
    }, {"db": db, "user_id": OWNER,
        "user_message": "Programma fra 5 minuti un controllo meteo."})
    assert response.status == "error"
    assert await db.ambient_wakes.count_documents({}) == 0
