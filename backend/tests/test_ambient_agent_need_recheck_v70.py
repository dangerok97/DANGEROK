from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AutonomousGoal, CommunicationNeed
from agent.needs import NeedService
from agent.repository import AgentRepository
from ambient.models import AmbientWake
from ambient.service import AmbientService
from delivery.models import DeliveryPlan
from delivery.service import DeliveryService


OWNER = "alice"


@pytest.mark.asyncio
async def test_ambient_recheck_keeps_agent_need_as_agent_need(monkeypatch):
    db = AsyncMongoMockClient().test

    goal = AutonomousGoal(
        owner_id=OWNER,
        status="waiting",
        objective="Concludere un lavoro quando serve il via libera",
        desired_outcome="Riprendere appena il momento è utile",
        requires_user_authority=True,
    )
    await AgentRepository(db).create_goal(goal)

    need = await NeedService(db).raise_need(
        CommunicationNeed(
            owner_id=OWNER,
            goal_id=goal.id,
            kind="needs_authority",
            summary="Serve il tuo via libera.",
            reason="Il prossimo passo ha un effetto esterno.",
            source_refs=["journal:test"],
            what_is_missing="Conferma.",
            requires_response=True,
        )
    )

    plan = await DeliveryService(db).repo.save_plan(
        DeliveryPlan(
            owner_id=OWNER,
            source_type="agent_need",
            source_id=need.id,
            mode="push",
            status="pending",
            not_before=datetime.now(timezone.utc).isoformat(),
        )
    )

    seen = {}

    async def evaluate_subject(self, user_id, subject, *, app_state="unknown", language="it"):
        seen["source_type"] = getattr(subject, "source_type", "")
        seen["id"] = getattr(subject, "id", "")
        seen["goal_id"] = getattr(subject, "goal_id", "")
        return SimpleNamespace(
            unavailable=False,
            mode="in_app",
            blocked_by="",
        )

    monkeypatch.setattr(DeliveryService, "evaluate_subject", evaluate_subject)
    monkeypatch.setattr(AmbientService, "app_state", AsyncMock(return_value="background"))

    wake = AmbientWake(
        owner_id=OWNER,
        reason="delivery_recheck",
        delivery_plan_id=plan.id,
        source_ref=f"agent_need:{need.id}",
        scheduled_for=datetime.now(timezone.utc).isoformat(),
    )

    out = await AmbientService(db).recheck_delivery(wake)

    assert out.handled is True
    assert out.result == "in_app"
    assert seen == {
        "source_type": "agent_need",
        "id": need.id,
        "goal_id": goal.id,
    }


@pytest.mark.asyncio
async def test_closed_goal_cancels_agent_need_wake_without_new_judgement(monkeypatch):
    db = AsyncMongoMockClient().test

    goal = AutonomousGoal(
        owner_id=OWNER,
        status="waiting",
        objective="Seguire un esito",
        desired_outcome="Concludere senza notifiche stale",
        requires_user_authority=True,
    )
    await AgentRepository(db).create_goal(goal)
    need = await NeedService(db).raise_need(
        CommunicationNeed(
            owner_id=OWNER,
            goal_id=goal.id,
            kind="needs_authority",
            summary="Serve il tuo via libera.",
            reason="Il prossimo passo ha un effetto esterno.",
            source_refs=["journal:test"],
            what_is_missing="Conferma.",
            requires_response=True,
        )
    )
    plan = await DeliveryService(db).repo.save_plan(
        DeliveryPlan(
            owner_id=OWNER,
            source_type="agent_need",
            source_id=need.id,
            mode="push",
            status="pending",
        )
    )

    goal.status = "completed"
    goal.requires_user_authority = False
    await AgentRepository(db).save_goal(goal)

    decide = AsyncMock()
    monkeypatch.setattr(DeliveryService, "evaluate_subject", decide)

    wake = AmbientWake(
        owner_id=OWNER,
        reason="delivery_recheck",
        delivery_plan_id=plan.id,
        source_ref=f"agent_need:{need.id}",
    )
    out = await AmbientService(db).recheck_delivery(wake)

    assert out.handled is True
    assert out.result == "cancelled_resolved"
    decide.assert_not_awaited()
    saved = await DeliveryService(db).repo.get_plan(OWNER, plan.id)
    assert saved.status == "cancelled"
