"""Outcome context never promotes registration, scope or a check into a forecast."""
import pytest
from mongomock_motor import AsyncMongoMockClient

from life_profile.knowledge_map import knowledge_map


@pytest.mark.asyncio
async def test_time_scope_is_not_an_outcome_estimate_and_physical_start_is_preserved():
    db = AsyncMongoMockClient().test
    state = {
        "id": "sit_v160_projection", "user_id": "owner", "status": "active",
        "summary": "Attività in corso.", "temporal_scope": "oggi",
        "desired_outcome": "Sapere quando è utile intervenire.",
        "started_at": "2026-10-24T23:30:00+02:00",
        "created_at": "2026-10-25T00:10:00+02:00",
        "updated_at": "2026-10-25T02:10:00+01:00", "revision": 3,
        "attention_intent": "Rivalutare gli elementi che cambiano.",
    }
    await db.situations.insert_one(dict(state))
    await db.situations.insert_one({**state, "id": "sit_foreign", "user_id": "other",
                                    "desired_outcome": "PRIVATE FOREIGN OUTCOME"})
    result = await knowledge_map(db, "owner")
    temporary = [star for star in result["stars"] if star.get("temporary")]
    assert len(temporary) == 1
    star = temporary[0]
    assert star["expected_outcome_summary"] is None
    assert star["started_at"] == state["started_at"]
    assert star["started_at"] != star["created_at"]
    assert star["desired_outcome"] == state["desired_outcome"]
    assert "PRIVATE FOREIGN OUTCOME" not in str(result)
    assert await db.situations.find_one({"id": state["id"]}, {"_id": 0}) == state
