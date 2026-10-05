"""V83: calendar conversation is AI-first; backend validates the effect."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _pending(*, minutes_ago: int = 0):
    created = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {
        "at": created.isoformat(),
        "asked": "Elimino «Dentista» domani alle 10:00 dal calendario Google?",
        "calendar_cancel": {
            "question": "Elimino «Dentista» domani alle 10:00 dal calendario Google?",
            "arguments": {
                "calendar_ref": "calendar:google:ing_dentista",
                "confirmation_snapshot": {
                    "title": "Dentista",
                    "starts_at": "2026-10-06T10:00:00+02:00",
                    "ends_at": "2026-10-06T11:00:00+02:00",
                    "location": "",
                    "description": "",
                    "updated_at": "2026-10-05T17:00:00+00:00",
                },
            },
        },
    }


def test_loop_has_no_calendar_semantic_router_before_ai():
    source = (ROOT / "conversation_engine" / "ai_core" / "loop.py").read_text(
        encoding="utf-8"
    )
    confirmation = (
        ROOT / "conversation_engine" / "ai_core" / "calendar_confirmation.py"
    ).read_text(encoding="utf-8")

    assert "next_decision(" not in source
    assert "calendar_decision =" not in source
    assert "def next_decision" not in confirmation
    # Tool confirmation copy is no longer turned into a CognitiveDecision
    # before the model. Exact material facts are enforced after reasoning.
    assert "frase_pronta = _the_tool_s_own_sentence" not in source


def test_pending_calendar_skill_state_exposes_question_not_frozen_arguments():
    from conversation_engine.ai_core.loop import _pending_calendar_skill_context

    state = _pending()
    visible = _pending_calendar_skill_context({"pending_act": state})

    assert visible["skill"] == "calendar"
    assert visible["capability"] == "continue_calendar_action"
    assert visible["awaiting_user_reply"] is True
    assert "Dentista" in visible["question"]
    assert "calendar_ref" not in str(visible)
    assert "confirmation_snapshot" not in str(visible)
    assert "continue_calendar_action" in visible["instruction"]


@pytest.mark.asyncio
async def test_calendar_continuation_rejects_non_approval_before_effect(monkeypatch):
    from conversation_engine.ai_core.tools import calendar_caps

    called = False

    async def must_not_cancel(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("calendar effect must not run without user approval")

    monkeypatch.setattr(calendar_caps, "cancel_calendar_event", must_not_cancel)

    obs = await calendar_caps.continue_calendar_action(
        {},
        {
            "user_id": "owner",
            "user_message": "no, lascia stare",
            "pending_act": _pending(),
        },
    )

    assert obs.status == "error"
    assert obs.payload["failure_kind"] == "USER_CONFIRMATION_REQUIRED"
    assert called is False


@pytest.mark.asyncio
async def test_calendar_continuation_rejects_stale_proposal(monkeypatch):
    from conversation_engine.ai_core.tools import calendar_caps

    called = False

    async def must_not_cancel(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("stale proposal must be re-read")

    monkeypatch.setattr(calendar_caps, "cancel_calendar_event", must_not_cancel)

    obs = await calendar_caps.continue_calendar_action(
        {},
        {
            "user_id": "owner",
            "user_message": "sì",
            "pending_act": _pending(minutes_ago=16),
        },
    )

    assert obs.status == "error"
    assert obs.payload["failure_kind"] == "PENDING_CALENDAR_ACTION_EXPIRED"
    assert called is False


@pytest.mark.asyncio
async def test_calendar_continuation_uses_exact_frozen_backend_arguments(monkeypatch):
    from conversation_engine.ai_core.models import Observation
    from conversation_engine.ai_core.tools import calendar_caps

    pending = _pending()
    frozen = pending["calendar_cancel"]["arguments"]
    captured = {}

    async def fake_cancel(arguments, runtime):
        captured["arguments"] = arguments
        captured["runtime"] = runtime
        return Observation(
            kind="tool",
            name="cancel_calendar_event",
            status="ok",
            payload={
                "status": "ok",
                "operation": "cancelled",
                "verified": True,
                "calendar_ref": arguments["calendar_ref"],
                "what_was_removed": "Dentista",
            },
        )

    monkeypatch.setattr(calendar_caps, "cancel_calendar_event", fake_cancel)

    runtime = {
        "user_id": "owner",
        "user_message": "sì",
        "pending_act": pending,
    }
    obs = await calendar_caps.continue_calendar_action({}, runtime)

    assert obs.status == "ok"
    assert captured["arguments"] == frozen
    assert captured["arguments"] is not frozen
    assert captured["runtime"] is runtime
    assert captured["arguments"]["confirmation_snapshot"]["title"] == "Dentista"


def test_registry_exposes_calendar_continuation_as_skill():
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    catalogue = {
        row["capability"]: row for row in ToolRegistry(db=None).list_public()
    }
    assert "continue_calendar_action" in catalogue
    skill = catalogue["continue_calendar_action"]
    assert skill["side_effect"] == "REVERSIBLE_WRITE"


def test_calendar_confirmation_module_only_extracts_governed_pending_request():
    from conversation_engine.ai_core.calendar_confirmation import pending_request

    request = _pending()["calendar_cancel"]
    obs = {
        "name": "cancel_calendar_event",
        "payload": {
            "status": "authority_required",
            "confirmation_request": request,
        },
    }
    assert pending_request([obs]) == request

    # A completed write is not another pending confirmation.
    completed = {
        "name": "cancel_calendar_event",
        "payload": {"status": "ok", "verified": True},
    }
    assert pending_request([completed]) is None



def test_no_user_facing_conversation_can_finish_before_first_ai_decision():
    source = (
        ROOT / "conversation_engine" / "ai_core" / "loop.py"
    ).read_text(encoding="utf-8")

    first_ai = source.index("raw = await _call_ai(")
    prefix = source[:first_ai]

    assert "return CognitiveTurnResult(" not in prefix
    assert "CognitiveDecision(" not in prefix
    assert "PHONE_FOLLOWUP_FAST_PATH" not in prefix
    assert "NAVIGATION_FAST_PATH" not in prefix
    assert "calendar_decision =" not in prefix
