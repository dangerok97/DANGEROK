"""Cross-component acceptance for a fresh everyday Situation.

A scripted cognitive decision invokes the actual tool registry, resolves the
user-named locality without device GPS, then creates the owned temporary
Situation with a durable INITIAL REVIEW wake. This is a *first-turn* test,
not just a direct SituationService or weather adapter invocation.

All inputs and provider responses are synthetic. No model, real location,
user account, push, forecast quality or physical outcome is claimed.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.models import ConversationSession
from opportunities.discovery import OpportunityDiscovery
from places import lookup
from situations.followup import INITIAL_KIND, KIND, goal_id_for, read_followup


OWNER = "synthetic-first-turn-owner"


async def setup(monkeypatch):
    import weather
    from home.service import HomeService

    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setattr(OpportunityDiscovery, "note",
                        AsyncMock(return_value={"outcome": "accepted"}))
    db = AsyncMongoMockClient().experiment_first_turn_situation
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index(
        "identity", unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "claimed"]}},
    )
    suggest = AsyncMock(return_value={
        "available": True,
        "suggestions": [{"place_id": "synthetic-town",
                         "primary": "Tarquinia",
                         "text": "Tarquinia, VT"}],
    })
    resolve = AsyncMock(return_value={
        "available": True, "place_id": "synthetic-town",
        "locality": "Tarquinia", "address": "Tarquinia, VT",
        "latitude": 42.25, "longitude": 11.76,
    })
    forecast = AsyncMock(return_value={
        "available": True, "provider": "synthetic-weather",
        "place": "Tarquinia", "observed_at": "2026-10-18T14:00:00+02:00",
        "retrieved_at": "2026-10-18T14:01:00+02:00",
        "timezone": "Europe/Rome",
        "condition_label": "Dry synthetic conditions",
        "temperature_c": 21, "humidity_pct": 58,
        "wind_kmh": 10, "precipitation_mm": 0, "hours": [],
    })
    monkeypatch.setattr(lookup, "suggest", suggest)
    monkeypatch.setattr(lookup, "resolve", resolve)
    monkeypatch.setattr(weather, "forecast_at", forecast)
    # The code-computed drying plan has its own lookup and hourly read and its
    # own tests (test_outdoor_drying_v1); here the watch's path is measured.
    from situations import outdoor_drying
    monkeypatch.setattr(outdoor_drying, "plan", AsyncMock(return_value=None))
    device = AsyncMock(side_effect=AssertionError("Do not use device GPS"))
    monkeypatch.setattr(HomeService, "_where_they_are", device)
    return db, suggest, resolve, forecast, device


@pytest.mark.asyncio
async def test_first_message_weather_then_situation_wake_is_real_and_not_fake_check(
    monkeypatch,
):
    db, suggest, resolve, forecast, device = await setup(monkeypatch)
    session = ConversationSession(
        user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}},
    )
    started = datetime.now(timezone.utc).isoformat()
    due = (datetime.now(timezone.utc) + timedelta(minutes=32)).isoformat()
    seen_initial_review = False
    calls = 0

    async def decide(system, payload):
        nonlocal calls, seen_initial_review
        calls += 1
        if calls == 1:
            return {
                "response_mode": "tool",
                "tool_call": {
                    "capability": "get_weather_forecast",
                    "arguments": {"place_query": "Tarquinia"},
                },
            }
        if calls == 2:
            assert "Tarquinia" in payload
            return {
                "response_mode": "answer",
                "message_to_user": (
                    "Ho registrato una situazione di prova. Il meteo è una "
                    "fonte iniziale; un controllo eseguibile deve essere ancora scelto."
                ),
                "situation_update": {
                    "operation": "create",
                    "source": "user_conversation",
                    "summary": "TEST: panni fittizi all'aperto",
                    "semantic_kind": "situazione temporanea",
                    "location_label": "Tarquinia",
                    "started_at": started,
                    "desired_outcome": "Sapere quando conviene intervenire",
                    "attention_intent": "Osservare nuove condizioni e decidere quando agire",
                },
            }
        if calls == 3:
            # The FollowupTurnGate rightfully rejects "I'll monitor" after
            # saving a note without a scheduled checkpoint. The same cognitive
            # turn must use the real governed scheduling capability.
            memory = await db.situations.find_one({"user_id": OWNER})
            assert memory, "the declared Situation must persist before scheduling"
            initial = await read_followup(db, OWNER, memory["id"])
            assert initial["status"] == "review_pending"
            assert initial["next_check_at"] is None
            assert (await db.agent_goals.find_one({
                "owner_id": OWNER, "id": goal_id_for(OWNER, memory["id"]),
            }))["source_kind"] == INITIAL_KIND
            seen_initial_review = True
            return {
                "response_mode": "tool",
                "tool_call": {
                    "capability": "schedule_situation_check",
                    "arguments": {
                        "situation_id": memory["id"],
                        "expected_revision": memory["revision"],
                        "check_at": due,
                        "purpose": "Rileggere i dati verificabili aggiornati",
                        "notify_when": "Se una nuova fonte segnala un rischio anticipato",
                        "completion_when": "Quando una verifica giustifica il consiglio utile",
                    },
                },
            }
        if calls == 4:
            return {
                "response_mode": "answer",
                "message_to_user": "Il controllo futuro è stato registrato; non ho verificato che i panni siano asciutti.",
            }
        raise AssertionError("Unexpected extra model decision after verified check")

    result = await run_cognitive_loop(
        sess=session, db=db,
        user_message="TEST: ho steso adesso i panni a Tarquinia; segui la situazione.",
        decision_fn=decide,
    )
    assert result.ok, result
    assert result.tool_calls == 2, result.trace
    assert calls == 4
    assert seen_initial_review is True
    suggest.assert_awaited_once_with("Tarquinia")
    resolve.assert_awaited_once_with("synthetic-town")
    forecast.assert_awaited_once_with(
        lat=42.25, lon=11.76, place="Tarquinia",
    )
    device.assert_not_awaited()

    memory = await db.situations.find_one({"user_id": OWNER})
    assert memory is not None and memory["location_label"] == "Tarquinia"
    assert memory["attention_intent"]
    gid = goal_id_for(OWNER, memory["id"])
    review = await read_followup(db, OWNER, memory["id"])
    assert review["status"] == "scheduled", review
    assert review["next_check_at"] == due
    assert (await db.agent_goals.find_one({
        "owner_id": OWNER, "id": gid,
    }))["source_kind"] == KIND
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{gid}",
        "status": {"$in": ["pending", "claimed"]},
    }) == 1
    scheduled_wake = await db.ambient_wakes.find_one({
        "owner_id": OWNER, "source_ref": f"goal:{gid}",
        "status": {"$in": ["pending", "claimed"]},
    })
    assert scheduled_wake["scheduled_for"] == due
    assert await db.ambient_wakes.count_documents({
        "owner_id": "another-owner",
    }) == 0
    assert await db.delivery_plans.count_documents({}) == 0
    assert await db.life_nodes.count_documents({"type": "event"}) == 0
    assert await db.situations.count_documents({"user_id": OWNER}) == 1
    assert (await db.situations.find_one({"id": memory["id"]}))["status"] == "active"
    assert "panni siano asciutti" in result.ora_text


@pytest.mark.asyncio
async def test_provider_outage_after_owned_situation_create_keeps_review_but_never_promises_check(
    monkeypatch,
):
    """A model outage after saving a Situation must not fake monitoring.

    The initial review remains as durable work even when no subsequent
    model answer arrives to choose a meaningful physical checkpoint.
    """
    db, suggest, resolve, forecast, device = await setup(monkeypatch)
    session = ConversationSession(
        user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}},
    )
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "tool",
                "tool_call": {
                    "capability": "get_weather_forecast",
                    "arguments": {"place_query": "Tarquinia"},
                },
            }
        if calls == 2:
            return {
                "response_mode": "answer",
                "message_to_user": (
                    "Ho creato la memoria e seguirò il caso con ORA."
                ),
                "situation_update": {
                    "operation": "create",
                    "source": "user_conversation",
                    "summary": "TEST: situazione non osservata fisicamente",
                    "location_label": "Tarquinia",
                    "desired_outcome": "Sapere il momento utile reale",
                    "attention_intent": "Verificare condizioni prima di agire",
                },
            }
        # All later model calls fail, e.g. quota, network or provider outage.
        # No later function may forge a user-authorised physical checkpoint.
        return None

    result = await run_cognitive_loop(
        sess=session, db=db,
        user_message="TEST ORA: ho steso i panni a Tarquinia, segui la situazione.",
        decision_fn=decide,
    )
    assert calls >= 3
    suggest.assert_awaited_once()
    resolve.assert_awaited_once()
    forecast.assert_awaited_once()
    device.assert_not_awaited()
    state = await db.situations.find_one({"user_id": OWNER})
    assert state is not None
    assert state["attention_intent"]
    gid = goal_id_for(OWNER, state["id"])
    review = await read_followup(db, OWNER, state["id"])
    assert review["status"] == "review_pending", review
    assert review["next_check_at"] is None
    assert (await db.agent_goals.find_one({"id": gid}))["source_kind"] == INITIAL_KIND
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{gid}",
        "status": {"$in": ["pending", "claimed"]},
    }) == 1
    assert await db.delivery_plans.count_documents({}) == 0
    assert not any(phrase in result.ora_text.lower() for phrase in (
        "controllo già programmato", "prossimo controllo è programmato",
        "è il momento di ritirarli", "i panni sono asciutti",
    )), result.ora_text
