"""Proof of WHAT the background worker attempted, not what the world did.

Regression for ORA Test 2: at 16:09, 16:15 and 16:21 the scheduler logged
'in_progress', but no documented weather observation was available to the
owner. The code must expose ONLY owner-linked wake records for this exact
Situation and retain the distinction from weather evidence.
"""
import pytest
from mongomock_motor import AsyncMongoMockClient

from situations.models import SituationState
from situations.followup import (
    goal_id_for, list_situation_followups, get_situation_followup,
)
from situations.wake_audit import read_situation_wake_audit

OWNER = "wake-history-synthetic-owner"
OTHER = "wake-history-unrelated-user"
SID = "sit_laundry_oct19"
CREATED = "2026-10-16T12:00:00+00:00"
STARTED = "2026-10-19T12:00:00+00:00"
MESSAGE = "Che cosa ha fatto ORA per i panni stesi il 19 ottobre 2026 a Tarquinia?"


def runtime(db, owner=OWNER):
    return {"db": db, "user_id": owner, "user_message": MESSAGE}


async def prepare(db):
    situation = SituationState(
        id=SID, user_id=OWNER, summary="Panni stesi a Tarquinia",
        location_label="Tarquinia", status="cancelled",
        created_at=CREATED, started_at=STARTED,
        updated_at="2026-10-19T20:23:34+00:00",
    )
    await db.situations.insert_one(situation.model_dump())
    return situation


async def wake(db, *, owner=OWNER, sid=SID, scheduled, claimed=None,
               status="completed", result="in_progress", attempts=1):
    gid = goal_id_for(OWNER, sid)  # exact source from the owner's original work
    await db.ambient_wakes.insert_one({
        "owner_id": owner,
        "source_ref": f"goal:{gid}",
        "reason": "opportunity_revisit",
        "scheduled_for": scheduled,
        "claimed_at": claimed or scheduled,
        "completed_at": scheduled if status == "completed" else None,
        "status": status, "last_error": result, "attempts": attempts,
    })


@pytest.mark.asyncio
async def test_closed_oct19_situation_retains_three_exact_wakes_without_false_weather(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().audit_own_wakes
    situation = await prepare(db)
    for utc in ("2026-10-19T14:09:00+00:00",
                "2026-10-19T14:15:00+00:00",
                "2026-10-19T14:21:00+00:00"):
        await wake(db, scheduled=utc)
    # Exclude an older wake for the same reused Situation before its
    # explicit physical start, plus another owner's and another goal's wake.
    await wake(db, scheduled="2026-10-11T17:03:00+00:00")
    await wake(db, owner=OTHER, scheduled="2026-10-19T14:11:00+00:00")
    await wake(db, sid="sit_different", scheduled="2026-10-19T14:12:00+00:00")
    before = {
        coll: await db[coll].count_documents({})
        for coll in ("situations", "ambient_wakes", "agent_goals",
                     "agent_journal", "delivery_plans")
    }

    audit = await read_situation_wake_audit(db, OWNER, situation)
    assert audit["wake_audit_status"] == "records_found"
    assert audit["wake_attempt_count"] == 3, audit
    assert len(audit["wake_attempts"]) == 3
    assert [r["scheduled_for"] for r in audit["wake_attempts"]] == [
        "2026-10-19T14:21:00+00:00",
        "2026-10-19T14:15:00+00:00",
        "2026-10-19T14:09:00+00:00",
    ]
    assert all(row["worker_status"] == "completed" for row in audit["wake_attempts"])
    assert all(row["worker_result"] == "in_progress" for row in audit["wake_attempts"])
    assert not any(row["proves_weather_or_physical_outcome"] for row in audit["wake_attempts"])
    assert "NON" not in audit["wake_audit_note"]  # only clear statement in prose

    list_obs = await list_situation_followups(
        {"place_query": "Tarquinia"}, runtime(db),
    )
    assert list_obs.status == "ok", list_obs
    assert list_obs.payload["count"] == 1
    item = list_obs.payload["items"][0]
    assert item["situation_id"] == SID
    assert item["wake_attempt_count"] == 3
    assert item["monitoring_status"] == "stopped"
    assert item["last_checked_at"] is None
    assert item["last_result"] is None
    assert "other" not in str(item).lower()

    exact = await get_situation_followup(
        {"situation_id": SID, "place_query": "Tarquinia"}, runtime(db),
    )
    assert exact.status == "ok"
    assert exact.payload["wake_attempt_count"] == 3
    assert exact.payload["last_checked_at"] is None
    assert "non" in exact.payload["factual_readback"]["text"].lower()
    assert await db.delivery_plans.count_documents({}) == 0
    for coll, n in before.items():
        assert await db[coll].count_documents({}) == n, coll


@pytest.mark.asyncio
async def test_wake_audit_unavailable_does_not_rewrite_missing_records_or_cross_owner(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().audit_bound
    situation = await prepare(db)
    await wake(db, owner=OTHER, scheduled="2026-10-19T14:09:00+00:00")
    other = await read_situation_wake_audit(db, OTHER, situation)
    assert other["wake_audit_status"] == "unavailable"

    owned = await read_situation_wake_audit(db, OWNER, situation)
    assert owned["wake_audit_status"] == "no_records_in_bounded_history"
    assert owned["wake_attempt_count"] == 0
    assert "nessuna" in owned["wake_audit_note"].lower()
    out = await list_situation_followups({"place_query": "Tarquinia"}, runtime(db))
    assert out.payload["items"][0]["wake_attempt_count"] == 0
    assert await db.ambient_wakes.count_documents({}) == 1


@pytest.mark.asyncio
async def test_bounded_mixed_wake_states_remain_technical_not_physical(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().audit_states
    situation = await prepare(db)
    await wake(db, scheduled="2026-10-19T14:09:00+00:00",
               status="pending", result="", attempts=0)
    await wake(db, scheduled="2026-10-19T14:15:00+00:00",
               status="failed", result="TimeoutError: sensitive content", attempts=2)
    out = await read_situation_wake_audit(db, OWNER, situation, limit=1)
    assert out["wake_attempt_count"] == 1
    assert out["wake_attempts"][0]["worker_result"] == "unavailable"
    assert not out["wake_attempts"][0]["proves_weather_or_physical_outcome"]
    assert "sensitive content" not in str(out)
