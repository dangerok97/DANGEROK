"""Persisted closure is reported truthfully even with an empty tool envelope."""
import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.models import ConversationSession
from situations.models import SituationState
from situations.repository import SituationRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,status", [("resolve", "resolved"), ("cancel", "cancelled")])
async def test_closed_situation_is_not_reported_as_missing_tool(monkeypatch, operation, status):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().test
    owner = "v160-closure-owner"
    state = SituationState(id="sit_v160_closure", user_id=owner,
                           summary="Una situazione temporanea già terminata.")
    await SituationRepository(db).insert(state)
    session = ConversationSession(user_id=owner, meta={"ui_mode": "ai_core", "ai_core": {}})

    async def decide(system, payload):
        return {
            "response_mode": "tool",
            "situation_update": {
                "operation": operation,
                "situation_id": state.id,
                "expected_revision": state.revision,
                "source_refs": ["user_conversation"],
            },
        }

    result = await run_cognitive_loop(sess=session, user_message="Questa situazione è conclusa.",
                                      db=db, decision_fn=decide)
    saved = await SituationRepository(db).get(owner, state.id)
    assert saved.status == status
    assert result.ok
    assert "Ho chiuso questa situazione." in result.ora_text
    assert "Non sono previsti altri controlli." in result.ora_text
    assert "Non riesco a usare lo strumento" not in result.ora_text
    assert result.tool_calls == 0
    assert await db.situations.count_documents({"user_id": owner}) == 1
    assert await db.agent_goals.count_documents({"owner_id": owner, "status": "open"}) == 0


@pytest.mark.asyncio
async def test_failed_closure_never_gets_success_confirmation(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().test
    owner = "v160-failed-closure-owner"
    state = SituationState(id="sit_v160_failed_closure", user_id=owner,
                           summary="Una situazione ancora attiva.")
    await SituationRepository(db).insert(state)
    session = ConversationSession(user_id=owner, meta={"ui_mode": "ai_core", "ai_core": {}})
    calls = 0

    async def fail_apply(self, **kwargs):
        raise RuntimeError("synthetic persistence failure")

    monkeypatch.setattr("situations.service.SituationService.apply", fail_apply)

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "tool",
                "situation_update": {"operation": "resolve", "situation_id": state.id,
                                     "expected_revision": state.revision},
            }
        return {"response_mode": "answer", "message_to_user": "La chiusura non è stata confermata."}

    result = await run_cognitive_loop(sess=session, user_message="Questa situazione è conclusa.",
                                      db=db, decision_fn=decide)
    saved = await SituationRepository(db).get(owner, state.id)
    assert saved.status == "active"
    assert "Ho chiuso" not in result.ora_text
    assert "chiusura non è stata confermata" in result.ora_text


@pytest.mark.asyncio
async def test_hypothetical_next_use_does_not_reopen_old_session_context(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().test
    owner = "v160-hypothetical-owner"
    old = SituationState(id="sit_v160_old", user_id=owner,
                         summary="Attività terminata.", attention_intent="Seguire il risultato.")
    old_context = old.context_preview()
    old.status = "resolved"
    old.attention_intent = None
    await SituationRepository(db).insert(old)
    session = ConversationSession(user_id=owner, meta={
        "ui_mode": "ai_core", "ai_core": {"active_situation_ref": old_context},
    })

    async def decide(system, payload):
        return {"response_mode": "answer", "situation_update": {"operation": "none"},
                "message_to_user": "Quando inizierai, servirà una stima del momento utile per intervenire."}

    result = await run_cognitive_loop(
        sess=session, user_message="Non è più in corso. La prossima volta voglio sapere quando intervenire.",
        db=db, decision_fn=decide,
    )
    assert result.ok
    assert (await SituationRepository(db).get(owner, old.id)).status == "resolved"
    assert await db.situations.count_documents({"user_id": owner}) == 1
    assert await db.agent_goals.count_documents({"owner_id": owner}) == 0
    assert await db.ambient_wakes.count_documents({"user_id": owner}) == 0
