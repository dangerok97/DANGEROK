"""Real Situation governance/persistence and loop recovery; scripted cognition only.

The create declaration reproduces the missing summary in the synthetic 636 live
report. These tests do not establish a real drying estimate or run any provider.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.models import ConversationSession
from situations.followup import read_followup
from situations.models import SituationState
from situations.repository import SituationRepository
from situations.service import SituationService


OWNER = "synthetic-situation-protocol"
PLACE_REF = "place:eval-tarquinia-public-point"
SUMMARY = "Panni stesi all'aperto a Tarquinia, ancora da ritirare."
USER_MESSAGE = (
    "Ho appena steso i panni all'aperto a Tarquinia. Dimmi quando è il momento "
    "di ritirarli perché presumibilmente asciutti, oppure prima se serve ripararli."
)
# Full Situation declaration from the first 636 response, except no free-form
# model reasoning. In particular, these other populated fields are NOT summary.
CREATE_636 = {
    "operation": "create",
    "semantic_kind": "Panni asciugati",
    "temporal_scope": "oggi",
    "attention_intent": "valutare se serve ritirare i panni o metterli al riparo",
    "desired_outcome": (
        "Conoscere il momento ottimale per ritirare i panni stesi all'aperto a "
        "Tarquinia, considerando le condizioni meteorologiche attuali e previste."
    ),
    "started_at": "2026-10-12T13:59:49+02:00",
    "icon_key": "shirt",
    "tracking_summary": (
        "ORA terrà questa situazione in vista finché non si decide se ritirare "
        "i panni o metterli al riparo in base alle condizioni meteorologiche."
    ),
    "location_label": "Tarquinia",
    "current_state_summary": "I panni sono stati stesi all'aperto a Tarquinia alle 13:59 di oggi.",
    "participants": [], "constraints": [], "facts": [], "assumptions": [],
    "source_refs": ["user_conversation"], "linked_plan_id": None,
    "linked_object_refs": [], "source": "user_conversation",
}


def session():
    return ConversationSession(user_id=OWNER, meta={"ui_mode": "ai_core", "ai_core": {}})


def observation(payload, name):
    return next(item for item in reversed(payload["observations"]) if item["name"] == name)


def checked_decision(decide):
    # _call_ai honestly maps ordinary provider exceptions to unavailability.
    # A failed test assertion must fail the test, not look like such a response.
    async def checked(system, user):
        try:
            return await decide(system, user)
        except Exception as error:
            pytest.fail(f"Scripted decision assertion failed: {type(error).__name__}: {error}")
    return checked


def schedule(sid, revision, due):
    return {"response_mode": "tool", "tool_call": {
        "capability": "schedule_situation_check", "arguments": {
            "situation_id": sid, "expected_revision": revision, "check_at": due,
            "purpose": "Rivalutare le evidenze pertinenti al momento utile.",
            "completion_when": "Le evidenze rendono ragionevole ritirare ciò che è ancora fuori.",
            "notify_when": "Un rischio impone di intervenire prima del risultato atteso.",
        },
    }}


def assert_summary_feedback(payload):
    failed = observation(payload, "situation_mutation")
    assert failed["kind"] == "error" and failed["status"] == "error"
    assert failed["payload"]["failure_code"] == "SUMMARY_REQUIRED"
    assert failed["payload"]["protocol_error"] == {
        "field": "situation_update.summary",
        "issue": "required_non_empty_string",
        "max_length": 400,
    }
    assert "situation" not in failed["payload"], "a rejected create has no canonical identity"
    assert "summary" not in failed["payload"], "feedback must not manufacture the model's summary"


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["omitted", "null", "blank"])
async def test_rejected_create_reports_required_field_without_inventing_state(monkeypatch, variant):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().synthetic
    sess = session()
    candidate = deepcopy(CREATE_636)
    if variant != "omitted":
        candidate["summary"] = None if variant == "null" else " \t\n"
    original = deepcopy(candidate)
    calls = []

    async def decide(system, user):
        payload = json.loads(user)
        calls.append(payload)
        if len(calls) == 1:
            # The real governance accepts this typed declaration and the real
            # service rejects it before research/tool execution or persistence.
            return {"response_mode": "research", "situation_update": candidate,
                    "research_need": {"question": "Quali condizioni sono pertinenti?",
                                      "purpose": "Valutare la situazione."}}
        assert len(calls) == 2
        assert await db.situations.count_documents({}) == 0
        assert await db.agent_goals.count_documents({}) == 0
        assert await db.ambient_wakes.count_documents({}) == 0
        assert_summary_feedback(payload)
        return {"response_mode": "answer", "message_to_user": "La situazione non è stata registrata."}

    result = await run_cognitive_loop(sess=sess, user_message=USER_MESSAGE, db=db,
                                     decision_fn=checked_decision(decide), max_steps=2)
    assert result.ok and result.tool_calls == 0
    assert len(calls) == 2 and candidate == original
    assert not (sess.meta.get("ai_core") or {}).get("active_situation_ref")
    assert await db.situations.count_documents({}) == 0
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_model_repair_uses_created_id_and_revision_for_one_real_checkpoint(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().synthetic
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index("identity", unique=True)
    sess = session()
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    calls = []
    created = {}

    async def decide(system, user):
        payload = json.loads(user)
        calls.append(payload)
        if len(calls) == 1:
            return {"response_mode": "answer", "situation_update": deepcopy(CREATE_636),
                    "message_to_user": "Tengo la situazione in vista."}
        if len(calls) == 2:
            assert_summary_feedback(payload)
            assert await db.situations.count_documents({}) == 0
            return {"response_mode": "answer", "message_to_user": "Tengo la situazione in vista.",
                    "situation_update": {**deepcopy(CREATE_636), "summary": SUMMARY}}
        if len(calls) == 3:
            ack = observation(payload, "situation_mutation")
            assert ack["status"] == "ok" and ack["payload"]["status"] == "success"
            created.update(ack["payload"]["situation"])
            assert created["id"].startswith("sit_") and created["id"] != PLACE_REF
            assert created["summary"] == SUMMARY and created["revision"] == 1
            assert created["desired_outcome"] == CREATE_636["desired_outcome"]
            assert created["started_at"] == CREATE_636["started_at"]
            return schedule(created["id"], created["revision"], due)
        assert len(calls) == 4
        ack = observation(payload, "schedule_situation_check")
        assert ack["status"] == "ok" and ack["payload"]["next_check_at"] == due
        return {"response_mode": "answer", "message_to_user": "Il controllo risulta registrato."}

    result = await run_cognitive_loop(sess=sess, user_message=USER_MESSAGE, db=db,
                                     decision_fn=checked_decision(decide), max_steps=4)
    assert result.ok and result.tool_calls == 1 and len(calls) == 4
    assert await db.situations.count_documents({"user_id": OWNER}) == 1
    state = await SituationRepository(db).get(OWNER, created["id"])
    assert state.summary == SUMMARY and state.source_refs == ["user_conversation"]
    followup = await read_followup(db, OWNER, state.id)
    assert followup["status"] == "scheduled" and followup["next_check_at"] == due
    assert followup["last_checked_at"] is None and followup["outcome"] is None
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "status": {"$in": ["pending", "claimed"]},
    }) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["place", "foreign", "closed"])
async def test_schedule_never_substitutes_a_place_foreign_or_closed_target(monkeypatch, target):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().synthetic
    sess = session()
    repo = SituationRepository(db)
    active = SituationState(id="sit_owned", user_id=OWNER, summary=SUMMARY)
    foreign = SituationState(id="sit_foreign", user_id="another-owner", summary="Un'altra attività.")
    closed = SituationState(id="sit_closed", user_id=OWNER, summary="Attività conclusa.", status="resolved")
    for state in (active, foreign, closed):
        await repo.insert(state)
    before = [item async for item in db.situations.find({}, {"_id": 0}).sort("id", 1)]
    sid = {"place": PLACE_REF, "foreign": foreign.id, "closed": closed.id}[target]
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    calls = []

    async def decide(system, user):
        payload = json.loads(user)
        calls.append(payload)
        if len(calls) == 1:
            return schedule(sid, 1, due)
        assert len(calls) == 2
        failed = observation(payload, "schedule_situation_check")
        assert failed["status"] == "error"
        assert failed["payload"]["error"] == "active_owned_situation_required"
        return {"response_mode": "answer", "message_to_user": "Il controllo non è stato registrato."}

    result = await run_cognitive_loop(sess=sess, user_message="Registra il controllo della situazione.",
                                     db=db, decision_fn=checked_decision(decide), max_steps=2)
    assert result.ok and result.tool_calls == 1 and len(calls) == 2
    after = [item async for item in db.situations.find({}, {"_id": 0}).sort("id", 1)]
    assert after == before
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_unknown_persistence_failure_does_not_invent_a_required_field(monkeypatch):
    db = AsyncMongoMockClient().synthetic
    calls = []

    async def unavailable(self, **kwargs):
        raise RuntimeError("synthetic-private-storage-detail")

    monkeypatch.setattr(SituationService, "apply", unavailable)

    async def decide(system, user):
        payload = json.loads(user)
        calls.append(payload)
        if len(calls) == 1:
            return {"response_mode": "answer", "message_to_user": "Tengo la situazione in vista.",
                    "situation_update": {**deepcopy(CREATE_636), "summary": SUMMARY}}
        assert len(calls) == 2
        failed = observation(payload, "situation_mutation")
        assert failed["payload"]["failure_code"] == "PERSISTENCE_ERROR"
        assert "protocol_error" not in failed["payload"]
        assert "synthetic-private-storage-detail" not in user
        return {"response_mode": "answer", "message_to_user": "Non riesco a registrare la situazione."}

    result = await run_cognitive_loop(sess=session(), user_message=USER_MESSAGE, db=db,
                                     decision_fn=checked_decision(decide), max_steps=2)
    assert result.ok and result.tool_calls == 0 and len(calls) == 2
    assert await db.situations.count_documents({}) == 0


@pytest.mark.asyncio
async def test_real_loop_sends_create_requirement_and_canonical_target_contract():
    db = AsyncMongoMockClient().synthetic
    calls = []

    async def decide(system, user):
        calls.append(user)
        assert '"summary": "required on create: non-empty semantic summary (max 400 chars); otherwise optional"' in system
        assert "situation_mutation.payload.situation.id" in system
        assert "place_ref and place:<id> are NOT Situation ids" in system
        assert 'response_mode="context"' in system
        assert "You choose the checkpoint; do not hand that job back to the user." in system
        return {"response_mode": "answer", "message_to_user": "Ho letto la richiesta."}

    result = await run_cognitive_loop(sess=session(), user_message="Come funziona una situazione?",
                                     db=db, decision_fn=checked_decision(decide), max_steps=1)
    assert result.ok and result.tool_calls == 0 and len(calls) == 1
    assert await db.situations.count_documents({}) == 0
