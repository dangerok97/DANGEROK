from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.models import ConversationSession
from conversation_engine.ai_core.loop import run_cognitive_loop


@pytest.mark.asyncio
async def test_situation_checkpoint_claim_matches_persisted_time(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().test
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index("identity", unique=True)

    session = ConversationSession(user_id="v106-time", meta={"ui_mode": "ai_core", "ai_core": {}})
    due = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    due_iso = due.isoformat()
    local_hhmm = due.astimezone(ZoneInfo("Europe/Rome")).strftime("%H:%M")
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "response_mode": "answer",
                "message_to_user": "Tengo la situazione in vista.",
                "situation_update": {
                    "operation": "create",
                    "summary": "Una situazione temporanea deve arrivare al suo esito utile.",
                    "semantic_kind": "Situazione attiva",
                    "icon_key": "activity",
                    "tracking_summary": "ORA seguirà questa situazione fino al risultato utile.",
                    "attention_intent": "capire quando arriva il momento utile",
                    "expected_outcome_summary": "oggi",
                    "source_refs": ["user_conversation"],
                },
            }
        if calls == 2:
            state = await db.situations.find_one({"user_id": session.user_id}, {"_id": 0})
            return {
                "response_mode": "tool",
                "tool_call": {
                    "capability": "schedule_situation_check",
                    "arguments": {
                        "situation_id": state["id"],
                        "expected_revision": state["revision"],
                        "check_at": due_iso,
                        "purpose": "Rivalutare le condizioni reali.",
                        "completion_when": "le evidenze indicano che è arrivato il momento utile",
                        "notify_when": "emerge prima un rischio che cambia cosa conviene fare",
                    },
                },
            }
        return {
            "response_mode": "answer",
            "message_to_user": "Ho programmato un controllo alle 14:00.",
            "situation_update": {"operation": "none"},
        }

    result = await run_cognitive_loop(
        sess=session,
        user_message="A che ora controllerai questa situazione?",
        db=db,
        decision_fn=decide,
    )

    assert result.ok
    assert f"alle {local_hhmm}" in result.ora_text
    if local_hhmm != "14:00":
        assert "alle 14:00" not in result.ora_text
