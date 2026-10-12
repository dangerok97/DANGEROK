"""Synthetic conversation diagnostics; no model, provider or physical effect.

The real public_trace can omit late events. The runner observes its input in
the exact conversation task, forwards the original call, and exports no copy.
"""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
from mongomock_motor import AsyncMongoMockClient
import pytest

from conversation_engine.ai_core import loop, trace as trace_module
from conversation_engine.ai_core.models import CognitiveTurnResult
from scripts import situation_live_eval_v162 as runner


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(httpx.AsyncClient, "send", AsyncMock(side_effect=AssertionError("No network")))


async def world():
    db = AsyncMongoMockClient().situation_conversation_diagnostics
    await db.eval_guards.insert_one({"_id": runner.VERSION, "owner": runner.OWNER})
    return db, SimpleNamespace(user_id=runner.OWNER)


def test_trace_projection_keeps_terminal_events_and_counts_without_free_payloads():
    private = "private-token-or-source-text" * 200
    steps = [{"event": "TURN", "user_message": private}]
    steps += [{"event": "DUPLICATE_SOFT", "capability": "get_weather_forecast",
               "observation": private} for _ in range(16)]
    steps += [{"event": "BARE_ACK_BLOCKED_TERMINAL", "message": private},
              {"event": "FINAL", "mode": "answer", "guidance_outcome": "continue", "text": private},
              {"event": "SITUATION_SCHEDULE_STATUS_BOUND"},
              {"event": "LOOP_BOUND", "guidance_outcome": "continue"}]
    raw = {"steps": steps, "secrets": private, "context_sources": [private]}
    before = deepcopy(raw)
    result = runner._conversation_trace(raw)
    assert raw == before
    assert result["source"] == "public_trace_input"
    assert result["steps_total"] == 21 and result["steps_excluded"] == 1
    assert len(result["events"]) == runner.MAX_DECISION_OBSERVATIONS == 12
    assert result["events_omitted"] == 8
    assert result["event_counts"] == {"DUPLICATE_SOFT": 16, "BARE_ACK_BLOCKED_TERMINAL": 1,
        "FINAL": 1, "SITUATION_SCHEDULE_STATUS_BOUND": 1, "LOOP_BOUND": 1}
    assert [row["sequence"] for row in result["events"]] == list(range(10, 22))
    assert result["events"][-1] == {"sequence": 21, "event": "LOOP_BOUND", "guidance_outcome": "continue"}
    assert result["trace_fields_excluded"] == 2 and result["event_fields_excluded"] == 18
    encoded = json.dumps(result)
    assert len(encoded) < 5000 and "private-token" not in encoded
    assert "context_sources" not in encoded and "secrets" not in encoded


def test_projection_excludes_unknown_codes_types_and_result_content():
    result = runner._conversation_result_fields(SimpleNamespace(ok="true", mode=["answer"],
        error="Bearer private failure", ai_calls=True, tool_calls=-1, ora_text="private draft",
        session_id="private-session", sources=["private source"]))
    assert result == {"ok": None, "mode": None, "error": None, "error_present": True,
                      "error_omitted": True, "ai_calls": None, "tool_calls": None}
    raw = {"steps": [None, {"event": "PRIVATE_EVENT", "payload": "secret"},
        {"event": "TOOL", "name": "unknown-private-tool", "status": {"secret": True}},
        {"event": "FINAL", "mode": "unrecognised", "guidance_outcome": ["act"]}]}
    projected = runner._conversation_trace(raw)
    assert projected["steps_excluded"] == 2
    assert projected["events"] == [{"sequence": 3, "event": "TOOL"}, {"sequence": 4, "event": "FINAL"}]
    assert "secret" not in json.dumps(projected)
    assert runner._conversation_trace({"steps": "not a list"})["status"] == "steps_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("trace_enabled", ["0", "1"])
async def test_original_public_trace_and_result_are_unchanged_but_late_event_is_observed(monkeypatch, trace_enabled):
    db, session = await world()
    monkeypatch.setenv("AI_CORE_TRACE", trace_enabled)
    raw = {"steps": [{"event": "CONTEXT", "payload": "private"} for _ in range(14)]
        + [{"event": "DUPLICATE_REUSED", "capability": "get_weather_forecast"},
           {"event": "BARE_ACK_BLOCKED_TERMINAL"}, {"event": "FINAL", "mode": "answer"}],
        "ai_calls": 7, "tool_calls": 3}
    before = deepcopy(raw)
    original = Mock(wraps=trace_module.public_trace)
    monkeypatch.setattr(loop, "public_trace", original)
    response = CognitiveTurnResult(ok=False, mode="answer", error="loop_bound", ai_calls=7, tool_calls=3)
    expected_kwargs = {"user_message": "synthetic declaration", "decision_fn": object(), "max_steps": 7}

    async def conversation(**kwargs):
        assert kwargs == {"sess": session, "db": db, **expected_kwargs}
        response.trace = loop.public_trace(raw)
        return response

    call = AsyncMock(side_effect=conversation)
    monkeypatch.setattr(loop, "run_cognitive_loop", call)
    report = {}
    returned = await runner.observe_conversation(db, session, report, **expected_kwargs)
    assert returned is response and call.await_count == 1
    assert loop.public_trace is original and original.call_count == 1 and raw == before
    # Public output still has its original privacy/length policy.
    assert not any(row.get("event") == "FINAL" for row in response.trace.get("steps", []))
    assert __import__("os").environ["AI_CORE_TRACE"] == trace_enabled
    diagnostic = report["conversation_result"]
    assert {key: diagnostic[key] for key in ("ok", "mode", "error", "ai_calls", "tool_calls")} == {
        "ok": False, "mode": "answer", "error": "loop_bound", "ai_calls": 7, "tool_calls": 3}
    assert [row["event"] for row in diagnostic["trace"]["events"]] == [
        "DUPLICATE_REUSED", "BARE_ACK_BLOCKED_TERMINAL", "FINAL"]


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["foreign_owner", "missing_marker", "foreign_marker", "wrong_database"])
async def test_scope_failure_exports_no_result_or_trace_and_does_not_change_turn(monkeypatch, boundary):
    db, session = await world()
    if boundary == "foreign_owner":
        session.user_id = "foreign-owner"
    elif boundary in ("missing_marker", "foreign_marker"):
        await db.eval_guards.delete_many({})
        if boundary == "foreign_marker":
            await db.eval_guards.insert_one({"_id": runner.VERSION, "owner": "foreign-owner"})
    else:
        db = object()
    original = loop.public_trace
    response = CognitiveTurnResult(ora_text="private foreign content", ai_calls=6)

    async def conversation(**kwargs):
        assert loop.public_trace is original
        response.trace = loop.public_trace({"steps": [{"event": "FINAL"}]})
        return response

    monkeypatch.setattr(loop, "run_cognitive_loop", conversation)
    report = {}
    assert await runner.observe_conversation(db, session, report) is response
    assert report == {"conversation_result": {"status": "scope_not_observed"}}
    assert loop.public_trace is original


@pytest.mark.asyncio
@pytest.mark.parametrize("unrelated", ["child_task", "thread"])
async def test_other_task_or_thread_trace_is_not_attributed_to_the_conversation(monkeypatch, unrelated):
    db, session = await world()

    async def conversation(**kwargs):
        result = CognitiveTurnResult()
        result.trace = loop.public_trace({"steps": [{"event": "FINAL", "mode": "answer"}]})

        async def other_task():
            return loop.public_trace({"steps": [{"event": "PROVIDER_FAIL"}]})

        if unrelated == "child_task":
            await asyncio.create_task(other_task())
        else:
            await asyncio.to_thread(loop.public_trace, {"steps": [{"event": "PROVIDER_FAIL"}]})
        return result

    monkeypatch.setattr(loop, "run_cognitive_loop", conversation)
    report = {}
    await runner.observe_conversation(db, session, report)
    assert report["conversation_result"]["trace"]["event_counts"] == {"FINAL": 1}
    assert report["conversation_result"]["public_trace_calls"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["owner_changed", "marker_removed", "projection_error"])
async def test_late_scope_or_diagnostic_failure_does_not_change_result(monkeypatch, boundary):
    db, session = await world()
    response = CognitiveTurnResult(ok=True, ai_calls=2)
    original = loop.public_trace
    if boundary == "projection_error":
        monkeypatch.setattr(runner, "_conversation_trace", Mock(side_effect=RuntimeError("private exception")))

    async def conversation(**kwargs):
        response.trace = loop.public_trace({"steps": [{"event": "FINAL"}]})
        if boundary == "owner_changed":
            session.user_id = "foreign-owner"
        elif boundary == "marker_removed":
            await db.eval_guards.delete_many({})
        return response

    monkeypatch.setattr(loop, "run_cognitive_loop", conversation)
    report = {}
    assert await runner.observe_conversation(db, session, report) is response
    assert loop.public_trace is original
    if boundary == "projection_error":
        assert report["conversation_result"]["ok"] is True
        assert report["conversation_result"]["trace"] == {"status": "projection_unavailable"}
        assert "private exception" not in json.dumps(report)
    else:
        assert report == {"conversation_result": {"status": "scope_not_observed"}}


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("private failure"), asyncio.CancelledError("cancelled")])
async def test_original_exception_identity_and_wrapper_restoration(monkeypatch, error):
    db, session = await world()
    original = loop.public_trace
    call = AsyncMock(side_effect=error)
    monkeypatch.setattr(loop, "run_cognitive_loop", call)
    report = {}
    with pytest.raises(type(error)) as caught:
        await runner.observe_conversation(db, session, report)
    assert caught.value is error and call.await_count == 1
    assert loop.public_trace is original and report == {}


@pytest.mark.asyncio
async def test_run_case_keeps_failed_verdict_and_records_available_result_before_assertion(monkeypatch):
    response = CognitiveTurnResult(ok=False, error="provider_unavailable", ai_calls=7, tool_calls=2)

    async def conversation(**kwargs):
        response.trace = loop.public_trace({"steps": [{"event": "PROVIDER_FAIL"}], "ai_calls": 7, "tool_calls": 2})
        return response

    monkeypatch.setattr(loop, "run_cognitive_loop", conversation)
    report = await runner.run_case()
    assert report["error"] == "CONVERSATION_NOT_OK"
    assert report["passed"] is report["full_laundry_outcome_passed"] is False
    assert report["overall_outcome"] == "failed"
    assert report["phases"]["conversation"]["status"] == "failed"
    assert report["phases"]["monitoring"] == report["phases"]["future_check"] == {"status": "not_run"}
    assert report["logical_model_calls"] == report["model_http_requests"] == report["real_notifications_sent"] == 0
    assert report["conversation_result"]["error"] == "provider_unavailable"
    assert report["conversation_result"]["trace"]["event_counts"] == {"PROVIDER_FAIL": 1}
