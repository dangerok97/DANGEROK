from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning
from agent.service import AgentService
from agent.models import AutonomousGoal


def test_plan_receives_the_actual_persisted_source_references():
    goal = AutonomousGoal(owner_id="alice", objective="Confronta i costi", desired_outcome="Conoscere condizioni",
        source_kind="document", source_refs=["document:d1"])
    assert goal.for_ai()["source_refs"] == ["document:d1"]
    assert goal.for_ai()["source_kind"] == "document"


@pytest.mark.asyncio
async def test_goal_decision_receives_only_cited_owned_sources(monkeypatch):
    db = AsyncMongoMockClient().test
    for doc in [
        {"id": "cited", "user_id": "alice", "extracted_text": "Condizioni incomplete " + "a"*1500},
        {"id": "uncited", "user_id": "alice", "extracted_text": "UNRELATED"},
        {"id": "foreign", "user_id": "bob", "extracted_text": "FOREIGN"},
    ]:
        await db.documents.insert_one(doc)
    decide = AsyncMock(return_value={"outcome": "no_goal"})
    monkeypatch.setattr(reasoning, "decide_goal", decide)
    await AgentService(db).consider("alice", situation={"what": "Prezzo cambiato"},
        source_refs=["document:cited", "document:foreign"])
    payload = decide.call_args.args[0]
    assert [row["ref"] for row in payload["source_context"]] == ["document:cited"]
    assert payload["source_context"][0]["excerpt_truncated"]
    assert payload["source_context_unavailable"] is True
    assert "FOREIGN" not in str(payload) and "UNRELATED" not in str(payload)
