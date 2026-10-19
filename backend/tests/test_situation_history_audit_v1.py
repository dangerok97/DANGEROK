"""A missing card or stale Situation id must not erase a persisted audit.

Everything is owner-scoped and synthetic. No user account, weather provider,
push delivery, running background process or production database is touched.
"""
import pytest
from mongomock_motor import AsyncMongoMockClient

from situations.models import SituationState
from situations.followup import (
    get_situation_followup, list_situation_followups, read_followup, goal_id_for,
)

OWNER = "synthetic-history-owner"
OTHER = "synthetic-other-account"


@pytest.mark.asyncio
async def test_completed_and_closed_situation_still_reports_only_verified_history(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().history_test
    closed = SituationState(
        id="sit_our_closed", user_id=OWNER, summary="Synthetic panni a Tarquinia",
        location_label="Tarquinia", status="cancelled",
        resolved_at="2026-10-19T20:23:34+00:00",
        created_at="2026-10-19T12:00:00+00:00",
        started_at="2026-10-19T12:00:00+00:00",
    )
    active = SituationState(
        id="sit_other_active", user_id=OWNER,
        summary="Synthetic unrelated pending task", status="active",
    )
    secret = SituationState(
        id="sit_foreign", user_id=OTHER, summary="Private foreign situation",
        status="active",
    )
    for state in (closed, active, secret):
        await db.situations.insert_one(state.model_dump())

    # A model statement or the existence of a terminated Situation alone
    # cannot establish that a physical check ran. Only this exact journal
    # event with its succeeded+really_happened flags can prove the timestamp.
    at = "2026-10-19T14:09:58+00:00"
    await db.agent_journal.insert_one({
        "owner_id": OWNER, "goal_id": goal_id_for(OWNER, closed.id),
        "kind": "step_done", "detail": {
            "really_happened": True, "status": "succeeded",
        },
        "at": at, "note": "Synthetic weather-source check was performed",
    })
    await db.agent_journal.insert_one({
        "owner_id": OTHER, "goal_id": goal_id_for(OTHER, secret.id),
        "kind": "step_done", "detail": {
            "really_happened": True, "status": "succeeded",
        },
        "at": "2026-10-19T15:00:00+00:00",
        "note": "Other owner's private observation",
    })
    before = {
        col: await db[col].count_documents({})
        for col in ("situations", "agent_goals", "ambient_wakes",
                    "agent_journal", "delivery_plans")
    }

    stopped = await read_followup(db, OWNER, closed.id)
    assert stopped["status"] == "stopped", stopped
    assert stopped["situation_lifecycle"] == "cancelled"
    assert stopped["last_checked_at"] is None
    assert stopped["last_step_at"] == at
    assert stopped["last_result"] is None
    assert stopped["last_result_verification"] == "location_not_proven"
    assert stopped["next_check_at"] is None
    assert "NON ci sono prove sufficienti" in stopped["diagnosis"]
    assert "programmato" not in stopped["diagnosis"]
    last = await get_situation_followup(
        {"situation_id": closed.id}, {"db": db, "user_id": OWNER}
    )
    assert last.status == "ok" and last.payload["last_step_at"] == at

    listing = await list_situation_followups({}, {"db": db, "user_id": OWNER})
    assert listing.status == "ok"
    assert listing.payload["count"] == 2
    summaries = {entry["situation_id"]: entry for entry in listing.payload["items"]}
    assert set(summaries) == {closed.id, active.id}
    assert summaries[closed.id]["monitoring_status"] == "stopped"
    assert summaries[closed.id]["last_step_at"] == at
    assert summaries[closed.id]["last_checked_at"] is None
    assert summaries[active.id]["next_check_at"] is None
    assert "Private foreign situation" not in str(listing.model_dump())
    assert "synthetic-other-account" not in str(listing.model_dump())

    for col, n in before.items():
        assert await db[col].count_documents({}) == n, col


@pytest.mark.asyncio
async def test_no_fake_execution_or_disclosure_for_closed_unchecked_or_wrong_id(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().history_not_done
    await db.situations.insert_one(SituationState(
        id="sit_cancelled_unchecked", user_id=OWNER, status="cancelled",
        summary="Synthetic no observation",
    ).model_dump())
    await db.situations.insert_one(SituationState(
        id="sit_foreign", user_id=OTHER, status="cancelled",
        summary="Other person's hidden history",
    ).model_dump())

    closed = await read_followup(db, OWNER, "sit_cancelled_unchecked")
    assert closed["status"] == "stopped"
    assert closed["last_checked_at"] is None
    assert closed["next_check_at"] is None
    assert "Non risulta un controllo eseguito" in closed["diagnosis"]

    for bad_id in ("sit_not_real", "sit_foreign"):
        invalid = await read_followup(db, OWNER, bad_id)
        assert invalid["status"] == "unavailable"
        assert invalid["read_failure_code"] == "situation_not_found_or_not_owned"
        assert "list_situation_followups" in invalid["diagnosis"]
        response = await get_situation_followup(
            {"situation_id": bad_id}, {"db": db, "user_id": OWNER}
        )
        assert response.status == "error"
        assert "Other person's hidden history" not in str(response.payload)
    assert await db.ambient_wakes.count_documents({}) == 0
    assert await db.agent_goals.count_documents({}) == 0


@pytest.mark.asyncio
async def test_storage_error_is_different_from_missing_record():
    class BadSituations:
        async def find_one(self, *_args, **_kw):
            raise OSError("simulated transient database failure")

    class BadDb:
        situations = BadSituations()

    result = await read_followup(BadDb(), OWNER, "sit_arbitrary")
    assert result["status"] == "unavailable"
    assert result["read_failure_code"] == "storage_read_failed"
    assert "lettura del database" in result["diagnosis"]
    assert result["last_checked_at"] is None
