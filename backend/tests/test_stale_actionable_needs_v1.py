"""Active question projection must not preserve expired physical situations.

Only synthetic data; do not mutate user goals, notifications or life state.
"""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import CommunicationNeed
from agent.needs import NeedService


@pytest.mark.asyncio
async def test_open_needs_never_show_stale_goal_or_expired_question():
    db = AsyncMongoMockClient().stale_needs
    service = NeedService(db)
    now = datetime.now(timezone.utc)
    before = (now - timedelta(days=2)).isoformat()
    after = (now + timedelta(days=2)).isoformat()
    owner = "synthetic-user"

    goals = [
        {"id": "finished", "owner_id": owner, "status": "completed", "valid_until": after},
        {"id": "old", "owner_id": owner, "status": "waiting", "valid_until": before},
        {"id": "good", "owner_id": owner, "status": "waiting", "valid_until": after},
        {"id": "other", "owner_id": "different-user", "status": "waiting", "valid_until": after},
    ]
    await db.agent_goals.insert_many(goals)
    needs = [
        ("finished", after),
        ("old", after),
        ("good", before),
        ("other", after),
        ("good", after),
    ]
    for i, (goal_id, expiry) in enumerate(needs):
        need = CommunicationNeed(
            owner_id=owner, goal_id=goal_id, kind="needs_information",
            summary=f"synthetic question {i}", valid_until=expiry,
            created_at=(now - timedelta(minutes=10 - i)).isoformat(),
        )
        await db.agent_needs.insert_one(need.model_dump())

    visible = await service.open_needs(owner, limit=1)
    assert len(visible) == 1
    assert visible[0].summary == "synthetic question 4"
    # History remains intact: no implicit cancellation of physical work.
    assert await db.agent_needs.count_documents({"owner_id": owner}) == 5


@pytest.mark.asyncio
async def test_open_needs_preserves_legacy_missing_goal_and_owner_isolation():
    db = AsyncMongoMockClient().legacy_needs
    service = NeedService(db)
    await db.agent_needs.insert_one(CommunicationNeed(
        owner_id="owner-a", goal_id="legacy-unknown",
        kind="needs_information", summary="Legacy question",
    ).model_dump())
    await db.agent_needs.insert_one(CommunicationNeed(
        owner_id="owner-b", goal_id="legacy-other",
        kind="needs_information", summary="Different owner's question",
    ).model_dump())
    result = await service.open_needs("owner-a")
    assert [x.summary for x in result] == ["Legacy question"]
