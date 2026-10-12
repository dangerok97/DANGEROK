"""Malformed prose recovers through existing cognition; providers are synthetic.

The 636 public report proves a structured-message fallback happened, but does
not retain whether the model returned an object or a serialized string. Cover
both possibilities without assigning either one to that historical response.
"""
import json
from unittest.mock import AsyncMock

import pytest

from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.models import ConversationSession
from scripts import phase1_read_provider_eval as runner


@pytest.mark.parametrize("field", ["message_to_user", "question"])
@pytest.mark.parametrize("value", [{"summary": "private draft"}, ["private draft"], 7, True])
def test_copy_fields_reject_wrong_types_before_string_coercion(field, value):
    raw = {"response_mode": "answer", "message_to_user": "Una risposta valida.", field: value}
    governed = validate_decision(raw, tools=ToolRegistry(None))
    assert not governed.ok
    assert f"{field}_must_be_string" in governed.errors
    assert "private draft" not in str(governed.errors)


@pytest.mark.parametrize("value", [None, "Una risposta valida.", "{\"summary\": \"JSON richiesto\"}"])
def test_plain_strings_and_optional_null_keep_the_existing_contract(value):
    governed = validate_decision({"response_mode": "answer", "message_to_user": value},
                                tools=ToolRegistry(None))
    assert governed.ok


@pytest.mark.asyncio
async def test_wrong_type_uses_existing_single_retry_with_precise_feedback():
    calls = []

    async def decide(system, user):
        calls.append((system, json.loads(user)))
        if len(calls) == 1:
            return {"response_mode": "answer", "message_to_user": {"summary": "private draft"}}
        return {"response_mode": "answer", "message_to_user": "Il modello ha corretto la forma della risposta."}

    sess = ConversationSession(user_id="synthetic-reply-shape", meta={"ai_core": {}})
    result = await run_cognitive_loop(sess=sess, user_message="Rispondi in una frase.",
                                     db=None, decision_fn=decide, max_steps=1)
    assert len(calls) == result.ai_calls == 2
    assert result.tool_calls == 0
    assert result.ora_text == "Il modello ha corretto la forma della risposta."
    assert "message_to_user_must_be_string" in calls[1][0]
    assert "private draft" not in calls[1][0]


@pytest.mark.asyncio
async def test_repeated_wrong_type_remains_bounded_without_executing_a_tool():
    calls = []

    async def decide(system, user):
        calls.append(1)
        return {"response_mode": "answer", "message_to_user": {"summary": "private draft"}}

    result = await run_cognitive_loop(
        sess=ConversationSession(user_id="synthetic-repeat-shape", meta={"ai_core": {}}),
        user_message="Rispondi in una frase.", db=None, decision_fn=decide, max_steps=1,
    )
    assert len(calls) == result.ai_calls == 2
    assert result.tool_calls == 0
    assert "private draft" not in result.ora_text
    assert not result.ora_text.startswith("{")


@pytest.mark.asyncio
async def test_invalid_copy_does_not_execute_an_otherwise_known_tool(monkeypatch):
    execute = AsyncMock()
    monkeypatch.setattr(ToolRegistry, "execute", execute)
    calls = []

    async def decide(system, user):
        calls.append(1)
        if len(calls) == 1:
            return {"response_mode": "tool", "message_to_user": {"summary": "invalid"},
                    "tool_call": {"capability": "get_route", "arguments": {"destination": "Museo"}}}
        return {"response_mode": "answer", "message_to_user": "La dichiarazione incompleta è stata corretta."}

    result = await run_cognitive_loop(
        sess=ConversationSession(user_id="synthetic-invalid-copy-tool", meta={"ai_core": {}}),
        user_message="Rispondi senza avviare operazioni.", db=None, decision_fn=decide, max_steps=1,
    )
    execute.assert_not_awaited()
    assert len(calls) == result.ai_calls == 2
    assert result.tool_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_reply,expected_finding", [
    ("{'summary': 'forma da correggere', 'details': []}", "STRUCTURED_MESSAGE_RENDERED_FROM_EVIDENCE"),
    ("Parti ora per evitare il traffico.", "UNSUPPORTED_TRAFFIC_COMPARISON"),
    ("Nelle prossime ore le precipitazioni saranno forti.", "UNVERIFIED_FORECAST_INTENSITY"),
])
async def test_model_corrects_rejected_reply_from_existing_reads(bad_reply, expected_finding):
    reference = await runner._scripted_model_factory()
    observed = []

    async def decide(system, user):
        payload = json.loads(user)
        observed.append(payload)
        answer = await reference(system, user)
        if len(observed) == 3:
            answer["message_to_user"] = bad_reply
        return answer

    result = await runner.run_case(mode="scripted", decide=decide, max_steps=5)
    assert len(observed) == result["verdict"]["ai_calls"] == 4
    repair = next(row for row in observed[-1]["observations"] if row["name"] == "reply_grounding_rejected")
    assert expected_finding in repair["payload"]["findings"]
    assert repair["payload"]["reason"]
    assert "draft" not in repair["payload"], "The guard reports a defect, not replacement prose"
    assert result["verdict"]["tool_calls"] == len(result["http_reads"]) == 2
    assert [row["capability"] for row in result["observations"]] == ["get_route", "get_weather_forecast"]
    assert result["final_answer"].startswith("Nel controllo con dati HTTP sintetici")
    assert result["semantic_review"]["grounding_rewrites"] == 0
    assert result["blocked_operations"] == []


@pytest.mark.asyncio
async def test_ignored_grounding_feedback_gets_one_nudge_then_existing_fallback():
    reference = await runner._scripted_model_factory()
    observed = []

    async def decide(system, user):
        observed.append(json.loads(user))
        answer = await reference(system, user)
        if answer["response_mode"] == "answer":
            answer["message_to_user"] = "{'summary': 'forma da correggere', 'details': []}"
        return answer

    result = await runner.run_case(mode="scripted", decide=decide, max_steps=7)
    assert len(observed) == result["verdict"]["ai_calls"] == 4
    assert result["semantic_review"]["grounding_rewrites"] == 1
    assert "MODEL_CLAIM_REWRITTEN" in result["semantic_review"]["reasons"]
    assert result["verdict"]["semantic_gate_passed"] is False
    assert result["verdict"]["tool_calls"] == 2
    assert "forma da correggere" not in result["final_answer"]


@pytest.mark.asyncio
async def test_last_available_pass_keeps_fallback_without_extra_model_call():
    reference = await runner._scripted_model_factory()
    calls = []

    async def decide(system, user):
        calls.append(1)
        answer = await reference(system, user)
        if answer["response_mode"] == "answer":
            answer["message_to_user"] = "{'summary': 'forma da correggere', 'details': []}"
        return answer

    result = await runner.run_case(mode="scripted", decide=decide, max_steps=3)
    assert len(calls) == result["verdict"]["ai_calls"] == 3
    assert result["semantic_review"]["grounding_rewrites"] == 1
    assert result["verdict"]["tool_calls"] == 2


@pytest.mark.asyncio
async def test_valid_reply_has_no_extra_judgement_or_tool_call():
    result = await runner.run_case(mode="scripted", max_steps=5)
    assert result["verdict"]["ai_calls"] == 3
    assert result["verdict"]["tool_calls"] == 2
    assert result["verdict"]["passed"] is True

