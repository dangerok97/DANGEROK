"""Offset-aware autonomous execution and explicit deferral, no external calls.

The point is the real instant, not the lexicographic ISO spelling. All users,
goals and wakes here are synthetic; no physical state or notification is made.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.background import _utc_instant, advance_wake
from agent.models import AutonomousGoal
from agent.repository import AgentRepository
from agent.service import AgentService
from ambient.models import AmbientWake


OWNER = "synthetic-timezone-owner"
FROZEN = datetime(2026, 10, 12, 21, 30, tzinfo=timezone.utc)


class FixedUtcClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN if tz is None else FROZEN.astimezone(tz)


def goal(goal_id, *, due, deferred=None):
    return AutonomousGoal(
        id=goal_id, owner_id=OWNER, status="active",
        objective="Recheck an unresolved situation",
        desired_outcome="A verified useful result",
        next_run_at=due, user_deferred_until=deferred,
    )


@pytest.mark.parametrize("written,expected", [
    ("2026-10-12T23:20:00+02:00", datetime(2026, 10, 12, 21, 20, tzinfo=timezone.utc)),
    ("2026-10-12T18:00:00-04:00", datetime(2026, 10, 12, 22, 0, tzinfo=timezone.utc)),
    ("2026-10-12T21:30:00Z", FROZEN),
    ("2026-10-12T21:30:00", None),
    ("not-a-date", None),
])
def test_utc_instant_is_timezone_aware_or_explicitly_unavailable(written, expected):
    assert _utc_instant(written) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("due,defer,expected", [
    # Local +02 date appears *later* than the UTC clock as text, but is due.
    ("2026-10-12T23:20:00+02:00", None, "advanced"),
    # Local -04 date appears *earlier* as text, but is still in the future.
    ("2026-10-12T18:00:00-04:00", None, "goal_not_due"),
    # The person postponed: a stale past deadline must not defeat that choice.
    ("2026-10-12T23:20:00+02:00", "2026-10-13T00:00:00+02:00", "goal_not_due"),
    ("2026-10-12T21:15:00", None, "goal_time_unverified"),
    ("2026-10-12T23:20:00+02:00", "unknown", "defer_time_unverified"),
])
async def test_wake_dispatch_uses_instants_and_honors_person_defer(
    monkeypatch, due, defer, expected
):
    import agent.background as background

    monkeypatch.setattr(background, "datetime", FixedUtcClock)
    db = AsyncMongoMockClient().synthetic_offset_wake
    # Use a legacy raw row: a new AgentRepository write is normalized to UTC.
    original = goal("gol_offset_test", due=due, deferred=defer)
    await db.agent_goals.insert_one(original.model_dump())
    advanced = AsyncMock(return_value={"ok": True, "state": "advanced"})
    monkeypatch.setattr(AgentService, "advance", advanced)
    wake = AmbientWake(owner_id=OWNER, reason="opportunity_revisit",
                       source_ref=f"goal:{original.id}", scheduled_for=FROZEN.isoformat())

    result = await advance_wake(db, wake)
    assert result.result == expected
    if expected == "advanced":
        advanced.assert_awaited_once()
        assert advanced.await_args.args[:2] == (OWNER, original.id)
    else:
        advanced.assert_not_awaited()
    if expected.endswith("_unverified"):
        assert result.retry_after_seconds == 300
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert await db.agent_goals.count_documents({"owner_id": "another-owner"}) == 0


@pytest.mark.asyncio
async def test_legacy_goal_reads_normalize_in_memory_for_later_agent_checks_without_mutating_store():
    db = AsyncMongoMockClient().synthetic_legacy_offset
    repo = AgentRepository(db)
    raw_due = "2026-10-12T23:20:00+02:00"
    raw_defer = "2026-10-13T00:00:00+02:00"
    older = goal("gol_legacy_offset", due=raw_due, deferred=raw_defer)
    await db.agent_goals.insert_one(older.model_dump())

    loaded = await repo.get_goal(OWNER, older.id)
    assert loaded.next_run_at == "2026-10-12T21:20:00+00:00"
    assert loaded.user_deferred_until == "2026-10-12T22:00:00+00:00"
    opened = await repo.open_goals(OWNER)
    assert len(opened) == 1
    assert opened[0].next_run_at == loaded.next_run_at
    # The model/worker gets one canonical instant while storage remains
    # untouched until a legitimate owned write occurs.
    stored = await db.agent_goals.find_one({"owner_id": OWNER, "id": older.id})
    assert stored["next_run_at"] == raw_due
    assert stored["user_deferred_until"] == raw_defer


@pytest.mark.asyncio
async def test_new_and_deferred_goals_are_saved_in_canonical_utc_and_stale_workers_cannot_erase_defer():
    db = AsyncMongoMockClient().synthetic_canonical_goal
    await db.agent_goals.create_index("id", unique=True)
    repo = AgentRepository(db)
    pending = goal("gol_local_clock", due=(datetime.now(timezone.utc) + timedelta(hours=4))
                   .astimezone(timezone(timedelta(hours=2))).isoformat())
    assert await repo.create_goal(pending)
    first = await repo.get_goal(OWNER, pending.id)
    assert first.next_run_at.endswith("+00:00")
    assert datetime.fromisoformat(first.next_run_at) == datetime.fromisoformat(
        pending.next_run_at
    )

    local_due = (datetime.now(timezone.utc) + timedelta(hours=5)).astimezone(
        timezone(timedelta(hours=2))
    ).replace(microsecond=0)
    accepted = await repo.defer_goal(OWNER, pending.id, until=local_due.isoformat())
    assert accepted is not None
    expected_utc = local_due.astimezone(timezone.utc).isoformat()
    assert accepted.next_run_at == accepted.user_deferred_until == expected_utc
    # An old worker with the original goal object cannot overwrite the human.
    stale = goal(pending.id, due=datetime.now(timezone.utc).isoformat())
    await repo.save_goal(stale)
    saved = await repo.get_goal(OWNER, pending.id)
    assert saved.next_run_at == saved.user_deferred_until == expected_utc
    assert saved.status == "waiting"
    assert (await repo.defer_goal(OWNER, pending.id, until="2026-10-12T18:00:00")) is None
    assert (await repo.get_goal(OWNER, pending.id)).user_deferred_until == expected_utc
