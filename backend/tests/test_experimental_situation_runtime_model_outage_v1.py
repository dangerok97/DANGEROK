"""Actual Ambient → Agent → model-outage → durable recovery acceptance.

Uses an isolated MongoDB database *only* on the GitHub Actions localhost
service, not a user's ORA data and not an external LLM/provider. The model
unavailability is fault-injected at the ordinary planning adapter. This joins
the persistent wake claim, AgentService.advance and recover_due protocols.
The UI may never equate this technical retry with a physical outcome.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from ambient import runtime
from agent import reasoning
from agent.background import recover_due
from opportunities.discovery import OpportunityDiscovery
from situations.followup import INITIAL_KIND, read_followup, goal_id_for
from situations.models import SituationUpdate
from situations.service import SituationService

OWNER = "exp-outage-owned-synthetic"


@pytest.mark.asyncio
async def test_real_mongo_background_planning_outage_remains_recoverable(monkeypatch):
    url = (os.environ.get("MONGO_URL") or "").strip()
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or not url.startswith(("mongodb://127.0.0.1:27017",
                               "mongodb://localhost:27017"))
    ):
        pytest.skip("Isolated real Mongo acceptance only runs in GitHub CI")

    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setattr(
        OpportunityDiscovery, "note",
        AsyncMock(return_value={"outcome": "accepted"}),
    )
    # Inject the LLM outage in the REAL AgentService planning protocol:
    # no guessed steps, no external model call or fallback text pretending
    # an evidence-backed weather observation exists.
    fake_model = AsyncMock(return_value=None)
    monkeypatch.setattr(reasoning, "make_plan", fake_model)

    name = "ora_exp_model_outage_" + uuid.uuid4().hex[:12]
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=3500)
    try:
        db = client[name]
        await db.command("ping")
        await db.agent_goals.create_index("id", unique=True)
        await db.agent_runs.create_index("goal_id", unique=True)
        await db.ambient_wakes.create_index(
            "identity", unique=True,
            partialFilterExpression={
                "status": {"$in": ["pending", "claimed"]}
            },
        )
        created = await SituationService(db).apply(
            user_id=OWNER,
            session_id="synthetic-conversation",
            reasoning_epoch="explicit-user-synthetic",
            update=SituationUpdate(
                operation="create", source="user_conversation",
                summary="TEST: processo fisico dichiarato, non osservato",
                attention_intent="Indagare il momento utile e continuare",
                desired_outcome="Una conclusione utile basata su evidenze",
                location_label="Città dichiarata nel test",
            ),
        )
        assert created["status"] == "success"
        sid = created["situation"]["id"]
        gid = goal_id_for(OWNER, sid)
        initial = await read_followup(db, OWNER, sid)
        assert initial["status"] == "review_pending", initial
        assert initial["next_check_at"] is None

        # A genuine Ambient worker claims the initial user-owned wake and
        # invokes the real AgentService.advance. No mocked worker dispatcher.
        first = await runtime.tick(db, limit=1)
        assert first["claimed"] == 1, first
        assert fake_model.await_count == 1, "real Agent planning was invoked"
        stored = await db.agent_goals.find_one(
            {"owner_id": OWNER, "id": gid}, {"_id": 0}
        )
        assert stored and stored["source_kind"] == INITIAL_KIND
        assert stored["status"] in ("active", "waiting")
        assert stored["planning_attempts"] >= 1
        assert stored["planning_unavailable"] is True
        retry_at = stored.get("next_run_at")
        assert retry_at and datetime.fromisoformat(retry_at) > datetime.now(timezone.utc)
        check = await read_followup(db, OWNER, sid)
        assert check["next_check_at"] is None
        assert check["status"] not in ("scheduled", "due", "running")
        assert await db.life_nodes.count_documents({"user_id": OWNER, "type": "event"}) == 0
        assert await db.delivery_plans.count_documents({"owner_id": OWNER}) == 0

        # A later scanner must reconstruct EXACTLY ONE runnable wake from
        # the persisted retry-at, without treating elapsed time as evidence.
        due = datetime.fromisoformat(retry_at) + timedelta(seconds=4)
        recovered = await recover_due(db, now=due, limit=2, admit=False)
        open_wakes = await db.ambient_wakes.find(
            {"owner_id": OWNER, "source_ref": f"goal:{gid}",
             "status": {"$in": ["pending", "claimed"]}},
        ).to_list(5)
        assert len(open_wakes) == 1, (recovered, open_wakes)
        assert await recover_due(db, now=due, limit=2, admit=False) == 0
        assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
        assert await db.situations.count_documents({"user_id": OWNER}) == 1
        assert await db.agent_needs.count_documents({"owner_id": OWNER}) == 0
        assert await db.delivery_plans.count_documents({"owner_id": OWNER}) == 0
        assert await db.life_nodes.count_documents({"user_id": OWNER, "type": "event"}) == 0
    finally:
        await client.drop_database(name)
        client.close()
