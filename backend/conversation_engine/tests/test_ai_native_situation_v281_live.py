"""Opt-in real-provider semantic evals for Situation V1.

These tests never use production data or Mongo: the provider reasons over an
in-memory user-scoped repository. They load local provider configuration but
never print credentials or model payloads.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import load_dotenv

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.models import ConversationSession
from conversation_engine.tests.test_ai_native_situation_v281 import FakeDB
from llm.manager import get_manager
from life_os.models import LifeOsPlan, PlanItem
from situations.models import SituationUpdate
from situations.service import SituationService

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


async def _provider_available() -> bool:
    return bool((await get_manager().status()).get("configured"))


@pytest.mark.asyncio
async def test_real_provider_roma_context_continuity():
    if not await _provider_available():
        pytest.skip("No real LLM provider configured")
    db = FakeDB()
    sess = ConversationSession(
        id="eval_roma", user_id="eval_v281", meta={"ai_core": {}}
    )
    turns = [
        "Domani devo andare a Roma.",
        "Devo essere lì alle 10.",
        "Anzi lascia perdere, viene Giulia qui.",
    ]
    for turn in turns:
        result = await run_cognitive_loop(sess=sess, user_message=turn, db=db)
        assert result.ok and result.ora_text
    docs = db["situations"].docs
    assert len(docs) == 1
    assert docs[0]["revision"] >= 3
    assert docs[0]["status"] == "cancelled"
    assert "memories" not in db._cols


@pytest.mark.asyncio
async def test_real_provider_non_travel_context_continuity():
    if not await _provider_available():
        pytest.skip("No real LLM provider configured")
    db = FakeDB()
    sess = ConversationSession(
        id="eval_work", user_id="eval_v281", meta={"ai_core": {}}
    )
    turns = [
        "Devo preparare la presentazione per venerdì.",
        "Il manager vuole massimo 5 minuti.",
        "Alla fine la presentazione è stata annullata.",
    ]
    for turn in turns:
        result = await run_cognitive_loop(sess=sess, user_message=turn, db=db)
        assert result.ok and result.ora_text
    docs = db["situations"].docs
    assert len(docs) == 1
    assert docs[0]["revision"] >= 3
    assert docs[0]["status"] == "cancelled"
    assert "memories" not in db._cols


@pytest.mark.asyncio
async def test_real_provider_cancels_linked_plan_only_by_ai_decision():
    if not await _provider_available():
        pytest.skip("No real LLM provider configured")
    db = FakeDB()
    plan = LifeOsPlan(
        id="eval_plan",
        user_id="eval_v281",
        summary="Preparare un'attività temporanea",
        items=[PlanItem(id="eval_item", title="Preparazione")],
    )
    await db["life_os_plans"].insert_one(plan.model_dump())
    situation = await SituationService(db).apply(
        user_id="eval_v281",
        session_id="eval_linked",
        update=SituationUpdate(
            operation="create",
            summary="Attività temporanea prevista",
            linked_plan_id="eval_plan",
            source_refs=["user_conversation"],
        ),
        reasoning_epoch="seed",
    )
    sess = ConversationSession(
        id="eval_linked",
        user_id="eval_v281",
        meta={
            "ai_core": {
                "active_plan_id": "eval_plan",
                "active_situation_ref": situation["situation"],
            }
        },
    )
    result = await run_cognitive_loop(
        sess=sess,
        user_message="Questa attività non si farà più: annullala.",
        db=db,
    )
    assert result.ok and result.ora_text
    stored_situation = db["situations"].docs[0]
    stored_plan = db["life_os_plans"].docs[0]
    assert stored_situation["status"] == "cancelled"
    assert stored_plan["status"] == "cancelled"
