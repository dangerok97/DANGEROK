"""V91 — skill execution outcome, not invocation, determines plan completion."""

from conversation_engine.ai_core.loop import (
    _required_skill_plan_satisfied,
    _required_skill_states,
    _skill_outcome_class,
)


def outcome(capability, status="ok", result_status="ok", failure_kind="", observed=None):
    return {
        "capability": capability,
        "observed_capability": observed or capability,
        "status": status,
        "result_status": result_status,
        "failure_kind": failure_kind,
    }


def test_successful_observation_satisfies_required_skill():
    states = _required_skill_states(
        ["get_calendar_events"],
        [outcome("get_calendar_events")],
    )
    assert states == {
        "succeeded": ["get_calendar_events"],
        "waiting": [],
        "failed": [],
        "unseen": [],
    }
    assert _required_skill_plan_satisfied(
        ["get_calendar_events"],
        [outcome("get_calendar_events")],
    )


def test_failed_observation_is_attempted_but_not_satisfied():
    failed = outcome(
        "open_navigation",
        status="failed",
        result_status="provider_error",
        failure_kind="ROUTE_UNAVAILABLE",
    )
    assert _skill_outcome_class(failed) == "failed"
    states = _required_skill_states(["open_navigation"], [failed])
    assert states["failed"] == ["open_navigation"]
    assert not _required_skill_plan_satisfied(["open_navigation"], [failed])


def test_confirmation_or_client_wait_does_not_satisfy_skill():
    waiting = outcome(
        "cancel_calendar_event",
        status="partial",
        result_status="authority_required",
    )
    assert _skill_outcome_class(waiting) == "waiting"
    states = _required_skill_states(["cancel_calendar_event"], [waiting])
    assert states["waiting"] == ["cancel_calendar_event"]
    assert not _required_skill_plan_satisfied(
        ["cancel_calendar_event"], [waiting]
    )


def test_latest_retry_success_overrides_prior_failure():
    outcomes = [
        outcome(
            "get_route",
            status="failed",
            result_status="provider_error",
            failure_kind="TEMPORARY_FAILURE",
        ),
        outcome("get_route", status="ok", result_status="ok"),
    ]
    states = _required_skill_states(["get_route"], outcomes)
    assert states["succeeded"] == ["get_route"]
    assert states["failed"] == []
    assert _required_skill_plan_satisfied(["get_route"], outcomes)


def test_leaf_observation_can_satisfy_required_concrete_skill():
    wrapped = outcome(
        "continue_calendar_action",
        status="ok",
        result_status="ok",
        observed="cancel_calendar_event",
    )
    states = _required_skill_states(["cancel_calendar_event"], [wrapped])
    assert states["succeeded"] == ["cancel_calendar_event"]


def test_unseen_skill_remains_incomplete():
    states = _required_skill_states(
        ["search_my_life", "get_calendar_events"],
        [outcome("search_my_life")],
    )
    assert states["succeeded"] == ["search_my_life"]
    assert states["unseen"] == ["get_calendar_events"]
    assert not _required_skill_plan_satisfied(
        ["search_my_life", "get_calendar_events"],
        [outcome("search_my_life")],
    )


def test_failure_nudge_contract_exists_in_runtime_and_prompt():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    loop = (root / "conversation_engine" / "ai_core" / "loop.py").read_text(
        encoding="utf-8"
    )
    prompt = (root / "conversation_engine" / "ai_core" / "prompt.py").read_text(
        encoding="utf-8"
    )

    assert "DECLARED_SKILL_PLAN_FAILED" in loop
    assert 'event="SKILL_PLAN_FAILURE_NUDGE"' in loop
    assert "ATTEMPTED is not SUCCEEDED" in prompt
    assert "Never turn" in prompt and "the tool ran" in prompt


def test_successful_envelope_does_not_hide_provider_error():
    # The Python adapter returned without throwing; the provider did not.
    item = outcome(
        "get_route", status="ok", result_status="provider_error",
    )
    assert _skill_outcome_class(item) == "failed"
    assert not _required_skill_plan_satisfied(["get_route"], [item])


def test_incomplete_adapter_payload_does_not_complete_required_skill():
    item = outcome(
        "search_accommodations", status="ok", result_status="partial",
    )
    assert _skill_outcome_class(item) == "failed"
    assert _required_skill_states(
        ["search_accommodations"], [item]
    )["failed"] == ["search_accommodations"]


def test_pending_provider_outcome_is_waiting_not_done():
    item = outcome(
        "continue_calendar_action", status="ok", result_status="pending",
    )
    assert _skill_outcome_class(item) == "waiting"
    assert not _required_skill_plan_satisfied(
        ["continue_calendar_action"], [item]
    )


def test_successful_empty_lookup_remains_valid_read_evidence():
    # A correctly completed search can report not_found without provider failure.
    item = outcome(
        "get_calendar_events", status="ok", result_status="not_found",
    )
    assert _skill_outcome_class(item) == "succeeded"
    assert _required_skill_plan_satisfied(["get_calendar_events"], [item])


def test_failed_inner_result_then_real_success_is_valid_retry():
    previous = outcome(
        "get_route", status="ok", result_status="provider_error",
    )
    current = outcome("get_route", status="ok", result_status="ok")
    assert _required_skill_states(
        ["get_route"], [previous, current]
    )["succeeded"] == ["get_route"]
