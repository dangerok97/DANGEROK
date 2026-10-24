"""Records that only grew now have an end.

Production census 23/10/2026, one account: 212,040 permission-audit rows and
6,521 Home snapshots, nothing ever removed.
"""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from ops import retention

NOW = datetime(2026, 10, 23, 16, 0, tzinfo=timezone.utc)


def at(days):
    return (NOW - timedelta(days=days)).isoformat()


@pytest.mark.asyncio
async def test_old_snapshots_go_but_the_latest_ones_stay():
    db = AsyncMongoMockClient().retention_v1
    rows = [{"user_id": "active", "generated_at": at(d)} for d in range(0, 60)]
    rows += [{"user_id": "dormant", "generated_at": at(100 + d)} for d in range(25)]
    rows += [{"user_id": "small", "generated_at": at(90 + d)} for d in range(3)]
    await db.home_snapshots.insert_many(rows)
    removed = await retention.prune_home_snapshots(db, now=NOW)
    left = {u: await db.home_snapshots.count_documents({"user_id": u}) for u in ("active", "dormant", "small")}
    assert left == {"active": 31, "dormant": 20, "small": 3}  # day 30 sits on the cutoff
    assert removed == 29 + 5
    newest = await db.home_snapshots.find({"user_id": "dormant"}).sort("generated_at", -1).to_list(1)
    assert newest[0]["generated_at"] == at(100)
    assert await retention.prune_home_snapshots(db, now=NOW) == 0


@pytest.mark.asyncio
async def test_only_audit_rows_past_their_own_retention_are_removed():
    db = AsyncMongoMockClient().retention_v1_audit
    await db.permission_audit.insert_many([
        {"event_id": "a", "retention_until": at(1)},
        {"event_id": "b", "retention_until": at(-1)},
        {"event_id": "c", "retention_until": at(-300)},
    ])
    report = await retention.run(db, now=NOW)
    assert report["permission_audit"] == 1
    assert sorted(r["event_id"] for r in await db.permission_audit.find().to_list(None)) == ["b", "c"]


def test_runtime_schedules_the_retention_lane():
    import inspect
    from ambient import runtime
    assert "ops.retention" in inspect.getsource(runtime._cycle)
    every = runtime._retention_every_ticks()
    assert every > 1 and every // 2 != 0  # never at start-up, never a new lane
