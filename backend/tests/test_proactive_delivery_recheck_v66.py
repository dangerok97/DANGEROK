from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AutonomousGoal, CommunicationNeed
from agent.needs import NeedService
from agent.repository import AgentRepository
from delivery.service import DeliveryService
from opportunities.models import Opportunity
from opportunities.repository import OpportunityRepository


OWNER = "alice"


class Provider:
    name = "test"

    def __init__(self):
        self.sent = []
        self.cancelled = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return {"ok": True, "provider": self.name, "external_id": "test"}

    async def cancel(self, *, owner_id, plan_id):
        self.cancelled.append(plan_id)
        return {"ok": True}


def push_at(when=None):
    return {
        "mode": "push",
        "timing": "at" if when else "now",
        "not_before": when,
        "not_after": None,
        "reason_to_interrupt": "Serve saperlo nel momento utile.",
        "reason_to_open": "ORA ha rivalutato la situazione.",
        "what_decided_the_mode": "Il momento attuale rende utile intervenire.",
        "copy_intent": "Dire cosa è cambiato.",
        "confidence": "strong",
        "sensitivity": "ordinary",
        "requires_recheck": True,
        "copy": {
            "title": "Aggiornamento utile",
            "body": "C'è qualcosa da vedere adesso.",
            "public_title": "Aggiornamento utile",
            "public_body": "Apri ORA per vedere.",
        },
    }


def in_app():
    return {
        "mode": "in_app",
        "timing": "now",
        "reason_to_interrupt": "Non serve interrompere adesso.",
        "reason_to_open": "L'aggiornamento resta disponibile nell'app.",
        "what_decided_the_mode": "Il momento non giustifica una push.",
        "copy_intent": "",
        "confidence": "strong",
        "sensitivity": "ordinary",
        "requires_recheck": True,
        "copy": {},
    }


async def setup_delivery(monkeypatch, db, answers):
    from delivery import context as delivery_context
    from delivery import provider as provider_module
    from delivery import reasoning as delivery_reasoning

    channel = Provider()
    monkeypatch.setattr(provider_module, "get_provider", lambda: channel)
    monkeypatch.setattr(
        delivery_context, "build", AsyncMock(return_value={"app_state": "background"})
    )
    monkeypatch.setattr(
        DeliveryService, "_may_push", AsyncMock(return_value=(True, ""))
    )
    monkeypatch.setattr(DeliveryService, "_arrange_wake", AsyncMock())
    decide = AsyncMock(side_effect=list(answers))
    monkeypatch.setattr(delivery_reasoning, "decide_delivery", decide)
    return channel, decide


async def goal_and_need(db):
    goal = AutonomousGoal(
        owner_id=OWNER,
        status="waiting",
        objective="Seguire un esito esterno",
        desired_outcome="Sapere cosa fare quando cambia qualcosa",
        requires_user_authority=True,
    )
    await AgentRepository(db).create_goal(goal)
    need = CommunicationNeed(
        owner_id=OWNER,
        goal_id=goal.id,
        kind="needs_authority",
        summary="Ho preparato tutto: serve il tuo via libera.",
        reason="Il prossimo passo cambia qualcosa fuori da ORA.",
        source_refs=["journal:one"],
        work_already_done=["Ho verificato il contesto."],
        what_is_missing="Serve il tuo via libera.",
        requires_response=True,
    )
    need = await NeedService(db).raise_need(need)
    return goal, need


async def make_need_plan(monkeypatch, db, second_answer):
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    channel, decide = await setup_delivery(
        monkeypatch, db, [push_at(future), second_answer]
    )
    goal, need = await goal_and_need(db)
    first = await NeedService(db).offer_to_delivery(OWNER, need)
    assert first.mode == "push"
    assert first.plan is not None and first.plan.source_type == "agent_need"
    assert channel.sent == []
    await db.delivery_plans.update_one(
        {"id": first.plan.id},
        {"$set": {
            "not_before": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        }},
    )
    return channel, decide, goal, need, first.plan.id


@pytest.mark.asyncio
async def test_due_agent_need_is_rejudged_and_can_become_in_app(monkeypatch):
    db = AsyncMongoMockClient().test
    channel, decide, _goal, need, plan_id = await make_need_plan(
        monkeypatch, db, in_app()
    )

    summary = await DeliveryService(db).deliver_due(OWNER)

    assert summary == {"sent": 0, "cancelled": 1, "held": 0}
    assert channel.sent == []
    assert decide.await_count == 2
    plan = await DeliveryService(db).repo.get_plan(OWNER, plan_id)
    assert plan.status == "cancelled"
    assert plan.last_rechecked_at is not None
    assert (await NeedService(db).get(OWNER, need.id)).is_open is True


@pytest.mark.asyncio
async def test_due_agent_need_can_still_push_after_fresh_judgement(monkeypatch):
    db = AsyncMongoMockClient().test
    channel, decide, _goal, need, plan_id = await make_need_plan(
        monkeypatch, db, push_at()
    )

    summary = await DeliveryService(db).deliver_due(OWNER)

    assert summary["sent"] == 1
    assert summary["cancelled"] == 0
    assert len(channel.sent) == 1
    assert decide.await_count == 2
    plan = await DeliveryService(db).repo.get_plan(OWNER, plan_id)
    assert plan.status == "delivered"
    assert f"needId={need.id}" in plan.deep_link
    assert (await NeedService(db).get(OWNER, need.id)).is_open is True


@pytest.mark.asyncio
async def test_closed_goal_kills_scheduled_agent_need_push_before_model_or_provider(monkeypatch):
    db = AsyncMongoMockClient().test
    channel, decide, goal, _need, plan_id = await make_need_plan(
        monkeypatch, db, push_at()
    )
    goal.status = "completed"
    goal.requires_user_authority = False
    await AgentRepository(db).save_goal(goal)

    summary = await DeliveryService(db).deliver_due(OWNER)

    assert summary["sent"] == 0
    assert summary["cancelled"] == 1
    assert channel.sent == []
    assert decide.await_count == 1, "un bisogno morto non deve comprare un altro giudizio"
    plan = await DeliveryService(db).repo.get_plan(OWNER, plan_id)
    assert plan.status == "cancelled"


@pytest.mark.asyncio
async def test_due_opportunity_is_rejudged_not_merely_permission_checked(monkeypatch):
    db = AsyncMongoMockClient().test
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    channel, decide = await setup_delivery(
        monkeypatch, db, [push_at(future), in_app()]
    )
    opportunity = await OpportunityRepository(db).save(
        Opportunity(
            owner_id=OWNER,
            identity_key="v66:changing-moment",
            status="active",
            semantic_summary="Una situazione potrebbe richiedere attenzione più tardi.",
            why_it_matters="Il valore dipende da come cambia prima del momento utile.",
            initiative="prepare",
        )
    )

    first = await DeliveryService(db).evaluate(OWNER, opportunity.id)
    assert first.plan is not None
    await db.delivery_plans.update_one(
        {"id": first.plan.id},
        {"$set": {
            "not_before": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        }},
    )

    summary = await DeliveryService(db).deliver_due(OWNER)

    assert summary["sent"] == 0
    assert summary["cancelled"] == 1
    assert channel.sent == []
    assert decide.await_count == 2, "il momento di invio deve comprare un nuovo giudizio"
