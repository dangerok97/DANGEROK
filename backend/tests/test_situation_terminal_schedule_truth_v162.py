"""A bounded conversation preserves a confirmed check, never a physical result.

Production governance, tool dispatch, weather adapter and Situation scheduling
remain connected. HTTP and cognitive responses are synthetic; no clock moves.
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core import loop
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.models import ConversationSession
from places.models import Coordinates, LifePlace
from situations.followup import read_followup
from situations.models import SituationUpdate
from situations.service import SituationService


OWNER = "terminal-schedule-synthetic-owner"
PLACE_ID = "terminal-schedule-public-place"
HANDOFF_TEXT = "Confermi il passaggio richiesto?"


async def exercise(monkeypatch, *, ending, after_schedule=None):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setenv("WEATHER_PROVIDER", "open_meteo")
    monkeypatch.setenv("AI_CORE_TRACE", "1")
    db = AsyncMongoMockClient().terminal_schedule
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index("identity", unique=True)
    await db.users.insert_one({"id": OWNER, "user_id": OWNER,
        "settings": {"timezone": "Europe/Rome"}})
    await db.life_places.insert_one(LifePlace(
        id=PLACE_ID, user_id=OWNER, label="Tarquinia", locality="Tarquinia",
        coordinates=Coordinates(latitude=42.249, longitude=11.756),
    ).model_dump())
    session = ConversationSession(user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}})
    created = await SituationService(db).apply(
        user_id=OWNER, session_id=session.id, reasoning_epoch="synthetic-declaration",
        update=SituationUpdate(operation="create", summary="Panni appena stesi a Tarquinia.",
            desired_outcome="Indicare quando ritirarli o quando serve un intervento anticipato.",
            attention_intent="Seguire l'evoluzione fino al momento utile.",
            linked_object_refs=["place:" + PLACE_ID]),
    )
    sid = created["situation"]["id"]
    due = (datetime.now(timezone.utc) + timedelta(minutes=31)).replace(microsecond=0).isoformat()
    hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    http_calls, tool_calls = [], []
    original_client_init = httpx.AsyncClient.__init__

    def client_init(self, *args, **kwargs):
        # The fake transport must not initialise a host proxy/optional SOCKS SDK.
        return original_client_init(self, *args, **{**kwargs, "trust_env": False})

    async def send(client, request, **kwargs):
        assert request.url.host == "api.open-meteo.com", "Only the synthetic weather HTTP is allowed"
        http_calls.append(request)
        return httpx.Response(200, request=request, json={
            "timezone": "UTC", "utc_offset_seconds": 0,
            "current": {"time": hour, "weather_code": 1, "temperature_2m": 23,
                "relative_humidity_2m": 56, "wind_speed_10m": 11, "precipitation": 0},
            "hourly": {"time": [hour], "temperature_2m": [23],
                "relative_humidity_2m": [56], "wind_speed_10m": [11],
                "precipitation_probability": [0], "weather_code": [1]},
            "daily": {},
        })

    monkeypatch.setattr(httpx.AsyncClient, "__init__", client_init)
    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    original_execute = ToolRegistry.execute
    saved = {}
    handoff_caps = {
        "phone": "prepare_a_phone_call", "navigation": "open_navigation",
        "calendar": "cancel_calendar_event", "failed_read": "get_situation_followup",
    }

    async def execute(self, capability, arguments, *, runtime=None):
        if capability == handoff_caps.get(ending):
            # Only these handoff/failed-read observations are fakes. The
            # weather and saved checkpoint still use their production path.
            if ending == "calendar":
                payload = {"status": "authority_required", "confirmation_request": {
                    "question": HANDOFF_TEXT, "arguments": {"calendar_ref": "calendar:synthetic"}}}
                observation = Observation(kind="tool", name=capability, status="partial", payload=payload)
            elif ending == "failed_read":
                observation = Observation(kind="tool", name=capability, status="error", payload={
                    "situation_id": sid, "ok": False, "status": "unavailable"})
            else:
                observation = Observation(kind="tool", name=capability, status="ok", payload={
                    "status": "preparing", "say_this": HANDOFF_TEXT, "ready": True})
        else:
            observation = await original_execute(self, capability, arguments, runtime=runtime)
        tool_calls.append((capability, observation.status))
        if capability == "schedule_situation_check":
            assert observation.status == "ok"
            saved.update(await read_followup(db, OWNER, sid))
            assert saved["status"] == "scheduled" and saved["next_check_at"] == due
            if after_schedule:
                await after_schedule(db, sid, session)
        return observation

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    weather = {"response_mode": "tool", "reasoning_status": "needs_tool", "tool_call": {
        "capability": "get_weather_forecast", "arguments": {"place_ref": "place:" + PLACE_ID},
    }, "skill_plan": {"objective": "Seguire il momento utile con fonti pertinenti.",
        "required_capabilities": ["get_weather_forecast", "schedule_situation_check"],
        "completion_condition": "Lettura eseguita e prossimo controllo salvato."}}
    schedule = {"response_mode": "tool", "tool_call": {
        "capability": "schedule_situation_check", "arguments": {
            "situation_id": sid, "expected_revision": 1, "check_at": due,
            "purpose": "Rivalutare il momento utile con fonti aggiornate.",
            "completion_when": created["situation"]["desired_outcome"],
            "notify_when": "Un rischio anticipato richiede un intervento.",
        },
    }}
    answers = [weather, schedule]
    if ending in handoff_caps:
        final = {"response_mode": "tool", "tool_call": {
            "capability": handoff_caps[ending], "arguments": {
                "situation_id": sid, "calendar_ref": "calendar:synthetic", "destination": "Colosseo"}}}
        if ending in ("phone", "navigation", "calendar"):
            final["skill_plan"] = {**weather["skill_plan"], "required_capabilities": [
                *weather["skill_plan"]["required_capabilities"], handoff_caps[ending]]}
        answers.append(final)
    if ending in ("duplicate", "failed_read"):
        answers.append(weather)
    model_calls = 0

    async def decision(system, payload):
        nonlocal model_calls
        assert model_calls < len(answers), "No additional cognitive attempt"
        answer = answers[model_calls]
        model_calls += 1
        return answer

    message = ("Portami al Colosseo." if ending == "navigation"
        else "Ho appena steso i panni a Tarquinia, segui quando ritirarli.")
    response = await loop.run_cognitive_loop(sess=session, user_message=message,
        db=db, decision_fn=decision, max_steps=len(answers))
    assert response.ok and response.ai_calls == model_calls == len(answers)
    assert response.tool_calls == (3 if ending in handoff_caps else 2)
    assert tool_calls[:2] == [("get_weather_forecast", "ok"), ("schedule_situation_check", "ok")]
    assert len(http_calls) == 1
    return db, response, saved, session


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["duplicate", "tool_bound"])
async def test_terminal_reply_preserves_exact_saved_check_without_repeating_work(monkeypatch, ending):
    db, response, saved, _ = await exercise(monkeypatch, ending=ending)
    assert saved["next_check_label"] in response.ora_text
    assert saved["timezone"] in response.ora_text
    assert "valutazione" in response.ora_text.lower() and "non" in response.ora_text.lower()
    assert "ti avvis" not in response.ora_text.lower() and "asciutti" not in response.ora_text.lower()
    current = await read_followup(db, OWNER, saved["situation_id"])
    assert current["next_check_at"] == saved["next_check_at"]
    assert current["goal_id"] == saved["goal_id"]
    assert current["outcome"] is None and current["last_checked_at"] is None
    assert await db.ambient_wakes.count_documents({"status": "pending"}) == 1
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    events = [row["event"] for row in response.trace["steps"]]
    if ending == "duplicate":
        assert "DUPLICATE_SOFT" in events and "BARE_ACK_BLOCKED_TERMINAL" in events
        assert "SITUATION_SCHEDULE_STATUS_TERMINAL" in events
    else:
        assert "LOOP_BOUND" in events and response.error == "loop_bound"
        assert "SITUATION_SCHEDULE_STATUS_BOUND" in events


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["duplicate", "tool_bound"])
@pytest.mark.parametrize("change", ["resolved", "other_owner", "read_unavailable"])
async def test_terminal_copy_does_not_reuse_a_stale_or_unverifiable_check(monkeypatch, ending, change):
    async def after_schedule(db, sid, session):
        if change == "resolved":
            await SituationService(db).apply(user_id=OWNER, session_id=session.id,
                reasoning_epoch="synthetic-withdrawal", update=SituationUpdate(
                    operation="resolve", situation_id=sid, expected_revision=1))
        elif change == "other_owner":
            await db.situations.update_one({"id": sid, "user_id": OWNER},
                {"$set": {"user_id": "a-different-synthetic-owner"}})
        else:
            from situations import followup

            async def unavailable(*args, **kwargs):
                raise RuntimeError("synthetic read unavailable")

            monkeypatch.setattr(followup, "read_followup", unavailable)

    _, response, saved, _ = await exercise(monkeypatch, ending=ending, after_schedule=after_schedule)
    assert saved["next_check_label"] not in response.ora_text
    assert "programmato" not in response.ora_text.lower()
    assert "non" in response.ora_text.lower()
    events = [row["event"] for row in response.trace["steps"]]
    assert not any(event.startswith("SITUATION_SCHEDULE_STATUS_") for event in events)


@pytest.mark.asyncio
async def test_a_newer_failed_followup_read_defeats_the_earlier_schedule_observation(monkeypatch):
    _, response, saved, _ = await exercise(monkeypatch, ending="failed_read")
    assert saved["next_check_label"] not in response.ora_text
    assert "programmato" not in response.ora_text.lower()
    assert "BARE_ACK_BLOCKED_TERMINAL" in [row["event"] for row in response.trace["steps"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["phone", "navigation", "calendar"])
async def test_saved_check_does_not_replace_the_pending_action_handoff(monkeypatch, ending):
    _, response, saved, session = await exercise(monkeypatch, ending=ending)
    assert response.ora_text == HANDOFF_TEXT
    assert saved["next_check_label"] not in response.ora_text
    if ending == "calendar":
        pending = session.meta["ai_core"]["pending_act"]
        assert pending["calendar_cancel"]["question"] == HANDOFF_TEXT
        assert pending["calendar_cancel"]["arguments"] == {"calendar_ref": "calendar:synthetic"}
