"""Create and schedule during the same conversation, then render current truth.

The production loop, governance, Situation service, scheduler and weather
adapter execute against synthetic storage/HTTP. No real model, delivery, or
clock advancement is used. These tests do not prove physical drying.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core import loop
from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.models import CognitiveDecision, Observation
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
        "source_refs": [],
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


# Formal raw-JSON completeness is separate from the semantic choice of a place.
_CREATE_CONTEXT_FIELDS = ("location_label", "source_refs", "linked_object_refs")


def _raw_context_create():
    return {
        "response_mode": "answer", "message_to_user": "Tengo la situazione in vista.",
        "situation_update": {
            "operation": "create", "summary": "Una situazione temporanea è ancora in corso.",
            "attention_intent": "Rivalutare le condizioni prima del prossimo passo.",
            "desired_outcome": DESIRED_OUTCOME,
            "location_label": None, "source_refs": [], "linked_object_refs": [],
        },
    }


@pytest.mark.parametrize("missing", [
    ("location_label",), ("source_refs",), ("linked_object_refs",),
    ("location_label", "source_refs"),
    ("location_label", "linked_object_refs"),
    ("source_refs", "linked_object_refs"),
    _CREATE_CONTEXT_FIELDS,
])
def test_raw_create_context_omissions_require_repair_before_defaults(missing):
    raw = _raw_context_create()
    for field in missing:
        del raw["situation_update"][field]
    original = deepcopy(raw)
    result = validate_decision(raw, tools=ToolRegistry(None))
    assert not result.ok and result.decision is None
    assert result.errors == [f"situation_create_missing_{field}" for field in missing]
    assert raw == original, "The validator must not invent unknowns or references"


@pytest.mark.parametrize("typed", [False, True])
def test_explicit_unknown_context_and_typed_defaults_keep_their_existing_meaning(typed):
    raw = _raw_context_create()
    if typed:
        # Trusted typed callers already serialize all three optional defaults.
        for field in _CREATE_CONTEXT_FIELDS:
            del raw["situation_update"][field]
        raw = CognitiveDecision.model_validate(raw)
        assert all(field in raw.model_dump()["situation_update"] for field in _CREATE_CONTEXT_FIELDS)
    original = raw.model_dump() if typed else deepcopy(raw)
    result = validate_decision(raw, tools=ToolRegistry(None))
    assert result.ok and result.decision is not None
    update = result.decision.situation_update
    assert update.operation == "create"
    assert update.location_label is None
    assert update.source_refs == [] and update.linked_object_refs == []
    assert (raw.model_dump() if typed else raw) == original


@pytest.mark.parametrize("operation", ["none", "update", "cancel", "resolve"])
def test_non_create_declarations_do_not_require_initial_context_fields(operation):
    update = {"operation": operation}
    if operation != "none":
        update.update(situation_id="sit_existing", expected_revision=3)
    if operation == "update":
        update["summary"] = "Una precisazione circoscritta."
    raw = {"response_mode": "answer", "message_to_user": "Ho letto l'aggiornamento.",
           "situation_update": update}
    original = deepcopy(raw)
    result = validate_decision(raw, tools=ToolRegistry(None))
    assert result.ok and result.decision.situation_update.operation == operation
    assert result.decision.situation_update.situation_id == update.get("situation_id")
    assert not any(code.startswith("situation_create_missing_") for code in result.errors)
    assert raw == original and all(field not in update for field in _CREATE_CONTEXT_FIELDS)


@pytest.mark.parametrize("focus", ["place:" + PLACE_ID, None])
def test_display_focus_survives_governance_without_becoming_a_situation_link(focus):
    raw = {**_raw_context_create(), "display_focus_ref": focus}
    original = deepcopy(raw)
    result = validate_decision(raw, tools=ToolRegistry(None))
    assert result.ok and result.decision.display_focus_ref == focus
    assert loop._display_focus_ref(result.decision, [], None) == focus
    assert result.decision.situation_update.linked_object_refs == []
    assert result.decision.situation_update.location_label is None
    assert raw == original


@pytest.mark.parametrize("focus", [
    {"ref": "place:" + PLACE_ID}, ["place:" + PLACE_ID], 123, False, "x" * 161,
], ids=["object", "list", "number", "boolean", "too_long"])
def test_invalid_display_focus_is_not_stringified_or_silently_discarded(focus):
    raw = {**_raw_context_create(), "display_focus_ref": focus}
    original = deepcopy(raw)
    result = validate_decision(raw, tools=ToolRegistry(None))
    assert not result.ok and result.decision is None
    assert "pydantic_fail" in result.errors
    assert raw == original


def _checked_context_decision(decide):
    async def checked(system, user):
        try:
            return await decide(system, user)
        except Exception as error:
            pytest.fail(f"Scripted declaration assertion failed: {type(error).__name__}: {error}")
    return checked


@pytest.mark.asyncio
async def test_existing_single_repair_precedes_one_real_create_and_checkpoint(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setenv("AI_CORE_TRACE", "1")
    db = AsyncMongoMockClient().create_context_protocol
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index("identity", unique=True)
    await db.users.insert_one({"id": OWNER, "user_id": OWNER,
                              "settings": {"timezone": "Europe/Rome"}})
    session = ConversationSession(user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}})
    complete = _raw_context_create()
    incomplete = deepcopy(complete)
    for field in _CREATE_CONTEXT_FIELDS:
        del incomplete["situation_update"][field]
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    calls, mutations, tools = [], [], []
    created = {}
    original_apply, original_execute = SituationService.apply, ToolRegistry.execute

    async def apply(self, **kwargs):
        mutations.append(deepcopy(kwargs["update"].model_dump()))
        return await original_apply(self, **kwargs)

    async def execute(self, capability, arguments, *, runtime=None):
        assert capability == "schedule_situation_check", "No implicit external read or extra tool"
        tools.append(deepcopy(arguments))
        return await original_execute(self, capability, arguments, runtime=runtime)

    monkeypatch.setattr(SituationService, "apply", apply)
    monkeypatch.setattr(ToolRegistry, "execute", execute)

    async def decide(system, user):
        payload = json.loads(user)
        calls.append({"system": system, "user": user})
        if len(calls) == 1:
            return deepcopy(incomplete)
        if len(calls) == 2:
            assert user == calls[0]["user"], "The existing repair sees the same turn input"
            assert "Situation CREATE missing fields: " + ", ".join(_CREATE_CONTEXT_FIELDS) in system
            assert "Do not invent a place or link." in system
            assert mutations == [] and tools == []
            assert await db.situations.count_documents({}) == 0
            assert await db.agent_goals.count_documents({}) == 0
            assert await db.ambient_wakes.count_documents({}) == 0
            return deepcopy(complete)
        if len(calls) == 3:
            ack = next(item for item in reversed(payload["observations"])
                       if item["name"] == "situation_mutation")
            assert ack["status"] == "ok" and ack["payload"]["status"] == "success"
            created.update(ack["payload"]["situation"])
            assert created["id"].startswith("sit_") and created["revision"] == 1
            assert created["location_label"] is None
            assert created["linked_object_refs"] == []
            stored = await db.situations.find_one({"id": created["id"], "user_id": OWNER})
            assert stored is not None and stored["source_refs"] == []
            return {"response_mode": "tool", "tool_call": {
                "capability": "schedule_situation_check", "arguments": {
                    "situation_id": created["id"], "expected_revision": created["revision"],
                    "check_at": due, "purpose": "Rivalutare le condizioni al momento utile.",
                    "completion_when": DESIRED_OUTCOME,
                    "notify_when": "Un rischio richiede un intervento anticipato.",
                },
            }}
        assert len(calls) == 4, "One existing repair, then the same bounded loop"
        ack = next(item for item in reversed(payload["observations"])
                   if item["name"] == "schedule_situation_check")
        assert ack["status"] == "ok" and ack["payload"]["next_check_at"] == due
        return {"response_mode": "answer", "message_to_user": "Il controllo risulta registrato."}

    result = await loop.run_cognitive_loop(
        sess=session, user_message="Segui questa situazione temporanea fino al suo esito.",
        db=db, decision_fn=_checked_context_decision(decide), max_steps=3,
    )
    # The fourth call is the pre-existing malformed-declaration repair, not an
    # additional loop stage or an increase of max_steps.
    assert result.ok and result.ai_calls == len(calls) == 4
    assert result.tool_calls == len(tools) == 1
    assert len(mutations) == 1
    assert mutations[0] == SituationUpdate.model_validate(complete["situation_update"]).model_dump()
    assert await db.situations.count_documents({"user_id": OWNER}) == 1
    assert created["desired_outcome"] == DESIRED_OUTCOME
    assert tools[0]["situation_id"] == created["id"]
    current = await read_followup(db, OWNER, created["id"])
    assert current["status"] == "scheduled" and current["next_check_at"] == due
    assert current["last_checked_at"] is None and current["outcome"] is None
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "status": {"$in": ["pending", "claimed"]},
    }) == 1
    assert "AI_DECISION_RETRY" in [row["event"] for row in result.trace["steps"]]


@pytest.mark.asyncio
async def test_still_incomplete_repair_has_no_domain_effect_or_success_claim(monkeypatch):
    from life_memory.governance import MemoryGovernanceService

    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setenv("AI_CORE_TRACE", "1")
    db = AsyncMongoMockClient().rejected_create_context
    session = ConversationSession(user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}})
    raw = _raw_context_create()
    for field in _CREATE_CONTEXT_FIELDS:
        del raw["situation_update"][field]
    rejected_copy = "Ho completato la mutazione non ancora validata."
    raw.update(
        response_mode="tool", message_to_user=rejected_copy,
        tool_call={"capability": "get_weather_forecast", "arguments": {"city": "Tarquinia"}},
        state_updates=[{"path": "current_facts.note", "value": "rejected-state-marker"}],
        memory_candidates=[{"summary": "Preferisco risposte concise.",
                            "permanence": "durable", "authority": "user_stated"}],
    )
    original = deepcopy(raw)
    calls = []

    async def forbidden(*args, **kwargs):
        pytest.fail("An invalid declaration cannot call Situation, Memory or a tool")

    monkeypatch.setattr(SituationService, "apply", forbidden)
    monkeypatch.setattr(MemoryGovernanceService, "process", forbidden)
    monkeypatch.setattr(ToolRegistry, "execute", forbidden)

    async def decide(system, user):
        calls.append({"system": system, "user": user})
        assert len(calls) <= 2, "There is no second repair stage"
        if len(calls) == 2:
            assert user == calls[0]["user"]
            assert "Situation CREATE missing fields: " + ", ".join(_CREATE_CONTEXT_FIELDS) in system
            assert rejected_copy not in system
        return deepcopy(raw)

    result = await loop.run_cognitive_loop(
        sess=session, user_message="Segui la situazione descritta.", db=db,
        decision_fn=_checked_context_decision(decide), max_steps=1,
    )
    assert result.ai_calls == len(calls) == 2 and result.tool_calls == 0
    assert raw == original
    assert rejected_copy not in (result.ora_text or "")
    assert "rejected-state-marker" not in json.dumps(session.meta)
    assert not (session.meta.get("ai_core") or {}).get("active_situation_ref")
    for collection in ("situations", "agent_goals", "ambient_wakes", "memories"):
        assert await db[collection].count_documents({}) == 0
    events = [row["event"] for row in result.trace["steps"]]
    assert "MALFORMED_FALLBACK" in events
    assert "SITUATION_MUTATION" not in events and "TOOL" not in events
