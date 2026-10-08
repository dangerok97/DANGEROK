"""Contract tests for the optional Phase 1 real-model evaluation runner.

These NEVER call an LLM, a production provider or a real user database.
They establish whether the harness accurately reports tool observations and
refuses to certify unverified or world-changing actions.
"""
from types import SimpleNamespace

import pytest

from scripts.phase1_cognitive_live_eval import (
    FIXTURE_SOURCE,
    SCENARIOS,
    _model_signal,
    _scripted_model_factory,
    _verdict,
    run_case,
)


@pytest.mark.asyncio
async def test_real_loop_with_scripted_trip_models_all_three_reads():
    decision_fn = await _scripted_model_factory("trip")
    result = await run_case("trip", decide=decision_fn, max_steps=5)
    verdict = result["verdict"]
    assert result["scope"] == "scripted_model_in_memory_synthetic_tools"
    assert result["owner"] == "synthetic_isolated_no_real_account"
    assert verdict["passed"] is True, result
    assert verdict["model_decisions"] == 4
    assert verdict["tool_calls"] == 3
    assert set(verdict["verified_reads"]) == {
        "get_calendar_events", "get_route", "get_weather_forecast"
    }
    assert all(row["fixture"] == FIXTURE_SOURCE for row in result["observations"])
    assert not any(row["side_effect"] != "READ_ONLY" for row in result["observations"])


@pytest.mark.asyncio
async def test_weather_without_saved_situation_is_not_false_pass():
    result = await run_case(
        "situation", decide=await _scripted_model_factory("situation"),
        max_steps=3,
    )
    assert "get_weather_forecast" in result["verdict"]["verified_reads"]
    assert result["verdict"]["passed"] is False
    assert "situation_not_persisted" in result["verdict"]["reasons"]
    assert "followup_not_actually_scheduled" in result["verdict"]["reasons"]


@pytest.mark.asyncio
async def test_birthday_answer_without_permanent_memo_does_not_pass():
    result = await run_case(
        "birthday", decide=await _scripted_model_factory("birthday"),
        max_steps=1,
    )
    assert result["verdict"]["passed"] is False
    assert "permanent_memory_not_persisted" in result["verdict"]["reasons"]
    assert "annual_reminder_not_persisted" in result["verdict"]["reasons"]


def test_verdict_requires_actual_observations_even_for_successful_model_prose():
    result = SimpleNamespace(
        ok=True, mode="answer", trace={"skill_plan_completed": True},
        ai_calls=1, tool_calls=0,
    )
    verdict = _verdict(
        "trip", result,
        [{"mode": "answer", "capability": "",
          "required": ["get_calendar_events", "get_route", "get_weather_forecast"]}],
        observations=[],
    )
    assert verdict["passed"] is False
    assert "missing_verified_reads:" in verdict["reasons"][0]


def test_safe_boundary_blocks_world_changing_capabilities_from_pass():
    result = SimpleNamespace(
        ok=True, mode="answer", trace={}, ai_calls=2, tool_calls=3,
    )
    samples = [{
        "capability": name, "outer_status": "ok", "result_status": "ok",
        "fixture": FIXTURE_SOURCE, "side_effect": "READ_ONLY",
    } for name in SCENARIOS["trip"]["required_read"]]
    samples.append({
        "capability": "create_calendar_event",
        "outer_status": "failed", "result_status": "failed",
        "fixture": "blocked", "side_effect": "REVERSIBLE_WRITE",
    })
    verdict = _verdict(
        "trip", result, [{"mode": "tool"}], samples,
    )
    assert verdict["passed"] is False
    assert "blocked_world_changing_capability" in verdict["reasons"]


def test_model_signals_do_not_export_private_arguments_or_model_text():
    raw = {
        "response_mode": "tool", "reasoning_status": "needs_tool",
        "tool_call": {
            "capability": "get_route",
            "arguments": {"private_home_address": "do-not-emit"},
        },
        "message_to_user": "do-not-emit",
        "skill_plan": {
            "required_capabilities": ["get_route", "get_weather_forecast"],
            "resume_plan_ref": "opaque-secret-ref",
        },
        "memory_candidates": [{"summary": "do-not-emit"}],
    }
    result = _model_signal(raw)
    assert result["capability"] == "get_route"
    assert result["resume"] is True
    assert result["required"] == ["get_route", "get_weather_forecast"]
    assert result["memory_proposals"] == 1
    assert "do-not-emit" not in str(result)
    assert "opaque-secret-ref" not in str(result)


def test_benchmark_accepts_only_local_persisted_followup_as_scheduled():
    result = SimpleNamespace(
        ok=True, mode="answer", trace={}, ai_calls=3, tool_calls=2,
    )
    events = [{
        "capability": "get_weather_forecast", "outer_status": "ok",
        "result_status": "ok", "fixture": FIXTURE_SOURCE,
        "side_effect": "READ_ONLY",
    }, {
        "capability": "schedule_situation_check", "outer_status": "ok",
        "result_status": "scheduled", "fixture": "synthetic_db_write",
        "side_effect": "REVERSIBLE_WRITE",
    }]
    incomplete = _verdict(
        "situation", result, [{"mode": "tool"}], events,
        situation_count=1, followup_count=0,
    )
    assert incomplete["passed"] is False
    assert "followup_not_actually_scheduled" in incomplete["reasons"]
    complete = _verdict(
        "situation", result, [{"mode": "tool"}], events,
        situation_count=1, followup_count=1,
    )
    assert complete["passed"] is True
    assert complete["synthetic_scheduled_followups"] == 1
