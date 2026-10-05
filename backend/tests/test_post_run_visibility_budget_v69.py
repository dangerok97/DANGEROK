from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import (
    AgentBudget,
    AgentEvidence,
    AgentRun,
    AutonomousGoal,
    ResultProvenance,
    VisibilityDecision,
)
from agent.service import AgentService


OWNER = "alice"


async def _worked_goal(db):
    service = AgentService(db)
    goal = AutonomousGoal(
        owner_id=OWNER,
        status="active",
        objective="Seguire una situazione utile senza essere guidata passo passo",
        desired_outcome="Avere un risultato verificato e comunicarlo solo se serve",
        success_criteria=["Il risultato utile è verificato."],
    )
    await service.repo.create_goal(goal)
    await service.evidence.record(
        AgentEvidence(
            owner_id=OWNER,
            goal_id=goal.id,
            claim="È emerso un risultato reale e verificabile.",
            provenance=ResultProvenance(
                source_class="external_research",
                capability="web.research",
                freshness="fresh",
            ),
        )
    )
    await service.repo.journal(
        OWNER,
        goal.id,
        kind="step_done",
        note="Ho verificato il fatto utile.",
        detail={"really_happened": True, "came_from": "external_research"},
    )
    return service, goal


@pytest.mark.asyncio
async def test_exhausted_work_budget_still_gets_one_visibility_judgement(monkeypatch):
    from delivery.service import DeliveryService

    db = AsyncMongoMockClient().test
    service, goal = await _worked_goal(db)
    run = AgentRun(owner_id=OWNER, goal_id=goal.id, background=True)
    budget = AgentBudget(
        cognitive_calls=8,
        max_cognitive_calls=8,
        visibility_calls=0,
        max_visibility_calls=1,
    )

    decision = VisibilityDecision(
        goal_id=goal.id,
        outcome="inform_user",
        headline="Ho trovato un risultato utile da mostrarti.",
        reasoning="Il lavoro ha prodotto qualcosa che cambia ciò che sai.",
        refs=["journal:worked"],
        fingerprint="v69-useful-result",
    )
    consider = AsyncMock(return_value=decision)
    monkeypatch.setattr(service.visibility, "consider", consider)
    monkeypatch.setattr(service.visibility, "show", AsyncMock(return_value=True))

    delivered = AsyncMock(return_value=SimpleNamespace(mode="in_app"))
    monkeypatch.setattr(DeliveryService, "evaluate_subject", delivered)

    result = await service._consider_visibility(
        OWNER, goal.id, run, budget, language="it"
    )

    assert result is decision
    assert budget.cognitive_calls == 8, "la comunicazione non deve rubare budget al lavoro"
    assert budget.visibility_calls == 1
    assert run.model_calls == 9
    consider.assert_awaited_once()

    need = await db.agent_needs.find_one({"owner_id": OWNER, "goal_id": goal.id})
    assert need is not None
    assert need["kind"] == "useful_result"
    assert need["summary"] == decision.headline

    delivered.assert_awaited_once()
    subject = delivered.await_args.args[1]
    assert subject.source_type == "agent_need"
    assert subject.goal_id == goal.id
    assert subject.semantic_summary == decision.headline


@pytest.mark.asyncio
async def test_visibility_budget_is_still_hard_bounded(monkeypatch):
    db = AsyncMongoMockClient().test
    service, goal = await _worked_goal(db)
    run = AgentRun(owner_id=OWNER, goal_id=goal.id, background=True)
    budget = AgentBudget(
        cognitive_calls=8,
        max_cognitive_calls=8,
        visibility_calls=1,
        max_visibility_calls=1,
    )

    consider = AsyncMock()
    monkeypatch.setattr(service.visibility, "consider", consider)

    result = await service._consider_visibility(
        OWNER, goal.id, run, budget, language="it"
    )

    assert result is None
    consider.assert_not_awaited()
    assert budget.visibility_calls == 1


@pytest.mark.asyncio
async def test_silent_visibility_still_creates_no_need(monkeypatch):
    db = AsyncMongoMockClient().test
    service, goal = await _worked_goal(db)
    run = AgentRun(owner_id=OWNER, goal_id=goal.id, background=True)
    budget = AgentBudget(cognitive_calls=8, max_cognitive_calls=8)

    monkeypatch.setattr(
        service.visibility,
        "consider",
        AsyncMock(return_value=VisibilityDecision(
            goal_id=goal.id,
            outcome="silent",
            reasoning="Non cambia nulla per la persona adesso.",
        )),
    )

    result = await service._consider_visibility(
        OWNER, goal.id, run, budget, language="it"
    )

    assert result is not None and result.outcome == "silent"
    assert budget.visibility_calls == 1
    assert await db.agent_needs.count_documents({"owner_id": OWNER}) == 0
