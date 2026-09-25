"""Deterministic full agent loop; controlled judgements, real reads and persistence.

This is NOT a live-model quality gate. No Home route or user command is used.
"""
from unittest.mock import AsyncMock
from datetime import datetime, timedelta, timezone
import pytest
from mongomock_motor import AsyncMongoMockClient
from agent import reasoning
from agent.service import AgentService
from agent.background import recover_due
from ambient.runtime import tick
from opportunities.discovery import OpportunityDiscovery


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["Condizioni di prova: costo annuo 120 euro.", "A" * 4000 + "Costo annuo: 120 euro."], ids=["short", "paginated"])
async def test_background_document_goal_reads_and_verifies_without_home(monkeypatch, text):
    import mongomock.collection
    original = mongomock.collection.Collection.find_one_and_update
    def update(self, *args, **kwargs):
        kwargs.pop("projection", None)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(mongomock.collection.Collection,"find_one_and_update",update)
    db = AsyncMongoMockClient().test
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.documents.insert_one({"id":"d1", "user_id":"alice", "filename":"PROVA.txt", "extracted_text":text})
    from opportunities import reasoning as opportunity_reasoning, snapshot
    for name in ("_open_questions", "_recently_settled", "_places", "_presence", "_routines", "_comparisons", "_calendar", "_situations", "_disagreements", "_money", "_existing_work"):
        monkeypatch.setattr(snapshot, name, AsyncMock(return_value=[]))
    async def scan(state, **kwargs):
        assert state["documents"][0]["ref"] == "document:d1"
        assert state["documents"][0]["text_available"]
        return {"opportunities": [{"identity_key": "fixture:document",
            "what": "Condizioni nuove da verificare", "why_it_matters": "Conoscere il costo dichiarato",
            "initiative": "prepare", "evidence_refs": ["document:d1"]}]}
    monkeypatch.setattr(opportunity_reasoning, "scan", AsyncMock(side_effect=scan))
    discovery = OpportunityDiscovery(db)
    await discovery.note("alice", source="documents", kind="document.added", entity_ref="d1", wake=False)
    review = await discovery.review("alice")
    assert review.ran and len(review.scan.created) == 1
    monkeypatch.setattr(AgentService,"_note_ambient",AsyncMock())
    monkeypatch.setattr(AgentService,"_consider_visibility",AsyncMock())
    monkeypatch.setattr(AgentService,"_observe_life_change",AsyncMock())
    monkeypatch.setattr(reasoning,"decide_goal",AsyncMock(return_value={"outcome":"create_goal", "objective":"Verificare il costo dichiarato", "desired_outcome":"Conoscere il costo nel documento"}))
    monkeypatch.setattr(reasoning,"make_plan",AsyncMock(return_value={"steps":[{"intent":"Leggi documento", "step_type":"inspect", "capability_needed":"document.read", "input_refs":["document:d1"]}]}))

    async def reconsider(goal, *, what_happened, **kwargs):
        # Continuation must be communicated by the real executor, not invented by the test.
        observation = what_happened["result"]["what_happened"]
        import re
        match = re.search(r"document_offset=(\d+), document_version=([0-9a-f]+)", observation)
        if not match:
            return {"decision":"continue"}
        return {"decision":"modify", "revised_steps":[{"intent":"Continua lettura", "step_type":"inspect", "capability_needed":"document.read", "input_refs":["document:d1"], "parameters":{"document_offset":int(match[1]),"document_version":match[2]}}]}
    replanner = AsyncMock(side_effect=reconsider)
    monkeypatch.setattr(reasoning,"reconsider",replanner)
    monkeypatch.setattr(reasoning,"choose_next_action",AsyncMock(side_effect=lambda *a, candidates, **kw: {"decision":"execute","step_id":candidates[0]["id"]}))
    async def verify(goal, *, evidence, **kwargs):
        found = str(evidence["what_was_found"])
        assert "120 euro" in found, "Goal reached verification before the relevant text was read"
        assert "document:d1" in found
        return {"outcome":"achieved", "reasoning":"Il documento dichiara 120 euro annui; non è un confronto di mercato."}
    monkeypatch.setattr(reasoning,"verify_goal",AsyncMock(side_effect=verify))
    async def draft(system, payload):
        import json
        rows = json.loads(payload)["evidence"]
        assert "120 euro" in str(rows)
        return {"verified": True, "content": "Il documento dichiara un costo annuo di 120 euro, non verificato sul mercato.",
                "evidence_ids": [row["id"] for row in rows]}
    monkeypatch.setattr(reasoning, "_ask_model", draft)
    await recover_due(db)
    await recover_due(db)
    result = await tick(db, now=datetime.now(timezone.utc)+timedelta(minutes=1))
    goal = await db.agent_goals.find_one({"owner_id":"alice"})
    assert goal["status"] == "completed", (result, await db.ambient_wakes.find({}, {"last_error":1}).to_list(10))
    assert goal["origin"] == "agent_initiated"
    assert "120 euro" in goal["prepared_text"] and goal["prepared_sources"]
    assert await db.agent_receipts.count_documents({}) == 0
    if len(text)>4000:
        assert replanner.await_count >= 1
