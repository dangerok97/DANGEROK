"""UTC-indexed Ambient wake times and timezone-labelled historical audit.

Regression: a real wake scheduled for 16:09 Europe/Rome is 14:09 UTC
on 19 October 2026. Lexical ISO comparisons across '+02:00' and '+00:00'
must not delay a due job or make ORA report 16:09 as '16:09 UTC'.
All cases are synthetic, owner-scoped and avoid external notifications.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient
from motor.motor_asyncio import AsyncIOMotorClient

from ambient.models import AmbientWake
from ambient.repository import AmbientRepository, _utc_schedule
from ambient.service import AmbientService
from situations.followup import goal_id_for
from situations.models import SituationState
from situations.wake_audit import read_situation_wake_audit

OWNER = "synthetic-rome-clock-owner"
SID = "sit_rome_clock"
ROME = ZoneInfo("Europe/Rome")


@pytest_asyncio.fixture
async def mongo_clock_db():
    """Real ephemeral Mongo instance from CI, never a user or Railway DB."""
    url = os.environ.get("MONGO_URL")
    if not url:
        pytest.skip("real UTC claim test requires explicit CI MONGO_URL")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=5000)
    await client.admin.command("ping")
    db = client["ora_ci_wake_utc_" + uuid.uuid4().hex[:20]]
    try:
        yield db
    finally:
        await client.drop_database(db.name)
        client.close()


@pytest.mark.asyncio
async def test_offset_schedule_is_saved_as_utc_and_claimed_at_correct_instant(mongo_clock_db):
    db = mongo_clock_db
    repo = AmbientRepository(db)
    await repo.ensure_indexes()
    wake = AmbientWake(
        owner_id=OWNER, reason="opportunity_revisit", source_ref="goal:synthetic",
        scheduled_for="2026-10-19T16:09:00+02:00",
    )
    first = await repo.schedule(wake)
    assert first is not None
    assert first.scheduled_for == "2026-10-19T14:09:00+00:00"
    raw = await db.ambient_wakes.find_one({"id": first.id})
    assert raw["scheduled_for"] == first.scheduled_for
    # One real instant should have one identity even if callers propose
    # it with different clock offsets.
    alt = AmbientWake(
        owner_id=OWNER, reason="opportunity_revisit", source_ref="goal:synthetic",
        scheduled_for="2026-10-19T14:09:00+00:00",
    )
    assert first.identity == alt.identity
    assert await repo.schedule(alt) is None
    assert await db.ambient_wakes.count_documents({}) == 1

    before = await repo.claim_due(
        worker_id="worker:before", now=datetime(2026, 10, 19, 14, 8, tzinfo=timezone.utc),
    )
    assert before is None
    due = await repo.claim_due(
        worker_id="worker:due", now=datetime(2026, 10, 19, 14, 9, tzinfo=timezone.utc),
    )
    assert due is not None and due.id == first.id
    assert due.attempts == 1
    await repo.complete(first.id, worker_id="worker:due", result="in_progress")
    done = await db.ambient_wakes.find_one({"id": first.id})
    assert done["status"] == "completed"
    assert done["last_error"] == "in_progress"
    assert await db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_scheduled_retry_and_reschedule_normalize_utc(mongo_clock_db):
    db = mongo_clock_db
    repo = AmbientRepository(db)
    await repo.ensure_indexes()
    wake = await repo.schedule(AmbientWake(
        owner_id=OWNER, reason="opportunity_revisit", source_ref="goal:test-reschedule",
        scheduled_for="2026-10-19T15:00:00+02:00",
    ))
    assert wake
    after = await repo.reschedule(wake.id, when="2026-10-19T16:15:00+02:00")
    assert after.scheduled_for == "2026-10-19T14:15:00+00:00"
    assert await repo.reschedule(wake.id, when="2026-10-19T16:15:00") is None
    assert (await db.ambient_wakes.find_one({"id": wake.id}))["scheduled_for"] == after.scheduled_for

    due = await repo.claim_due(
        worker_id="worker:retry", now=datetime(2026, 10, 19, 14, 15, tzinfo=timezone.utc),
    )
    assert due
    await repo.release(
        wake.id, when="2026-10-19T16:21:00+02:00",
        worker_id="worker:retry", error="TimeoutError",
    )
    raw = await db.ambient_wakes.find_one({"id": wake.id})
    assert raw["status"] == "pending"
    assert raw["scheduled_for"] == "2026-10-19T14:21:00+00:00"
    assert await repo.claim_due(
        worker_id="worker:too-soon", now=datetime(2026, 10, 19, 14, 20, tzinfo=timezone.utc),
    ) is None
    assert await db.push_endpoints.count_documents({}) == 0


@pytest.mark.asyncio
async def test_legacy_open_offset_wakes_migrate_without_recreating_or_claiming():
    db = AsyncMongoMockClient().legacy_offset
    old = AmbientWake(
        owner_id=OWNER, reason="opportunity_revisit",
        source_ref="goal:legacy", scheduled_for="2026-10-19T16:09:00+02:00",
        status="pending",
    )
    row = {**old.model_dump(), "identity": old.identity}
    await db.ambient_wakes.insert_one(row)
    before = await db.ambient_wakes.find_one({"id": old.id}, {"_id": 0})
    repo = AmbientRepository(db)
    await repo.ensure_indexes()
    after = await db.ambient_wakes.find_one({"id": old.id}, {"_id": 0})
    assert after["scheduled_for"] == "2026-10-19T14:09:00+00:00"
    assert after["id"] == before["id"]
    assert after["owner_id"] == before["owner_id"]
    assert after["source_ref"] == before["source_ref"]
    assert after["attempts"] == before["attempts"] == 0
    assert after["status"] == before["status"] == "pending"
    assert after["identity"] == before["identity"], "never replace historical idempotency key"
    assert await db.ambient_wakes.count_documents({}) == 1
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_legacy_completed_and_live_claim_are_not_migrated():
    db = AsyncMongoMockClient().do_not_mutate_history
    repo = AmbientRepository(db)
    live_lease = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    for status in ("completed", "cancelled", "claimed"):
        old = AmbientWake(
            owner_id=OWNER, reason="opportunity_revisit",
            source_ref=f"goal:{status}", status=status,
            scheduled_for="2026-10-19T16:09:00+02:00",
            lease_until=live_lease if status == "claimed" else None,
        )
        await db.ambient_wakes.insert_one({
            **old.model_dump(), "identity": old.identity,
        })
    await repo.ensure_indexes()
    allrows = await db.ambient_wakes.find({}).to_list(20)
    assert len(allrows) == 3
    assert all(row["scheduled_for"] == "2026-10-19T16:09:00+02:00"
               for row in allrows), "do not rewrite terminal history or active workers"


@pytest.mark.asyncio
async def test_readonly_audit_reports_rome_and_utc_without_mislabelling():
    db = AsyncMongoMockClient().local_utc_labels
    situation = SituationState(
        id=SID, user_id=OWNER, summary="Synthetic check",
        location_label="Tarquinia", status="cancelled",
        created_at="2026-10-19T12:00:00+00:00",
        started_at="2026-10-19T12:00:00+00:00",
    )
    await db.situations.insert_one(situation.model_dump())
    gid = goal_id_for(OWNER, SID)
    for iso, start, finished in (
        ("2026-10-19T16:09:41+02:00", "2026-10-19T14:09:43+00:00",
         "2026-10-19T14:09:58+00:00"),
        ("2026-10-19T14:15:13+00:00", "2026-10-19T14:15:23+00:00",
         "2026-10-19T14:15:24+00:00"),
        ("2026-10-19T16:20:53+02:00", "2026-10-19T14:21:03+00:00",
         "2026-10-19T14:21:04+00:00"),
    ):
        wake = AmbientWake(
            owner_id=OWNER, source_ref=f"goal:{gid}",
            reason="opportunity_revisit", scheduled_for=iso,
            claimed_at=start, completed_at=finished,
            status="completed", attempts=1, last_error="in_progress",
        )
        await db.ambient_wakes.insert_one(wake.model_dump())
    before = await db.ambient_wakes.count_documents({})
    data = await read_situation_wake_audit(
        db, OWNER, situation, timezone_name="Europe/Rome",
    )
    assert data["wake_audit_status"] == "records_found"
    assert data["wake_attempt_count"] == 3, data
    allwakes = data["wake_attempts"]
    assert all(x["timezone"] == "Europe/Rome" for x in allwakes)
    first = allwakes[-1]
    assert first["scheduled_for_utc"] == "2026-10-19T14:09:41+00:00"
    assert first["scheduled_for_local"] == "2026-10-19T16:09:41+02:00"
    assert first["worker_started_at_local"] == "2026-10-19T16:09:43+02:00"
    assert first["time_consistency"] == "normal"
    assert all(x["time_consistency"] == "normal" for x in allwakes)
    assert "16:09:41 (Europe/Rome)" in data["wake_audit_note"]
    assert "14:09:41+00:00 UTC" in data["wake_audit_note"]
    assert all(not x["proves_weather_or_physical_outcome"] for x in allwakes)
    assert await db.ambient_wakes.count_documents({}) == before


@pytest.mark.asyncio
async def test_real_worker_early_wake_is_explicitly_marked_not_physical_success():
    db = AsyncMongoMockClient().inconsistent_wake
    situation = SituationState(id=SID, user_id=OWNER, summary="Synthetic audit",
                               created_at="2026-10-19T12:00:00+00:00")
    wake = AmbientWake(
        owner_id=OWNER, source_ref=f"goal:{goal_id_for(OWNER, SID)}",
        reason="opportunity_revisit", scheduled_for="2026-10-19T16:09:00+00:00",
        claimed_at="2026-10-19T14:09:00+00:00",
        completed_at="2026-10-19T14:09:40+00:00",
        status="completed", attempts=1, last_error="in_progress",
    )
    await db.ambient_wakes.insert_one(wake.model_dump())
    report = await read_situation_wake_audit(
        db, OWNER, situation, timezone_name="Europe/Rome",
    )
    assert report["wake_attempt_count"] == 1
    row = report["wake_attempts"][0]
    assert row["time_consistency"] == "worker_started_before_due"
    assert row["scheduled_for_local"] == "2026-10-19T18:09:00+02:00"
    assert row["worker_started_at_local"] == "2026-10-19T16:09:00+02:00"
    assert row["proves_weather_or_physical_outcome"] is False


@pytest.mark.asyncio
async def test_two_ambiguous_dst_local_times_are_distinct_utc_instants():
    db = AsyncMongoMockClient().dst_clock
    repo = AmbientRepository(db)
    await repo.ensure_indexes()
    moments = [
        "2026-10-25T02:30:00+02:00",
        "2026-10-25T02:30:00+01:00",
    ]
    result = []
    for moment in moments:
        saved = await repo.schedule(AmbientWake(
            owner_id=OWNER, reason="opportunity_revisit",
            source_ref="goal:dst", scheduled_for=moment,
        ))
        assert saved
        result.append(saved.scheduled_for)
    assert result == [
        "2026-10-25T00:30:00+00:00",
        "2026-10-25T01:30:00+00:00",
    ]
    assert await db.ambient_wakes.count_documents({}) == 2
    assert _utc_schedule("2026-10-20T16:09:00") is None


@pytest.mark.asyncio
async def test_service_rejects_naive_datetime_and_keeps_real_instant():
    db = AsyncMongoMockClient().service_aware
    service = AmbientService(db)
    naive = datetime.now().replace(tzinfo=None) + timedelta(minutes=20)
    assert await service.schedule(
        OWNER, reason="opportunity_revisit", when=naive,
        source_ref="goal:no-naive-time",
    ) is None
    due = datetime.now(ROME) + timedelta(minutes=12)
    wake = await service.schedule(
        OWNER, reason="opportunity_revisit", when=due,
        source_ref="goal:valid-rome-time",
    )
    assert wake
    assert datetime.fromisoformat(wake.scheduled_for) == due.astimezone(timezone.utc)
    assert wake.scheduled_for.endswith("+00:00")
    assert await db.ambient_wakes.count_documents({}) == 1
