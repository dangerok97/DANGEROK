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
