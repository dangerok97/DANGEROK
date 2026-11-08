"""8/11 «Ho appena steso i panni»: the drying plan from the forecast is the follow-up.

The guard found no model-scheduled check and replaced the reply with its
internal diagnosis, although the runtime had already planned the drying
reminder (which notifies by itself)."""
import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import _with_situation_handoff
from conversation_engine.ai_core.models import ContextFact
from situations.models import SituationState
from situations.repository import SituationRepository
from situations.turn_followup import FollowupTurnGate

OWNER, SID = "dry-owner", "sit_dry_1"


async def world(*, planned: bool):
    db = AsyncMongoMockClient().test
    await SituationRepository(db).insert(SituationState(
        id=SID, user_id=OWNER, session_id="ces_x", summary="Panni appena stesi",
        attention_intent="Avvisare quando sono asciutti."))
    if planned:
        await db.reminders.insert_one({"id": f"rem_sit_{SID}", "user_id": OWNER, "status": "open",
                                       "due_at": "2099-01-01T15:00:00+00:00", "title": "Dovrebbero essere asciutti",
                                       "origin": "situation_stated_time",
                                       "meta": {"situation_id": SID, "kind": "drying_end"}})
    return db


@pytest.mark.asyncio
async def test_a_runtime_plan_leaves_nothing_pending():
    gate = FollowupTurnGate(await world(planned=True), OWNER)
    await gate.refresh([ContextFact(source="situation", ref=f"situation:{SID}")])
    assert gate.pending == []


@pytest.mark.asyncio
async def test_without_any_plan_the_guard_still_asks_for_one():
    gate = FollowupTurnGate(await world(planned=False), OWNER)
    await gate.refresh([ContextFact(source="situation", ref=f"situation:{SID}")])
    assert [p["situation_id"] for p in gate.pending] == [SID]


def test_the_reply_does_not_say_the_check_is_missing_when_the_runtime_set_it():
    result = {"status": "success", "operation": "create", "situation": {"attention_intent": ""},
              "follow_up": {"status": "not_scheduled"},
              "stated_reminder": {"at_local": "16:40", "drying": True}}
    text = _with_situation_handoff("Saranno asciutti verso le 16:40, ti avviso io.", result)
    assert "non risulta ancora programmato" not in text
    # 8/11: with the forecast's numbers the reply is said by code.
    assert "16:40" in text and "ti avviso io" in text
