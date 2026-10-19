"""Selective CAL164 port onto current ORA code: no duplicate calendar edits.

Synthetic Mongo owner IDs; no external calendar, user account, or messages.
"""
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from home import manual_event


@pytest.mark.asyncio
async def test_repeated_requested_local_change_keeps_revision_and_one_wake(monkeypatch):
    db = AsyncMongoMockClient().unified_calendar_repeat
    wake = AsyncMock()
    monkeypatch.setattr(manual_event, "_wake", wake)
    created = await manual_event.create_manual_event(
        db, "owner-one", title="TEST ORA calendar",
        start="2026-10-20T18:00:00+02:00",
        end="2026-10-20T18:10:00+02:00",
        tz_name="Europe/Rome", request_id="unified-calendar-001",
    )
    assert created["starts_at"] == "2026-10-20T18:00:00+02:00"
    wake.reset_mock()
    change = {"start_datetime": "2026-10-20T19:00:00+02:00",
              "end_datetime": "2026-10-20T19:10:00+02:00",
              "timezone": "Europe/Rome"}
    current = await manual_event.get_manual_event(db, "owner-one", created["id"])
    assert not manual_event.manual_update_is_noop(current, change)
    moved = await manual_event.update_manual_event(
        db, "owner-one", created["id"], change,
        expected_updated_at=current["updated_at"],
    )
    assert moved["changed_now"] is True
    assert moved["starts_at"] == change["start_datetime"]
    assert moved["ends_at"] == change["end_datetime"]
    assert wake.await_count == 1

    # A second model call is genuinely a no-op, not another wake/write.
    second = await manual_event.update_manual_event(
        db, "owner-one", created["id"], change,
        expected_updated_at=current["updated_at"],  # stale caller's revision
    )
    assert second["changed_now"] is False
    assert second["updated_at"] == moved["updated_at"]
    assert wake.await_count == 1
    row = await manual_event.get_manual_event(db, "owner-one", created["id"])
    assert row["updated_at"] == moved["updated_at"]
    assert manual_event.manual_update_is_noop(row, change)
    assert await manual_event.get_manual_event(db, "owner-two", created["id"]) is None


@pytest.mark.asyncio
async def test_wrong_zone_and_unknown_source_end_do_not_silently_succeed(monkeypatch):
    db = AsyncMongoMockClient().unified_calendar_zone
    wake = AsyncMock()
    monkeypatch.setattr(manual_event, "_wake", wake)
    created = await manual_event.create_manual_event(
        db, "owner", title="Unverified end",
        start="2026-10-20T18:00:00+02:00",
        end="2026-10-20T19:00:00+02:00",
        tz_name="Europe/Rome", request_id="unknown-end",
        end_time_known=False,
    )
    wake.reset_mock()
    before = await manual_event.get_manual_event(db, "owner", created["id"])
    assert before["attributes"]["end_time_known"] is False
    with pytest.raises(ValueError, match="timezone_mismatch"):
        await manual_event.update_manual_event(
            db, "owner", created["id"],
            {"start_datetime": "2026-10-20T12:00:00-04:00",
             "timezone": "Europe/Rome"},
        )
    after = await manual_event.get_manual_event(db, "owner", created["id"])
    assert after["updated_at"] == before["updated_at"]
    assert wake.await_count == 0
    assert manual_event.manual_update_is_noop(after, {
        "start_datetime": "2026-10-20T18:00:00+02:00",
        "timezone": "Europe/Rome",
    })
    assert not manual_event.manual_update_is_noop(after, {
        "end_datetime": "2026-10-20T19:00:00+02:00",
        "timezone": "Europe/Rome",
    })  # explicit user-confirmed end changes previously unknown end
