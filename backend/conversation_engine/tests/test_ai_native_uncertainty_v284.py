"""V2.8.4 — unified, AI-owned uncertainty and clarification governance."""

from __future__ import annotations

from copy import deepcopy

import pytest

from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.models import CognitiveDecision, UncertaintyState
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.models import ConversationSession
from conversation_engine.tests.test_ai_native_situation_v281 import FakeDB, _create
from situations.models import SituationUpdate
from situations.service import SituationService


def _uncertainty(*, strategy="defer", blocking=False, assumption=None):
    data = {
        "level": 0.7 if blocking else 0.3,
        "missing_information": [
            {
                "ref": "needed-detail",
                "description": "A detail relevant to the requested outcome",
                "purpose": "complete the current request safely",
                "importance": 0.9 if blocking else 0.3,
                "blocking": blocking,
                "strategy": strategy,
            }
        ],
        "blocking": blocking,
    }
    if assumption:
        data["assumptions"] = [assumption]
    return data


def _decision(mode="answer", **extra):
    raw = {
        "response_mode": mode,
        "user_intent_summary": "arbitrary life request",
        "reasoning_status": "needs_user_input" if mode == "ask" else "enough_information",
        "message_to_user": "Procedo in modo prudente." if mode != "ask" else None,
        "question": "Qual è il dettaglio necessario?" if mode == "ask" else None,
    }
    raw.update(extra)
    return raw


def _sess():
    return ConversationSession(user_id="u-v284", meta={"ui_mode": "ai_core", "ai_core": {}})


def _scripted(items):
    queue = [deepcopy(x) for x in items]

    async def decide(_system, _user):
        return queue.pop(0)

    return decide


def test_a_sufficient_information_needs_no_clarification():
    out = validate_decision(_decision(uncertainty={"level": 0.0}), tools=ToolRegistry())
    assert out.ok and out.decision.response_mode == "answer"
    assert out.decision.uncertainty.level == 0.0


def test_b_blocking_missing_information_can_be_asked_once():
    out = validate_decision(
        _decision("ask", uncertainty=_uncertainty(strategy="ask", blocking=True)),
        tools=ToolRegistry(),
    )
    assert out.ok and out.decision.response_mode == "ask"
    assert out.decision.uncertainty.missing_information[0].ref == "needed-detail"


def test_c_retrievable_information_uses_context_contract():
    out = validate_decision(
        _decision(
            "context",
            message_to_user=None,
            context_need={"query": "bounded evidence relevant to the detail", "max_items": 3},
            uncertainty=_uncertainty(strategy="retrieve", blocking=True),
        ),
        tools=ToolRegistry(),
    )
    assert out.ok and out.decision.response_mode == "context"
    assert out.decision.context_need.max_items == 3


def test_d_non_blocking_information_allows_answer():
    out = validate_decision(
        _decision(uncertainty=_uncertainty(strategy="defer", blocking=False)),
        tools=ToolRegistry(),
    )
    assert out.ok and out.decision.response_mode == "answer"


def test_e_safe_reversible_assumption_is_not_memory():
    assumption = {
        "ref": "working-option",
        "statement": "Use a provisional option for this response",
        "confidence": 0.6,
        "reversible": True,
        "consequential": False,
    }
    decision = CognitiveDecision.model_validate(
        _decision(uncertainty=_uncertainty(assumption=assumption))
    )
    assert decision.uncertainty.assumptions[0].reversible
    assert decision.memory_candidates == []


def test_f_unsafe_assumption_blocks_action():
    assumption = {
        "ref": "unsafe-option",
        "statement": "Guess a consequential parameter",
        "confidence": 0.5,
        "reversible": False,
        "consequential": True,
    }
    out = validate_decision(
        _decision("act", uncertainty=_uncertainty(blocking=True, assumption=assumption)),
        tools=ToolRegistry(),
    )
    assert out.decision.response_mode == "answer"
    assert "blocking_uncertainty_for_action" in out.errors


@pytest.mark.asyncio
async def test_g_clarification_answer_advances_same_conversation_state():
    sess = _sess()
    first = await run_cognitive_loop(
        sess=sess,
        user_message="Aiutami con questa scelta.",
        decision_fn=_scripted([_decision("ask", uncertainty=_uncertainty(strategy="ask", blocking=True))]),
    )
    asked_history = deepcopy(sess.meta["ai_core"]["clarification_history"])
    second = await run_cognitive_loop(
        sess=sess,
        user_message="Il dettaglio è questo.",
        decision_fn=_scripted([_decision(message_to_user="Ora posso continuare.", uncertainty={"level": 0.0})]),
    )
    assert first.mode == "ask" and second.mode == "answer"
    assert len(asked_history[0]["key"]) == 64
    assert "needed-detail" not in str(asked_history)
    assert sess.meta["ai_core"]["clarification_history"] == []


@pytest.mark.asyncio
async def test_h_corrected_assumption_updates_same_situation_revision():
    db = FakeDB()
    service = SituationService(db)
    created = await service.apply(
        user_id="u1", session_id="s1",
        update=_create("Impegno contestuale", assumptions=["orario provvisorio"]),
        reasoning_epoch="e1",
    )
    sid = created["situation"]["id"]
    updated = await service.apply(
        user_id="u1", session_id="s2",
        update=SituationUpdate(
            operation="update", situation_id=sid, expected_revision=1,
            facts=["orario confermato"], supersedes=["orario provvisorio"],
            source_refs=["user_conversation"],
        ),
        reasoning_epoch="e2",
    )
    assert updated["situation"]["id"] == sid
    assert updated["situation"]["revision"] == 2
    assert "orario provvisorio" not in updated["situation"]["assumptions"]


def test_i_repeated_structured_question_is_prevented():
    out = validate_decision(
        _decision("ask", uncertainty=_uncertainty(strategy="ask", blocking=True)),
        tools=ToolRegistry(), clarification_attempts={"needed-detail": 1},
    )
    assert out.decision.response_mode == "answer"
    assert out.decision.question is None
    assert "repeated_clarification" in out.errors


def test_j_user_refusal_can_defer_without_another_question():
    out = validate_decision(
        _decision(uncertainty=_uncertainty(strategy="defer", blocking=False)),
        tools=ToolRegistry(), clarification_attempts={"needed-detail": 1},
    )
    assert out.ok and out.decision.response_mode == "answer"


def test_k_context_failure_remains_explicit_uncertainty():
    decision = CognitiveDecision.model_validate(
        _decision(uncertainty=_uncertainty(strategy="defer", blocking=True))
    )
    assert decision.uncertainty.blocking
    assert decision.claim_grounding is None


def test_l_provider_failure_contract_does_not_invent_certainty():
    from conversation_engine.ai_core.fallback import provider_unavailable_result

    result = provider_unavailable_result(session_id="s1")
    assert result.error == "provider_unavailable"
    assert "riprovare" in result.ora_text.lower()


def test_m_durable_clarification_answer_still_requires_memory_candidate_governance():
    decision = CognitiveDecision.model_validate(
        _decision(
            memory_candidates=[{
                "summary": "A durable user-confirmed preference",
                "identity_key": "preference:generic",
                "authority": "user_confirmed",
                "epistemic_status": "confirmed",
                "permanence": "durable",
                "user_authorized": True,
            }],
            uncertainty={"level": 0.0},
        )
    )
    assert len(decision.memory_candidates) == 1


def test_n_temporary_clarification_answer_is_situation_not_memory():
    decision = CognitiveDecision.model_validate(
        _decision(
            situation_update={
                "operation": "create", "summary": "Temporary contextual commitment",
                "facts": ["temporary answer"], "source_refs": ["user_conversation"],
            },
            uncertainty={"level": 0.0},
        )
    )
    assert decision.situation_update is not None
    assert decision.memory_candidates == []


def test_o_contract_is_cross_session_serializable():
    state = UncertaintyState.model_validate(_uncertainty(strategy="ask", blocking=True))
    restored = UncertaintyState.model_validate(state.model_dump())
    assert restored.missing_information[0].ref == "needed-detail"


def test_p_arbitrary_domain_uses_same_contract_without_router_fields():
    state = UncertaintyState.model_validate({
        "level": 0.4,
        "ambiguities": [{
            "ref": "desired-outcome",
            "description": "The desired outcome is open to multiple interpretations",
            "blocking": False,
        }],
    })
    dumped = state.model_dump()
    assert "domain" not in dumped and "intent_router" not in dumped
