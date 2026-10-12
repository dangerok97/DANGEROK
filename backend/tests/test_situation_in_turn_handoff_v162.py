"""Create and schedule during the same conversation, then render current truth.

The production loop, governance, Situation service, scheduler and weather
adapter execute against synthetic storage/HTTP. No real model, delivery, or
clock advancement is used. These tests do not prove physical drying.
"""
from copy import deepcopy
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


OWNER = "in-turn-handoff-synthetic-owner"
PLACE_ID = "in-turn-handoff-public-place"
HANDOFF_TEXT = "Confermi il passaggio richiesto?"
DESIRED_OUTCOME = "Indicare quando ritirarli o quando serve un intervento anticipato."


async def exercise(monkeypatch, *, ending, after_schedule=None, model_text=None,
                   early_reply=False, render_snapshots=None):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setenv("WEATHER_PROVIDER", "open_meteo")
    monkeypatch.setenv("AI_CORE_TRACE", "1")
    db = AsyncMongoMockClient().in_turn_handoff
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
    created, acknowledgements = {}, []
    sid = None
    if render_snapshots is not None:
        from situations import followup

        original_read = followup.read_followup

        async def read(database, owner, situation_id):
            current = await original_read(database, owner, situation_id)
            if database is db and situation_id == sid:
                # Record the owned production reads, including the render/gate
                # before scheduling. The returned snapshot stays untouched.
                render_snapshots.append({
                    "owner_id": owner, "situation_id": situation_id,
                    "model_calls": model_calls, "snapshot": deepcopy(current),
                })
            return current

        monkeypatch.setattr(followup, "read_followup", read)
    original_apply = SituationService.apply

    async def apply(self, **kwargs):
        nonlocal sid
        result = await original_apply(self, **kwargs)
        if kwargs["update"].operation == "create":
            assert result["status"] == "success"
            created.update(result["situation"])
            sid = created["id"]
            acknowledgements.append((result, deepcopy(result)))
        return result

    monkeypatch.setattr(SituationService, "apply", apply)
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
            "completion_when": DESIRED_OUTCOME,
            "notify_when": "Un rischio anticipato richiede un intervento.",
        },
    }}
    declaration = {
        "operation": "create", "summary": "Panni appena stesi a Tarquinia.",
        "desired_outcome": DESIRED_OUTCOME,
        "attention_intent": "Seguire l'evoluzione fino al momento utile.",
        "linked_object_refs": ["place:" + PLACE_ID],
        "location_label": "Tarquinia",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if model_text is not None:
        schedule["message_to_user"] = model_text
    answers = [{**deepcopy(weather), "situation_update": declaration}]
    if early_reply:
        answers.append({
            "response_mode": "answer", "message_to_user": "Ok.",
            "skill_plan": deepcopy(weather["skill_plan"]),
        })
    answers.append(schedule)
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
        try:
            assert model_calls < len(answers), "No additional cognitive attempt"
            if model_calls == 0:
                assert await db.situations.count_documents({}) == 0
            else:
                assert len(acknowledgements) == 1 and created["revision"] == 1
            answer = deepcopy(answers[model_calls])
            arguments = (answer.get("tool_call") or {}).get("arguments") or {}
            if "situation_id" in arguments:
                assert sid is not None
                arguments["situation_id"] = sid
            model_calls += 1
            return answer
        except Exception as error:
            pytest.fail(f"Scripted decision failed: {type(error).__name__}: {error}")

    message = ("Portami al Colosseo." if ending == "navigation"
        else "Ho appena steso i panni a Tarquinia, segui quando ritirarli.")
    response = await loop.run_cognitive_loop(sess=session, user_message=message,
        db=db, decision_fn=decision, max_steps=len(answers))
    assert response.ok and response.ai_calls == model_calls == len(answers)
    assert response.tool_calls == (3 if ending in handoff_caps else 2)
    assert tool_calls[:2] == [("get_weather_forecast", "ok"), ("schedule_situation_check", "ok")]
    assert len(http_calls) == 1
    assert await db.situations.count_documents({}) == 1
    assert len(acknowledgements) == 1
    original_ack, ack_snapshot = acknowledgements[0]
    assert original_ack == ack_snapshot, "A render must not rewrite historical mutation evidence"
    assert "follow_up" not in ack_snapshot
    assert created["desired_outcome"] == DESIRED_OUTCOME
    return db, response, saved, session


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["duplicate", "tool_bound"])
async def test_terminal_reply_preserves_exact_saved_check_without_repeating_work(monkeypatch, ending):
    db, response, saved, _ = await exercise(monkeypatch, ending=ending)
    assert saved["next_check_label"] in response.ora_text
    assert saved["timezone"] in response.ora_text
    assert "non risulta" not in response.ora_text.lower()
    assert "non riesco a verificare" not in response.ora_text.lower()
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
async def test_earlier_render_does_not_leave_a_stale_handoff_after_scheduling(monkeypatch, ending):
    snapshots = []
    events = []
    original_public_trace = loop.public_trace

    def observe_trace(trace):
        # The public projection keeps only the first 12 steps. Capture event
        # names before projection and preserve the original return unchanged.
        events[:] = [row["event"] for row in trace["steps"]]
        return original_public_trace(trace)

    monkeypatch.setattr(loop, "public_trace", observe_trace)
    db, response, saved, _ = await exercise(
        monkeypatch, ending=ending, early_reply=True, render_snapshots=snapshots)
    before_schedule = [item for item in snapshots if item["model_calls"] == 2]
    assert before_schedule
    assert snapshots[0]["snapshot"]["status"] not in ("scheduled", "due", "running")
    assert before_schedule[0]["snapshot"]["status"] not in ("scheduled", "due", "running")
    assert snapshots[-1]["snapshot"]["status"] == "scheduled"
    assert snapshots[-1]["snapshot"]["next_check_at"] == saved["next_check_at"]
    assert all(
        item["owner_id"] == OWNER
        and item["situation_id"] == saved["situation_id"]
        and item["snapshot"]["situation_id"] == saved["situation_id"]
        for item in snapshots
    )
    assert response.ai_calls == (4 if ending == "duplicate" else 3)
    assert saved["next_check_label"] in response.ora_text
    assert saved["timezone"] in response.ora_text
    assert "non risulta" not in response.ora_text.lower()
    assert "non riesco a verificare" not in response.ora_text.lower()
    assert "valutazione" in response.ora_text.lower() and "non" in response.ora_text.lower()
    assert "ti avvis" not in response.ora_text.lower() and "asciutti" not in response.ora_text.lower()
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert await db.ambient_wakes.count_documents({"status": "pending"}) == 1
    # The Situation gate runs before the generic skill-plan guard here.
    assert "SITUATION_FOLLOWUP_NUDGE" in events
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


@pytest.mark.asyncio
async def test_bound_refreshes_handoff_even_when_the_last_tool_has_model_prose(monkeypatch):
    message = "Sto seguendo la situazione; la valutazione non è conclusa."
    _, response, saved, _ = await exercise(monkeypatch, ending="tool_bound", model_text=message)
    assert response.ora_text == message
    assert "non risulta" not in response.ora_text.lower()
    assert saved["status"] == "scheduled"
    assert response.error == "loop_bound"


@pytest.mark.asyncio
async def test_bound_uses_one_snapshot_for_the_check_and_its_handoff(monkeypatch):
    from situations import followup

    original_read = followup.read_followup
    snapshots = []

    async def after_schedule(db, sid, session):
        async def read(database, owner, situation_id):
            current = await original_read(database, owner, situation_id)
            snapshots.append(deepcopy(current))
            # The state can change after this read. A second render read would
            # observe a different state; neither response is an atomic promise.
            await database.situations.update_one(
                {"id": situation_id, "user_id": owner}, {"$set": {"status": "resolved"}})
            return current
        monkeypatch.setattr(followup, "read_followup", read)

    _, response, saved, _ = await exercise(
        monkeypatch, ending="tool_bound", after_schedule=after_schedule)
    assert len(snapshots) == 1
    assert snapshots[0]["next_check_at"] == saved["next_check_at"]
    assert saved["next_check_label"] in response.ora_text
    assert "non risulta" not in response.ora_text.lower()


@pytest.mark.parametrize("text", ["", "Ok."])
@pytest.mark.parametrize("status,expected", [
    ("stopped", "Il controllo di questa situazione è terminato. Non sono previsti altri controlli."),
    ("unavailable", "Non riesco a verificare la programmazione del controllo."),
])
def test_empty_handoff_does_not_reuse_the_historical_active_state(text, status, expected):
    result = {"status": "success", "operation": "create",
              "situation": {"id": "synthetic-situation", "status": "active"},
              "follow_up": {"status": status, "situation_id": "synthetic-situation"}}
    original = deepcopy(result)
    assert loop._with_situation_handoff(text, result) == expected
    assert result == original
    assert "attive" not in expected and "asciutt" not in expected
