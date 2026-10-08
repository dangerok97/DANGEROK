"""v140: end-to-end life-to-outcome path on synthetic Mongo, no real effects."""
from unittest.mock import patch

import pytest
from agent import reasoning
from agent.service import AgentService
from scripts.phase2_goal_outcome_eval_v140 import run, seed, OWNER, isolated_engine, admission, first_read


@pytest.mark.asyncio
async def test_source_creates_and_completes_one_grounded_result_across_fresh_services():
    report = await run("scripted")
    assert report["passed"] is True
    assert report["first"]["first_state"] == "in_progress"
    assert report["resumed"]["result"] == "completed"
    assert report["resumed"]["real_read_reused"] is True
    assert report["resumed"]["effects"] == 0
    assert report["replay"] == "completed"
    assert report["owner_isolation"] is True


@pytest.mark.asyncio
async def test_missing_source_does_not_finish_as_if_draft_is_proven():
    from mongomock_motor import AsyncMongoMockClient
    from agent.models import AgentBudget
    db = AsyncMongoMockClient().phase2_v140_missing_facts
    with isolated_engine("scripted"):
        await seed(db)
        goal_id = await admission(db)
        first = await first_read(db, goal_id)
        assert first["read_evidence"] == 1
        # New evidence is not silently invented after memory disappears.
        # The stored read remains a historical observation, not a false
        # independently-verified claim about the present provider.
        await db.memories.delete_many({"user_id": OWNER})
        current = await AgentService(db).repo.get_goal(OWNER, goal_id)
        assert current.status == "active"
        assert not current.prepared_text
        # Never claim a new provider read just because the first one exists.
        old = await db.agent_evidence.count_documents({
            "owner_id": OWNER, "goal_id": goal_id,
            "provenance.capability": "information.read",
        })
        assert old == 1


@pytest.mark.asyncio
async def test_other_owner_cannot_resume_the_pending_goal():
    from mongomock_motor import AsyncMongoMockClient
    db = AsyncMongoMockClient().phase2_v140_owner_isolation
    with isolated_engine("scripted"):
        await seed(db)
        goal_id = await admission(db)
        await first_read(db, goal_id)
        result = await AgentService(db).advance("unrelated-synthetic-owner", goal_id)
        assert result == {"ok": False, "reason": "unknown_goal"}
        assert await db.agent_goals.count_documents({"owner_id": OWNER, "status": "active"}) == 1
