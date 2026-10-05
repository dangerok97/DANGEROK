import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AutonomousGoal
from agent.owner_budget import OwnerBackgroundBudget
from agent.service import AgentService


OWNER = "alice"
FIXED = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_owner_budget_is_atomic_shared_and_isolated_between_people():
    db = AsyncMongoMockClient().test
    budget = OwnerBackgroundBudget(db, daily_limit=2)
    await budget.ensure_indexes()

    claims = await asyncio.gather(
        budget.claim(OWNER, now=FIXED),
        budget.claim(OWNER, now=FIXED),
        budget.claim(OWNER, now=FIXED),
    )

    assert sum(1 for claim in claims if claim.allowed) == 2
    assert sum(1 for claim in claims if not claim.allowed) == 1
    assert max(claim.used for claim in claims) == 2

    # A different person has a different budget row, even at the same instant.
    bob = await budget.claim("bob", now=FIXED)
    assert bob.allowed is True
    assert bob.used == 1

    row = await db.agent_owner_background_budgets.find_one(
        {"owner_id": OWNER, "day": "2026-10-05"}, {"_id": 0}
    )
    assert row is not None
    assert row["used"] == 2
    assert row["limit"] == 2


@pytest.mark.asyncio
async def test_owner_budget_persists_across_service_instances_and_resets_next_day():
    db = AsyncMongoMockClient().test
    first = OwnerBackgroundBudget(db, daily_limit=1)
    await first.ensure_indexes()

    allowed = await first.claim(OWNER, now=FIXED)
    assert allowed.allowed is True

    # A fresh process/service sees the same persistent owner budget.
    second = OwnerBackgroundBudget(db, daily_limit=1)
    denied = await second.claim(OWNER, now=FIXED + timedelta(hours=1))
    assert denied.allowed is False
    assert denied.used == 1

    tomorrow = await second.claim(OWNER, now=FIXED + timedelta(days=1))
    assert tomorrow.allowed is True
    assert tomorrow.used == 1
    assert tomorrow.reset_at > allowed.reset_at


@pytest.mark.asyncio
async def test_background_goal_pauses_at_owner_budget_and_user_run_bypasses(monkeypatch):
    from ambient.service import AmbientService

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = AutonomousGoal(
        id="goal_owner_budget_v79",
        owner_id=OWNER,
        status="active",
        objective="Seguire una situazione utile",
        desired_outcome="Portarla avanti senza consumare lavoro autonomo senza limite",
        source_kind="opportunity",
        source_refs=["situation:sit_budget"],
    )
    await service.repo.save_goal(goal)

    reset_at = (FIXED + timedelta(hours=12)).isoformat()
    denied = SimpleNamespace(
        allowed=False,
        used=12,
        limit=12,
        reset_at=reset_at,
    )
    claim = AsyncMock(return_value=denied)
    monkeypatch.setattr(service.owner_budget, "claim", claim)

    schedule = AsyncMock(return_value=True)
    monkeypatch.setattr(AmbientService, "schedule", schedule)

    work = AsyncMock(return_value={"ok": True, "state": "in_progress"})
    monkeypatch.setattr(service, "_work", work)
    monkeypatch.setattr(service, "_consider_visibility", AsyncMock())

    background = await service.advance(
        OWNER,
        goal.id,
        worker_id="ambient:v79",
    )

    assert background["state"] == "owner_budget_paused"
    assert background["until"] == reset_at
    claim.assert_awaited_once_with(OWNER)
    work.assert_not_awaited()

    saved = await service.repo.get_goal(OWNER, goal.id)
    assert saved is not None
    assert saved.status == "waiting"
    assert saved.next_run_at == reset_at
    assert saved.background_runs == 0

    schedule.assert_awaited_once()
    assert schedule.await_args.kwargs["reason"] == "owner_budget_reset"
    assert schedule.await_args.kwargs["source_ref"] == f"goal:{goal.id}"
    assert schedule.await_args.kwargs["when"] == datetime.fromisoformat(reset_at)

    journal = await db.agent_journal.find_one(
        {
            "owner_id": OWNER,
            "goal_id": goal.id,
            "kind": "owner_budget_wait",
        },
        {"_id": 0},
    )
    assert journal is not None
    assert journal["detail"]["used"] == 12
    assert journal["detail"]["limit"] == 12

    # A direct user-driven continuation is not unsolicited autonomy and must
    # not be blocked by the owner's background allowance.
    user_run = await service.advance(
        OWNER,
        goal.id,
        worker_id="user:v79",
    )

    assert user_run["state"] == "in_progress"
    assert claim.await_count == 1
    work.assert_awaited_once()


@pytest.mark.asyncio
async def test_owner_budget_claim_failure_fails_closed(monkeypatch):
    db = AsyncMongoMockClient().test
    budget = OwnerBackgroundBudget(db, daily_limit=4)

    async def broken(*args, **kwargs):
        raise RuntimeError("mongo unavailable")

    monkeypatch.setattr(
        db.agent_owner_background_budgets,
        "find_one_and_update",
        broken,
    )

    claim = await budget.claim(OWNER, now=FIXED)

    assert claim.allowed is False
    assert claim.used == 4
    assert claim.limit == 4


@pytest.mark.asyncio
async def test_goal_burst_ceiling_does_not_spend_shared_owner_budget(monkeypatch):
    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = AutonomousGoal(
        id="goal_local_budget_exhausted_v79",
        owner_id=OWNER,
        status="active",
        objective="Goal già arrivato al proprio tetto tecnico",
        desired_outcome="Non consumare budget condiviso senza lavoro",
        background_runs=3,
        source_kind="opportunity",
        source_refs=["situation:sit_local_limit"],
    )
    await service.repo.save_goal(goal)

    claim = AsyncMock()
    monkeypatch.setattr(service.owner_budget, "claim", claim)
    monkeypatch.setattr(service, "_work", AsyncMock())
    monkeypatch.setattr(service, "_consider_visibility", AsyncMock())

    result = await service.advance(
        OWNER,
        goal.id,
        worker_id="ambient:v79-local-limit",
    )

    assert result["state"] == "background_paused"
    claim.assert_not_awaited()
