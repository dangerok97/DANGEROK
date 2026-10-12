"""A blocked physical estimate must preserve only a freshly verified check.

The conversation and persisted Situation scheduling use production code. Model
answers are scripted; this suite measures no laundry and sends no notification.
"""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.models import ConversationSession
from situations.followup import cancel_dedicated_followup, read_followup
from situations.models import SituationState
from situations.repository import SituationRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("after_schedule", ["unchanged", "cancelled", "other_owner", "unavailable"])
async def test_blocked_estimate_reports_only_a_current_owned_schedule(monkeypatch, after_schedule):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().test
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index("identity", unique=True)
    owner = "estimate-schedule-synthetic-owner"
    session = ConversationSession(user_id=owner, meta={"ui_mode": "ai_core", "ai_core": {}})
    situation = SituationState(
        id="sit_estimate_schedule_v162", user_id=owner, session_id=session.id,
        summary="Panni appena stesi a Tarquinia.",
        desired_outcome="Sapere quando ritirarli perché presumibilmente asciutti o per un rischio anticipato.",
        attention_intent="Seguire il momento utile per ritirarli.",
    )
    await SituationRepository(db).insert(situation)
    due = (datetime.now(timezone.utc) + timedelta(minutes=31)).replace(microsecond=0).isoformat()
    calls = 0

    async def decision(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"response_mode": "tool", "tool_call": {
                "capability": "schedule_situation_check", "arguments": {
                    "situation_id": situation.id, "expected_revision": 1, "check_at": due,
                    "purpose": "Rivalutare il momento utile con fonti aggiornate.",
                    "completion_when": situation.desired_outcome,
                    "notify_when": "Un rischio anticipato richiede di ritirarli.",
                },
            }}
        assert calls == 2
        if after_schedule == "cancelled":
            await db.situations.update_one({"id": situation.id}, {"$set": {"status": "resolved"}})
            await cancel_dedicated_followup(db, owner, situation.id)
        elif after_schedule == "other_owner":
            await db.situations.update_one({"id": situation.id}, {"$set": {"user_id": "another-owner"}})
        elif after_schedule == "unavailable":
            from situations import followup

            async def unavailable(*args, **kwargs):
                raise RuntimeError("synthetic read failure")

            monkeypatch.setattr(followup, "read_followup", unavailable)
        return {"response_mode": "answer", "message_to_user": "Stimo che i panni saranno asciutti tra 2 e 4 ore."}

    response = await run_cognitive_loop(
        sess=session, user_message="Ho appena steso i panni: segui quando ritirarli.",
        db=db, decision_fn=decision, max_steps=2,
    )
    assert response.ok and calls == 2 and response.tool_calls == 1
    assert "2 e 4 ore" not in response.ora_text
    assert "stima" in response.ora_text.lower()
    assert "ti avviso" not in response.ora_text.lower()
    assert "push" not in response.ora_text.lower()
    if after_schedule == "unchanged":
        saved = await read_followup(db, owner, situation.id)
        assert saved["status"] == "scheduled" and saved["next_check_at"] == due
        assert "prossimo controllo" in response.ora_text.lower()
        assert saved["next_check_label"] in response.ora_text
        assert saved["timezone"] in response.ora_text
        assert await db.ambient_wakes.count_documents({"status": "pending"}) == 1
    else:
        assert "prossimo controllo" not in response.ora_text.lower()
        assert "programmato" not in response.ora_text.lower()


@pytest.mark.asyncio
async def test_blocked_estimate_without_schedule_does_not_invent_one(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().test
    session = ConversationSession(user_id="estimate-only-owner", meta={"ui_mode": "ai_core", "ai_core": {}})

    async def decision(system, payload):
        return {"response_mode": "answer", "message_to_user": "Stimo che i panni saranno asciutti tra 2 e 4 ore."}

    response = await run_cognitive_loop(sess=session, user_message="Quando saranno pronti?",
        db=db, decision_fn=decision, max_steps=1)
    assert response.ok and response.tool_calls == 0
    assert "2 e 4 ore" not in response.ora_text
    assert "stima" in response.ora_text.lower()
    assert "programmato" not in response.ora_text.lower()
    assert await db.ambient_wakes.count_documents({}) == 0
