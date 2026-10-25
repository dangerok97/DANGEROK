"""ORA checks its own watches and notifications, and repairs what it safely can."""
from datetime import datetime, timedelta, timezone

import pytest

from ops import selfcheck
from situations.followup import read_followup
from test_situation_useful_outcome_v160 import OWNER, setup


@pytest.mark.asyncio
async def test_a_watch_without_alarm_is_rearmed_and_reported(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    goal.next_run_at = None
    await service.repo.save_goal(goal)
    await db.ambient_wakes.delete_many({})
    assert (await read_followup(db, OWNER, state.id))["status"] in ("not_scheduled", "recovery_pending")

    report = await selfcheck.check_owner(db, OWNER)
    codes = {f["code"]: f for f in report["findings"]}
    assert codes["watch_without_alarm"]["repaired"] is True
    after = await read_followup(db, OWNER, state.id)
    assert after["status"] in ("scheduled", "due", "review_pending")
    journal = await db.agent_journal.find({"goal_id": goal.id, "kind": "situation_checkpoint_repaired"}).to_list(5)
    assert journal and journal[-1]["detail"]["by"] == "self_check"
    # A second pass finds nothing left to repair.
    again = await selfcheck.check_owner(db, OWNER)
    assert not [f for f in again["findings"] if f["code"] == "watch_without_alarm"]


@pytest.mark.asyncio
async def test_late_or_missed_notifications_and_missing_device_are_reported(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    now = datetime.now(timezone.utc)
    await db.delivery_plans.insert_many([
        {"id": "dlv_late", "owner_id": OWNER, "status": "pending", "mode": "push",
         "not_before": (now - timedelta(hours=1)).isoformat(), "created_at": (now - timedelta(hours=1)).isoformat()},
        {"id": "dlv_missed", "owner_id": OWNER, "status": "expired", "mode": "push",
         "rationale": "il momento utile è passato mentre ORA era ferma", "created_at": now.isoformat()},
    ])
    report = await selfcheck.check_owner(db, OWNER)
    codes = {f["code"] for f in report["findings"]}
    assert {"delivery_late", "delivery_missed_while_stopped", "no_device_for_notifications"} <= codes
    assert report["healthy"] is False
    latest = await selfcheck.latest(db, OWNER)
    assert latest["at"] == report["at"] and "owner_id" not in latest


@pytest.mark.asyncio
async def test_reports_are_bounded(monkeypatch):
    db, *_ = await setup(monkeypatch)
    for _ in range(selfcheck.KEEP_REPORTS + 5):
        await selfcheck.check_owner(db, OWNER)
    assert await db.ops_self_checks.count_documents({"owner_id": OWNER}) == selfcheck.KEEP_REPORTS


def test_runtime_runs_it_in_the_maintenance_lane():
    import inspect
    from ambient import runtime
    src = inspect.getsource(runtime._cycle)
    assert "ops.selfcheck" in src and '_launch("recovery", lambda: self_check(db)' in src


@pytest.mark.asyncio
async def test_stale_requests_leave_home_but_current_ones_stay(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=20)).isoformat()
    await db.agent_goals.insert_one({"id": "gol_done", "owner_id": OWNER, "status": "completed"})
    await db.agent_needs.insert_many([
        {"id": "ned_done", "owner_id": OWNER, "goal_id": "gol_done", "kind": "needs_information",
         "status": "open", "created_at": now.isoformat()},
        {"id": "ned_old_result", "owner_id": OWNER, "goal_id": goal.id, "kind": "important_outcome",
         "status": "open", "created_at": (now - timedelta(days=3)).isoformat()},
        {"id": "ned_old_question", "owner_id": OWNER, "goal_id": goal.id, "kind": "needs_information",
         "status": "open", "created_at": old},
        {"id": "ned_current", "owner_id": OWNER, "goal_id": goal.id, "kind": "needs_information",
         "status": "open", "created_at": now.isoformat()},
    ])

    async def get(owner, need_id):
        from agent.models import CommunicationNeed
        row = await db.agent_needs.find_one({"id": need_id}, {"_id": 0})
        return row and CommunicationNeed.model_construct(**row)

    cancelled = []

    async def cancel(self, owner, need_id, *, how="", by="code"):
        cancelled.append((need_id, how))
        await db.agent_needs.update_one({"id": need_id}, {"$set": {"status": "cancelled", "resolution": how}})

    monkeypatch.setattr("agent.needs.NeedService.cancel", cancel)
    report = await selfcheck.check_owner(db, OWNER)
    retired = {ref.split(":", 1)[1] for ref in (f["ref"] for f in report["findings"] if f["code"] == "need_retired")}
    assert retired == {"ned_done", "ned_old_result", "ned_old_question"}
    assert (await db.agent_needs.find_one({"id": "ned_current"}))["status"] == "open"
