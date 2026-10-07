"""V105 — temporary Situation persistence must not be reported as durable-Memory failure."""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.models import ConversationSession
from conversation_engine.ai_core.loop import run_cognitive_loop


@pytest.mark.asyncio
async def test_successful_temporary_situation_is_not_rewritten_as_memory_failure(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().test
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index("identity", unique=True)

    session = ConversationSession(
        user_id="v105-owner",
        meta={"ui_mode": "ai_core", "ai_core": {}},
    )
    due = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "answer",
                "message_to_user": "Ho salvato in memoria che la situazione è attiva.",
                "situation_update": {
                    "operation": "create",
                    "summary": "Una situazione temporanea è attiva.",
                    "semantic_kind": "Situazione attiva",
                    "icon_key": "activity",
                    "tracking_summary": "ORA seguirà questa situazione fino al suo esito utile.",
                    "attention_intent": "capire quando arriva il momento utile per intervenire",
                    "expected_outcome_summary": "raggiungere il momento utile per concludere",
                    "source_refs": ["user_conversation"],
                },
            }
        if calls == 2:
            state = await db.situations.find_one(
                {"user_id": session.user_id}, {"_id": 0}
            )
            assert state is not None
            return {
                "response_mode": "tool",
                "tool_call": {
                    "capability": "schedule_situation_check",
                    "arguments": {
                        "situation_id": state["id"],
                        "expected_revision": state["revision"],
                        "check_at": due,
                        "purpose": "Rivalutare le condizioni reali.",
                        "completion_when": "le evidenze indicano che il risultato utile è raggiunto",
                        "notify_when": "emerge prima un rischio che cambia cosa conviene fare",
                    },
                },
            }
        return {
            "response_mode": "answer",
            "message_to_user": "Ho salvato in memoria la situazione e ti avviserò.",
            "situation_update": {"operation": "none"},
        }

    result = await run_cognitive_loop(
        sess=session,
        user_message="Questa situazione va seguita.",
        db=db,
        decision_fn=decide,
    )

    assert result.ok
    assert "Non sono riuscita a salvare" not in result.ora_text
    assert "Sto seguendo questa situazione" in result.ora_text
    assert "Ti avviso quando" in result.ora_text
    assert "ti avviso prima" in result.ora_text.lower()
    assert await db.situations.count_documents({"user_id": session.user_id}) == 1
    assert await db.agent_goals.count_documents({"owner_id": session.user_id}) == 1
