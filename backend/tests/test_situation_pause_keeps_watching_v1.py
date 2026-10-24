"""A paused Situation watch always leaves the next look scheduled.

Production 24/10/2026 18:22, laundry: the planner meant "re-read, then wait for
the window", wrote no usable step, and the run paused with no next check —
the goal stayed open, nothing was scheduled, Home said "not scheduled".
"""
from datetime import datetime, timezone

import pytest

from agent.models import ActionPlan, AgentRun
from test_situation_useful_outcome_v160 import OWNER, setup


@pytest.mark.asyncio
async def test_pause_on_a_situation_watch_schedules_the_next_check(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    goal.next_run_at = None
    await service.repo.save_goal(goal)
    plan = ActionPlan(goal_id=goal.id, owner_id=OWNER)
    await service._pause(OWNER, goal, plan, run, "senza altra strada")
    saved = await service.repo.get_goal(OWNER, goal.id)
    assert saved.next_run_at and datetime.fromisoformat(saved.next_run_at) > datetime.now(timezone.utc)
    wakes = await db.ambient_wakes.find({"source_ref": f"goal:{goal.id}", "status": "pending"}).to_list(5)
    assert wakes


@pytest.mark.asyncio
async def test_a_future_check_already_planned_is_left_alone(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    goal.next_run_at = "2999-01-01T00:00:00+00:00"
    await service.repo.save_goal(goal)
    before = await db.ambient_wakes.count_documents({"source_ref": f"goal:{goal.id}"})
    await service._pause(OWNER, goal, ActionPlan(goal_id=goal.id, owner_id=OWNER), run, "x")
    assert await db.ambient_wakes.count_documents({"source_ref": f"goal:{goal.id}"}) == before
