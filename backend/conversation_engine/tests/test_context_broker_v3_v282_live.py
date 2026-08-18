"""Opt-in real-provider evals for AI-owned ContextNeed V3.

The model decisions are real. Evidence is isolated in memory and no provider
credential or model payload is logged by this module.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import load_dotenv

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.models import ConversationSession
from conversation_engine.tests.test_ai_native_situation_v281 import FakeDB
from life_os.models import LifeOsPlan, PlanItem
from llm.manager import get_manager
from situations.models import SituationUpdate
from situations.service import SituationService

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


async def _provider_available() -> bool:
    return bool((await get_manager().status()).get("configured"))


async def _run_context_question(
    db: FakeDB, *, session_id: str, user_id: str, message: str,
    require_targeted_context: bool = True,
):
    session = ConversationSession(id=session_id, user_id=user_id, meta={"ai_core": {}})
    result = await run_cognitive_loop(sess=session, user_message=message, db=db)
    assert result.ok and result.ora_text
    if require_targeted_context:
        assert result.context_calls >= 2, "the model did not request targeted Stage B context"
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("summary", "constraint", "question"),
    [
        (
            "Andare a Roma domani",
            "Arrivare entro le 10",
            "A che ora secondo te mi conviene partire, considerando ciò che sai già?",
        ),
        (
            "Preparare una presentazione importante entro venerdì",
            "Durata massima cinque minuti",
            "Quali finestre ho per lavorarci considerando gli altri impegni già salvati?",
        ),
        (
            "Ospitare una cena informale sabato",
            "Cucina disponibile soltanto dopo le 18",
            "Quali finestre ho per prepararla considerando gli altri impegni già salvati?",
        ),
    ],
)
async def test_real_provider_requests_general_purpose_context(
    summary: str, constraint: str, question: str
):
    if not await _provider_available():
        pytest.skip("No real LLM provider configured")
    db = FakeDB()
    user_id = "eval_v282"
    await SituationService(db).apply(
        user_id=user_id,
        session_id="earlier_session",
        update=SituationUpdate(
            operation="create",
            summary=summary,
            constraints=[constraint],
            source_refs=["user_conversation"],
        ),
        reasoning_epoch=f"seed_{abs(hash(summary))}",
    )
    await db["life_os_plans"].insert_one(
        LifeOsPlan(
            id=f"plan_{abs(hash(summary))}",
            user_id=user_id,
            summary="Impegno già pianificato",
            constraints=["Finestra occupata 08:30-09:15"],
            items=[PlanItem(id="existing", title="Concludere impegno precedente")],
        ).model_dump()
    )
    result = await _run_context_question(
        db, session_id=f"new_{abs(hash(question))}", user_id=user_id, message=question
    )
    trace = result.trace or {}
    assert trace.get("context_final_count", 0) > 0
    assert "situations" in (trace.get("context_sources") or [])


@pytest.mark.asyncio
async def test_real_provider_preserves_conflict_as_uncertainty():
    if not await _provider_available():
        pytest.skip("No real LLM provider configured")
    db = FakeDB()
    user_id = "eval_v282_conflict"
    await SituationService(db).apply(
        user_id=user_id,
        session_id="old",
        update=SituationUpdate(
            operation="create",
            summary="L'utente ha indicato l'incontro per martedì",
            source_refs=["user_conversation"],
        ),
        reasoning_epoch="seed_conflict_user",
    )
    await SituationService(db).apply(
        user_id=user_id,
        session_id="old",
        update=SituationUpdate(
            operation="create",
            summary="Un documento indica lo stesso incontro per mercoledì",
            source_refs=["external_evidence"],
        ),
        reasoning_epoch="seed_conflict_document",
    )
    result = await _run_context_question(
        db,
        session_id="new",
        user_id=user_id,
        message="Qual è il giorno definitivo dell'incontro di cui abbiamo parlato?",
        require_targeted_context=False,
    )
    answer = result.ora_text.lower()
    explicit_uncertainty = any(
        word in answer for word in ("conferm", "chiar", "conflitt", "diverg", "non posso", "due")
    )
    preserves_both = "martedì" in answer and "mercoledì" in answer
    assert explicit_uncertainty or preserves_both
