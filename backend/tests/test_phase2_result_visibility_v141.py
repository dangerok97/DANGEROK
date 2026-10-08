"""v141: autonomous completion must reach Home once, without a fake push."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning
from agent.models import AutonomousGoal
from agent.service import AgentService
from agent.visibility import VisibilityService
from scripts.phase2_goal_outcome_eval_v140 import (
    OWNER, seed, admission, first_read, isolated_engine,
)


def useful_visibility(*args, **kwargs):
    return {
        "outcome": "inform_user",
        "headline": "Ho preparato il confronto dei costi annuali: puoi consultarlo in ORA.",
        "reasoning": "Il lavoro informativo è concluso, la persona può leggerlo senza essere interrotta.",
        "about": "confronto costi archivio dodici mesi",
    }


async def in_app_only(*args, **kwargs):
    return {
        "mode": "in_app", "timing": "now",
        "what_decided_the_mode": "Il risultato non è urgente e resta disponibile nell'app",
        "reason_to_open": "C'è un confronto informativo da leggere",
        "requires_recheck": False,
    }


@pytest.mark.asyncio
async def test_completed_goal_surfaces_one_in_app_result_and_never_sends_push():
    from delivery import reasoning as delivery_reasoning

    db = AsyncMongoMockClient().phase2_visible_result_v141
    actual_visibility = AgentService._consider_visibility
    with isolated_engine("scripted"):
        await seed(db)
        goal_id = await admission(db)
        await first_read(db, goal_id)
        with (
            patch.object(AgentService, "_consider_visibility", actual_visibility),
            patch.object(reasoning, "decide_visibility", side_effect=useful_visibility),
            patch.object(delivery_reasoning, "decide_delivery", side_effect=in_app_only),
        ):
            result = await AgentService(db).advance(
                OWNER, goal_id, worker_id="ambient:v141-resumed"
            )
            assert result["state"] == "completed"

    goal = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal_id})
    assert goal and goal["status"] == "completed" and goal["prepared_text"]
    activities = await db.ambient_activity.find({
        "owner_id": OWNER, "visibility": "ambient", "kind": "review_completed"
    }).to_list(8)
    assert len(activities) == 1
    assert "confronto" in activities[0]["summary"].lower()
    assert goal_id in activities[0]["source_refs"]
    assert activities[0]["cognitive_provenance"]["goal"] == goal_id
    # This read-only Delivery bridge is exactly what HomeService calls:
    # the result must be retrievable without opening an ORA chat.
    from delivery.service import DeliveryService
    home_line = await DeliveryService(db).ambient_line(OWNER)
    assert home_line and "confronto" in str(home_line).lower()

    updates = await db.agent_updates.find({"owner_id": OWNER}).to_list(8)
    assert len(updates) == 1 and updates[0]["outcome"] == "inform_user"
    needs = await db.agent_needs.find({
        "owner_id": OWNER, "goal_id": goal_id, "kind": "useful_result"
    }).to_list(8)
    assert len(needs) == 1 and needs[0]["status"] == "open"
    assert await db.delivery_plans.count_documents({"owner_id": OWNER}) == 0
    assert await db.agent_action_attempts.count_documents({"owner_id": OWNER}) == 0

    # A settled goal must not create another update or request.
    with isolated_engine("scripted"):
        again = await AgentService(db).advance(OWNER, goal_id)
    assert again["state"] == "completed"
    assert await db.ambient_activity.count_documents({
        "owner_id": OWNER, "kind": "review_completed"
    }) == 1
    assert await db.agent_needs.count_documents({
        "owner_id": OWNER, "goal_id": goal_id
    }) == 1


@pytest.mark.asyncio
async def test_atomic_insert_allows_only_one_concurrent_worker_to_surface_the_same_news():
    db = AsyncMongoMockClient().visibility_race_v141
    visibility = VisibilityService(db)
    await visibility.ensure_indexes()
    goal = AutonomousGoal(
        owner_id="synthetic-race-owner", status="completed",
        objective="Risultato informativo sintetico", desired_outcome="Fornire un confronto scritto",
    )
    facts = {
        "refs": ["evidence:synthetic"],
        "what_ora_did_this_time": [{"what": "Confronto pronto", "really_happened": True}],
    }
    with (
        patch.object(reasoning, "decide_visibility", side_effect=useful_visibility),
        # Guarantee that both workers pass the optimistic read before
        # competing at Mongo's actual unique owner/fingerprint index.
        patch.object(VisibilityService, "_already_said", AsyncMock(return_value=False)),
    ):
        two = await asyncio.gather(
            visibility.consider("synthetic-race-owner", goal, what_happened=facts),
            visibility.consider("synthetic-race-owner", goal, what_happened=facts),
        )
    assert sum(x.is_visible for x in two) == 1
    assert sum(x.outcome == "silent" for x in two) == 1
    for decision in two:
        if decision.is_visible:
            assert await visibility.show("synthetic-race-owner", goal, decision)
    assert await db.agent_updates.count_documents({"owner_id": "synthetic-race-owner"}) == 1
    assert await db.ambient_activity.count_documents({"owner_id": "synthetic-race-owner"}) == 1


@pytest.mark.asyncio
async def test_without_evidence_ai_headline_cannot_become_an_activity():
    db = AsyncMongoMockClient().visibility_without_proof_v141
    visibility = VisibilityService(db)
    await visibility.ensure_indexes()
    goal = AutonomousGoal(
        owner_id="synthetic-proof-owner", status="active",
        objective="Capire se esiste un dato", desired_outcome="Informazione controllata",
    )
    with patch.object(reasoning, "decide_visibility", side_effect=useful_visibility):
        result = await visibility.consider(
            "synthetic-proof-owner", goal,
            what_happened={"refs": [], "what_ora_did_this_time": []}
        )
    assert result.outcome == "silent"
    assert result.quietened_by_code
    assert await db.agent_updates.count_documents({"owner_id": "synthetic-proof-owner"}) == 0
    assert await db.ambient_activity.count_documents({"owner_id": "synthetic-proof-owner"}) == 0
