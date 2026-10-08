"""v133: notification taps never forge delivery, another owner, or navigation.

The only accepted action is opening a previously accepted Delivery plan,
without authorizing a goal or changing any external system.
"""
from __future__ import annotations

from mongomock_motor import AsyncMongoMockClient
import pytest

from delivery.models import DeliveryPlan
from delivery.service import DeliveryService


async def build(
    db, *, owner="alice", source="opp_synthetic",
    source_type="opportunity", route=None, status="delivered",
    outcome="delivered",
):
    service = DeliveryService(db)
    if route is None:
        route = f"/aggiornamento/{source}"
    plan = DeliveryPlan(
        owner_id=owner,
        source_type=source_type,
        source_id=source,
        mode="push", status=status,
        outcome=outcome,
        deep_link=route,
    )
    await service.repo.save_plan(plan)
    return service, plan


@pytest.mark.asyncio
async def test_accepted_opportunity_tap_returns_only_backend_owned_route():
    db = AsyncMongoMockClient().notification_handoff_v133
    svc, plan = await build(db)
    first = await svc.record_outcome("alice", plan.id, "opened")
    assert first == {
        "ok": True, "outcome": "opened",
        "opportunity_id": "opp_synthetic",
        "route": "/aggiornamento/opp_synthetic",
    }
    saved = await svc.repo.get_plan("alice", plan.id)
    assert saved.outcome == "opened" and saved.opened_at
    second = await svc.record_outcome("alice", plan.id, "opened")
    assert second == first
    again = await svc.repo.get_plan("alice", plan.id)
    assert again.opened_at == saved.opened_at
    assert (await svc.record_outcome("alice", plan.id, "dismissed"))["outcome"] == "opened"


@pytest.mark.asyncio
async def test_foreign_owner_and_unsent_intention_cannot_report_open():
    db = AsyncMongoMockClient().notification_handoff_owner_v133
    svc, plan = await build(db, status="pending", outcome=None)
    assert await svc.record_outcome("alice", plan.id, "opened") == {
        "ok": False, "reason": "not_delivered"
    }
    assert await svc.record_outcome("bob", plan.id, "opened") == {
        "ok": False, "reason": "unknown_plan"
    }
    stored = await svc.repo.get_plan("alice", plan.id)
    assert stored.opened_at is None and stored.outcome is None


@pytest.mark.asyncio
@pytest.mark.parametrize("tampered", [
    "https://evil.example/authorize",
    "/agent/goals/fake/approve",
    "//evil.example",
    "/aggiornamento/foreign_id",
    "/ora?needId=other&goalId=test&entry=agent_need",
    "/",
])
async def test_edited_deep_link_cannot_escape_backend_allowlist(tampered):
    db = AsyncMongoMockClient().notification_handoff_route_v133
    svc, plan = await build(db, route=tampered)
    assert await svc.record_outcome("alice", plan.id, "opened") == {
        "ok": False, "reason": "invalid_notification_target"
    }
    assert (await svc.repo.get_plan("alice", plan.id)).opened_at is None


@pytest.mark.asyncio
async def test_agent_need_cannot_substitute_another_need_or_goal():
    db = AsyncMongoMockClient().notification_handoff_agent_v133
    svc, plan = await build(
        db, source="need_synthetic", source_type="agent_need",
        route="/ora?needId=need_synthetic&goalId=goal_synthetic&entry=agent_need",
    )
    result = await svc.record_outcome("alice", plan.id, "opened")
    assert result["ok"] is True and result["route"] == plan.deep_link
    assert result["opportunity_id"] == ""

    svc2, forged = await build(
        db, source="need_synthetic_2", source_type="agent_need",
        route="/ora?needId=need_other&goalId=goal_synthetic&entry=agent_need",
    )
    assert await svc2.record_outcome("alice", forged.id, "opened") == {
        "ok": False, "reason": "invalid_notification_target",
    }


@pytest.mark.asyncio
async def test_outcome_route_must_be_code_generated_and_not_user_supplied():
    db = AsyncMongoMockClient().notification_handoff_validation_v133
    svc, plan = await build(db)
    assert await svc.record_outcome("alice", plan.id, "authorise") == {
        "ok": False, "reason": "unknown_outcome",
    }
    assert (await svc.repo.get_plan("alice", plan.id)).outcome == "delivered"
