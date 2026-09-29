"""A diagnostic must tell pending from finished without returning user data."""
import pytest
from mongomock_motor import AsyncMongoMockClient

from ambient.audit import pipeline_counts


@pytest.mark.asyncio
async def test_pipeline_counts_are_scoped_and_content_free():
    db = AsyncMongoMockClient().test
    await db.opportunities.insert_many([
        {"owner_id": "alice", "status": "active", "delivery_review_state": "pending",
         "agent_review_state": "settled", "semantic_summary": "Riservato"},
        {"owner_id": "alice", "status": "active", "delivery_review_state": "paused",
         "agent_review_state": "paused", "semantic_summary": "Altro segreto"},
        {"owner_id": "alice", "status": "active", "agent_review_state": "pending"},
        {"owner_id": "bob", "status": "active", "delivery_review_state": "settled"},
    ])
    await db.agent_goals.insert_many([
        {"owner_id": "alice", "status": "active", "objective": "Riservato"},
        {"owner_id": "bob", "status": "completed"},
    ])
    await db.ambient_wakes.insert_one({"owner_id": "alice", "status": "failed"})

    counts = await pipeline_counts(db, owner_id="alice")
    assert counts["opportunities.active"] == 3
    assert counts["opportunities.delivery_pending"] == 1
    assert counts["opportunities.delivery_paused"] == 1
    assert counts["opportunities.delivery_legacy_untracked"] == 1
    assert counts["opportunities.agent_pending"] == 1
    assert counts["goals.active"] == 1
    assert counts["goals.completed"] == 0
    assert counts["wakes.failed"] == 1
    assert "Riservato" not in str(counts) and "alice" not in str(counts)
    assert (await pipeline_counts(db))["opportunities.active"] == 4
