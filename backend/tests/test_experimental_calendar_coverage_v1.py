"""Selective #279 regression: calendar absence must have source coverage.

The governed calendar reader is mocked, but its exact user and 48-hour
scope remain visible. No authenticated mailbox, external calendar or
calendar write occurs. An empty *successful* read and a failed read are
never interchangeable facts for the shared cognitive Core.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from conversation_engine.ai_core import calendar_ahead
from conversation_engine.ai_core.tools import calendar_caps


def observation(*, status="ok", payload=None):
    return SimpleNamespace(status=status, payload=payload)


@pytest.mark.asyncio
async def test_empty_window_has_current_observation_not_global_absence(monkeypatch):
    db = object()
    owner = "synthetic-calendar-owner"
    read = AsyncMock(return_value=observation(payload={
        "status": "ok", "events": [], "truncated": False,
    }))
    monkeypatch.setattr(calendar_caps, "get_calendar_events", read)
    state = await calendar_ahead.the_next_two_days(db, owner)
    assert state["status"] == "observed_empty_window"
    assert state["events"] == []
    assert state["source_capability"] == "get_calendar_events"
    assert state["historical_conversation_is_current_evidence"] is False
    assert "NOT the whole calendar" in state["this_is_only_the_next_48_hours"]
    assert "get_calendar_events" in state["this_is_only_the_next_48_hours"]
    assert state["observed_at"]
    assert datetime.fromisoformat(state["observed_at"]).tzinfo is not None
    assert state["may_be_truncated"] is False
    read.assert_awaited_once()
    args, kw = read.await_args.args, read.await_args.kwargs
    assert not kw
    assert args[1]["db"] is db and args[1]["user_id"] == owner
    assert (
        datetime.fromisoformat(args[0]["time_max"])
        - datetime.fromisoformat(args[0]["time_min"])
    ).total_seconds() == 48 * 3600


@pytest.mark.asyncio
@pytest.mark.parametrize("status,payload", [
    ("error", {"status": "error", "events": []}),
    ("partial", {"status": "ok", "events": []}),
    ("ok", {"status": "unavailable", "events": []}),
    ("ok", {"status": "ok"}),
    ("ok", {"status": "ok", "events": "not-a-list"}),
])
async def test_failed_partial_or_malformed_calendar_cannot_claim_empty(
    monkeypatch, status, payload,
):
    monkeypatch.setattr(calendar_caps, "get_calendar_events",
                        AsyncMock(return_value=observation(status=status, payload=payload)))
    result = await calendar_ahead.the_next_two_days(object(), "synthetic-owner")
    assert result["status"] == "unavailable"
    assert result["observed_at"] is None
    assert result["events"] == []
    assert result["reason"]
    assert result["historical_conversation_is_current_evidence"] is False


@pytest.mark.asyncio
async def test_calendar_read_exception_stays_unavailable_not_none(monkeypatch):
    monkeypatch.setattr(calendar_caps, "get_calendar_events",
                        AsyncMock(side_effect=RuntimeError("synthetic read failure")))
    state = await calendar_ahead.the_next_two_days(object(), "synthetic-owner")
    assert state["status"] == "unavailable"
    assert "earlier conversation" in state["reason"]
    assert state["observed_at"] is None
    assert await calendar_ahead.the_next_two_days(None, "synthetic-owner") is None
    assert await calendar_ahead.the_next_two_days(object(), "") is None


@pytest.mark.asyncio
async def test_successful_events_keep_deduplication_and_source_zone(monkeypatch):
    item = {
        "calendar_ref": "ora:synthetic",
        "title": "TEST ORA meeting",
        "start_datetime": "2026-10-20T18:00:00+02:00",
        "end_datetime": "2026-10-20T18:10:00+02:00",
        "timezone": "Europe/Rome",
    }
    monkeypatch.setattr(calendar_caps, "get_calendar_events", AsyncMock(
        return_value=observation(payload={
            "status": "ok", "events": [item, dict(item)],
            "truncated": False,
        }),
    ))
    state = await calendar_ahead.the_next_two_days(object(), "synthetic-owner")
    assert state["status"] == "observed_events"
    assert state["events"] == [item]
    assert state["observed_at"]
    assert state["may_be_truncated"] is False
    assert state["historical_conversation_is_current_evidence"] is False


@pytest.mark.asyncio
async def test_reader_truncation_remains_explicit(monkeypatch):
    monkeypatch.setattr(calendar_caps, "get_calendar_events", AsyncMock(
        return_value=observation(payload={
            "status": "ok", "events": [],
            "truncated": True,
        }),
    ))
    state = await calendar_ahead.the_next_two_days(object(), "synthetic-owner")
    assert state["status"] == "observed_empty_window"
    assert state["may_be_truncated"] is True
