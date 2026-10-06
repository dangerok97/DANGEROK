"""V86a — lifecycle wrapper success must count as the real calendar mutation."""

from conversation_engine.ai_core.loop import (
    _CALENDAR_WRITE_CAPS,
    _WRITE_CAPS,
    _calendar_write_observation_succeeded,
    _effective_capability,
)
from conversation_engine.ai_core.models import Observation


def _ok_cancel():
    return Observation(
        kind="tool",
        name="cancel_calendar_event",
        status="ok",
        payload={
            "status": "ok",
            "operation": "cancelled",
            "verified": True,
            "what_was_removed": "TEST ORA — seconda passata",
        },
    )


def test_calendar_continuation_credits_the_leaf_mutation():
    obs = _ok_cancel()

    assert (
        _effective_capability(
            "continue_calendar_action", obs.name, _CALENDAR_WRITE_CAPS
        )
        == "cancel_calendar_event"
    )
    assert (
        _effective_capability("continue_calendar_action", obs.name, _WRITE_CAPS)
        == "cancel_calendar_event"
    )
    assert _calendar_write_observation_succeeded(
        "continue_calendar_action", obs
    ) is True


def test_partial_continuation_is_not_false_success():
    obs = Observation(
        kind="tool",
        name="cancel_calendar_event",
        status="partial",
        payload={"status": "authority_required"},
    )

    assert _calendar_write_observation_succeeded(
        "continue_calendar_action", obs
    ) is False


def test_unrelated_wrapper_cannot_claim_calendar_success():
    obs = Observation(
        kind="tool",
        name="get_calendar_events",
        status="ok",
        payload={"status": "ok"},
    )

    assert _calendar_write_observation_succeeded(
        "continue_calendar_action", obs
    ) is False
