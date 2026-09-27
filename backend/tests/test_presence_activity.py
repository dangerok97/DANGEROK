"""Presentation telemetry must remain owner-scoped and unable to change execution."""
from types import SimpleNamespace
import time
import pytest
from pydantic import ValidationError
from test_post_call_application_v315 import FintoDb
from conversation_engine.models import ConversationSession, StartBody, MessageBody
from conversation_engine.ai_core.activity import CAPABILITY_AREAS, report_activity, read_activity
from conversation_engine.ai_core.orchestrator import AICoreOrchestrator


@pytest.mark.asyncio
async def test_real_loop_changes_topic_without_defaulting_to_memory_or_extra_ai_calls():
    from conversation_engine.ai_core.loop import run_cognitive_loop
    from conversation_engine.ai_core.activity import public_activity
    sess = ConversationSession(user_id="synthetic-owner", meta={"ui_mode": "ai_core", "ai_core": {}})
    # Same session, new requests and subjects. No tool calls or external effects.
    for index, area in enumerate(("home", "people", "calendar", "places", "documents", "finances", "calls", "memory", None)):
        sess.meta["activity_request_id"] = f"request-{index}"
        await report_activity(None, sess, "processing", reset=True)
        observed = []
        async def decide(system, user):
            observed.append(public_activity(sess.meta))
            return {"response_mode": "answer", "message_to_user": "Risposta sintetica.", "display_area": area}
        result = await run_cognitive_loop(sess=sess, user_message="Esempio inventato.", db=None, decision_fn=decide)
        await report_activity(None, sess, "done", keep_area=True)
        assert result.ok and result.ai_calls == 1 and result.tool_calls == 0
        assert len(observed) == 1 and observed[0]["area"] is None
        signal = public_activity(sess.meta)
        assert signal["area"] == area
        assert signal["basis"] == ("topic" if area else None)
        assert signal["touched"] == ([area] if area else [])
        assert "Esempio" not in str(signal)


@pytest.mark.parametrize("value", ["unknown", "MEMORIA", {}, [], 42])
def test_bad_visual_hint_never_invalidates_a_conversation_decision(value):
    from conversation_engine.ai_core.governance import validate_decision
    from conversation_engine.ai_core.models import CognitiveDecision
    from conversation_engine.ai_core.tool_registry import ToolRegistry
    payload = {"response_mode": "answer", "message_to_user": "Risposta.", "display_area": value}
    assert CognitiveDecision.model_validate(payload).display_area is None
    result = validate_decision(payload, tools=ToolRegistry(None))
    assert result.ok and result.decision.display_area is None


@pytest.mark.asyncio
async def test_topic_and_real_tool_are_distinct_and_cannot_cross_requests():
    sess = ConversationSession(user_id="synthetic-owner", meta={"activity_request_id": "one"})
    await report_activity(None, sess, "processing", area="home", basis="topic")
    await report_activity(None, sess, "tool", area=CAPABILITY_AREAS["read_document"], basis="tool")
    assert sess.meta["presence_activity"]["area"] == "documents"
    assert sess.meta["presence_activity"]["basis"] == "tool"
    assert sess.meta["presence_activity"]["touched"] == ["home", "documents"]
    sess.meta["activity_request_id"] = "two"
    await report_activity(None, sess, "processing", keep_area=True)
    assert sess.meta["presence_activity"]["area"] is None
    assert sess.meta["presence_activity"]["touched"] == []
    assert CAPABILITY_AREAS.get("search_my_life") is None
    assert CAPABILITY_AREAS.get("get_profile_snapshot") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("capability,expected", [("search_life_memory", "memory"), ("search_my_life", "home")])
async def test_real_loop_uses_tool_identity_without_mislabeling_generic_retrieval(monkeypatch, capability, expected):
    import conversation_engine.ai_core.loop as mod
    from conversation_engine.ai_core.models import Observation
    sess = ConversationSession(user_id="synthetic-owner", meta={"activity_request_id": "request-tools"})
    executed = []
    async def execute(self, cap, args, runtime):
        executed.append((cap, dict(sess.meta["presence_activity"])))
        return Observation(kind="tool", name=cap, status="ok", payload={"facts": []})
    monkeypatch.setattr(mod.ToolRegistry, "execute", execute)
    decisions = [
        {"response_mode": "tool", "display_area": "home", "tool_call": {"capability": capability, "arguments": {"query": "esempio casa"}}},
        {"response_mode": "answer", "message_to_user": "Nessuna informazione disponibile."},
    ]
    async def decide(system, user):
        return decisions.pop(0)
    result = await mod.run_cognitive_loop(sess=sess, user_message="Esempio inventato.", db=None, decision_fn=decide)
    assert result.ok and result.ai_calls == 2 and result.tool_calls == 1
    assert len(executed) == 1 and executed[0][0] == capability
    signal = executed[0][1]
    assert signal["phase"] == "tool" and signal["area"] == expected
    assert signal["basis"] == ("tool" if expected == "memory" else "topic")


@pytest.mark.asyncio
async def test_targeted_context_retains_the_topic_instead_of_forcing_memory(monkeypatch):
    import conversation_engine.ai_core.loop as mod
    sess = ConversationSession(user_id="synthetic-owner", meta={"activity_request_id": "request-context"})
    signals = []
    async def record(db, session, phase, **kwargs):
        await report_activity(db, session, phase, **kwargs)
        signals.append(dict(session.meta["presence_activity"]))
    monkeypatch.setattr(mod, "report_activity", record)
    decisions = [
        {"response_mode": "context", "display_area": "people", "context_query": "esempio relazione"},
        {"response_mode": "answer", "display_area": "people", "message_to_user": "Nessuna informazione disponibile."},
    ]
    async def decide(system, user):
        return decisions.pop(0)
    result = await mod.run_cognitive_loop(sess=sess, user_message="Esempio inventato.", db=None, decision_fn=decide)
    assert result.ok and result.ai_calls == 2 and result.context_calls == 2  # baseline + targeted
    assert [s["area"] for s in signals if s["phase"] == "context"] == [None, "people"]
    assert all(s["area"] != "memory" for s in signals)

@pytest.mark.asyncio
async def test_first_request_is_visible_without_session_id_and_is_owner_scoped():
    db = FintoDb()
    sess = ConversationSession(id="session-a", user_id="owner-a", input="private text", meta={"activity_request_id": "request-a"})
    await db["conversation_sessions"].insert_one(sess.model_dump())
    await report_activity(db, sess, "processing", reset=True)
    await report_activity(db, sess, "tool", area=CAPABILITY_AREAS["get_calendar_events"])
    result = await read_activity(db, "owner-a", "request-a")
    assert result["activity"]["area"] == "calendar"
    assert "private text" not in str(result)
    assert (await read_activity(db, "owner-b", "request-a"))["activity"] is None
    assert (await read_activity(db, "owner-a", "request-b"))["activity"] is None
    await report_activity(db, sess, "done", keep_area=True)
    assert (await read_activity(db, "owner-a", "request-a"))["activity"]["phase"] == "done"

@pytest.mark.asyncio
async def test_expired_worker_and_unknown_capability_cannot_fabricate_focus():
    db = FintoDb()
    sess = ConversationSession(id="s", user_id="u", input="x", meta={"activity_request_id": "r"})
    await db["conversation_sessions"].insert_one(sess.model_dump())
    await report_activity(db, sess, "tool", area="user says calendar")
    assert (await read_activity(db, "u", "r"))["activity"]["area"] is None
    await db["conversation_sessions"].update_one({"id": "s"}, {"$set": {"meta.presence_activity.updated_at": time.time() - 121}})
    assert (await read_activity(db, "u", "r"))["activity"] is None
    assert CAPABILITY_AREAS.get("web_search") is None
    assert CAPABILITY_AREAS["prepare_a_phone_call"] == "calls"

@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_completion_and_exception_close_activity_without_repeating_the_turn(monkeypatch, fails):
    import conversation_engine.ai_core.orchestrator as mod
    db = FintoDb()
    sess = ConversationSession(id="s", user_id="u", input="x", meta={"activity_request_id": "r"})
    await db["conversation_sessions"].insert_one(sess.model_dump())
    calls = []
    async def run(**kwargs):
        calls.append(kwargs)
        await report_activity(db, sess, "tool", area="documents")
        if fails:
            raise RuntimeError("synthetic failure")
        return SimpleNamespace(error=None)
    monkeypatch.setattr(mod, "run_cognitive_loop", run)
    orch = AICoreOrchestrator(db)
    if fails:
        with pytest.raises(RuntimeError):
            await orch._observed_turn(sess=sess)
    else:
        await orch._observed_turn(sess=sess)
    assert len(calls) == 1
    result = await read_activity(db, "u", "r")
    assert result["activity"]["phase"] == ("error" if fails else "done")
    assert result["activity"]["touched"] == ["documents"]

@pytest.mark.asyncio
async def test_telemetry_failure_does_not_fail_execution_and_legacy_clients_need_no_signal():
    class Broken:
        def __getitem__(self, name): return self
        async def update_one(self, *args, **kwargs): raise RuntimeError("unavailable")
    sess = ConversationSession(id="s", user_id="u", input="x", meta={"activity_request_id": "r"})
    await report_activity(Broken(), sess, "processing")
    assert sess.meta["presence_activity"]["phase"] == "processing"
    legacy = ConversationSession(id="s", user_id="u", input="x")
    await report_activity(Broken(), legacy, "processing")
    assert "presence_activity" not in legacy.meta
    assert StartBody(text="x").activity_request_id is None
    assert MessageBody(text="x").activity_request_id is None
    with pytest.raises(ValidationError): StartBody(text="x", activity_request_id="r" * 65)
    with pytest.raises(ValidationError): MessageBody(text="x", activity_request_id="private text")

@pytest.mark.asyncio
async def test_start_message_and_resume_keep_the_same_execution_path(monkeypatch):
    import conversation_engine.ai_core.orchestrator as mod
    from conversation_engine.ai_core.models import CognitiveTurnResult
    db = FintoDb()
    observed = []
    async def run(**kwargs):
        sess = kwargs['sess']
        signal = await read_activity(db, sess.user_id, sess.meta['activity_request_id'])
        assert signal['activity']['phase'] == 'processing'
        observed.append((sess.id, kwargs['user_message'], kwargs.get('resume_client', False)))
        await report_activity(db, sess, 'tool', area='calendar')
        return CognitiveTurnResult(mode='answer', ora_text='Risposta di test')
    monkeypatch.setattr(mod, 'run_cognitive_loop', run)
    from copy import deepcopy
    from test_post_call_application_v315 import _combacia
    table = db['conversation_sessions']
    async def replace_one(query, document):
        for index, row in enumerate(table.righe):
            if _combacia(row, query):
                table.righe[index] = deepcopy(document)
                return
        raise AssertionError('replacing a missing session')
    table.replace_one = replace_one
    orch = AICoreOrchestrator(db)
    first = await orch.start('owner', text='Primo messaggio', activity_request_id='first-request')
    assert first['ok'] and first['activity']['request_id'] == 'first-request'
    sid = first['session_id']
    second = await orch.message('owner', sid, text='Secondo messaggio', client_message_id='second-message', activity_request_id='second-request')
    assert second['ok'] and second['activity']['request_id'] == 'second-request'
    assert (await read_activity(db, 'owner', 'first-request'))['activity'] is None
    resumed = await orch.client_resume('owner', sid, completed=[])
    assert resumed['ok'] and resumed['activity']['request_id'] == 'second-request'
    assert len(observed) == 3
    assert all(row[0] == sid for row in observed)
    assert observed[-1][2] is True
    user_turns = [h for h in resumed['history'] if h['role'] == 'user']
    assert len(user_turns) == 2
