import json
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning
from agent.models import AutonomousGoal, ActionStep, AgentEvidence, ResultProvenance
from agent.providers import prepare_locally


async def fixture(with_evidence=True):
    db = AsyncMongoMockClient().test
    goal = AutonomousGoal(owner_id="alice", objective="Riassumi condizioni", desired_outcome="Bozza con costi e limiti", status="active")
    await db.agent_goals.insert_one(goal.model_dump())
    evidence = AgentEvidence(owner_id="alice", goal_id=goal.id, claim="Il documento indica 120 euro annui senza rimborso.",
        provenance=ResultProvenance(source_class="internal_observation", provider="documents", source_refs=["document:d1"]))
    if with_evidence:
        await db.agent_evidence.insert_one(evidence.model_dump())
    return db, goal, evidence, ActionStep(intent="Prepara riepilogo", step_type="prepare")


@pytest.mark.asyncio
async def test_preparation_saves_actual_content_and_sources_before_success(monkeypatch):
    db, goal, evidence, step = await fixture()
    content = "Costo dichiarato: 120 euro annui. I mesi inutilizzati non sono rimborsati."
    async def model(system, payload):
        assert json.loads(payload)["evidence"][0]["id"] == evidence.id
        return {"verified": True, "content": content, "evidence_ids": [evidence.id]}
    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await prepare_locally(db, "alice", goal, step)
    saved = await db.agent_goals.find_one({"id": goal.id})
    assert result.status == "succeeded"
    assert saved["prepared_text"] == goal.for_human()["prepared_text"] == content
    assert saved["prepared_sources"] == [evidence.id]
    assert content in result.claims[0].text
    assert result.provenance.provider == "generated_draft"


@pytest.mark.asyncio
async def test_no_evidence_cannot_become_ready(monkeypatch):
    db, goal, evidence, step = await fixture(False)
    model = AsyncMock()
    monkeypatch.setattr(reasoning, "_ask_model", model)
    assert (await prepare_locally(db, "alice", goal, step)).error_type == "preparation_sources_required"
    model.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [None, {"content": "Pronto", "evidence_ids": ["invented"]}, {"content": "", "evidence_ids": []}])
async def test_failed_or_ungrounded_draft_never_reports_success(monkeypatch, answer):
    db, goal, evidence, step = await fixture()
    monkeypatch.setattr(reasoning, "_ask_model", AsyncMock(return_value=answer))
    result = await prepare_locally(db, "alice", goal, step)
    assert result.status == "unavailable" and not result.claims and not goal.prepared_text


@pytest.mark.asyncio
async def test_owner_and_closed_goal_are_protected(monkeypatch):
    db, goal, evidence, step = await fixture()
    monkeypatch.setattr(reasoning, "_ask_model", AsyncMock(return_value={"verified": True, "content": "Bozza", "evidence_ids": [evidence.id]}))
    assert (await prepare_locally(db, "bob", goal, step)).error_type == "preparation_owner_mismatch"
    await db.agent_goals.update_one({"id": goal.id}, {"$set": {"status": "cancelled"}})
    assert (await prepare_locally(db, "alice", goal, step)).error_type == "preparation_goal_unavailable"


@pytest.mark.asyncio
async def test_generated_draft_cannot_cite_itself_as_independent_source(monkeypatch):
    db, goal, evidence, step = await fixture()
    await db.agent_evidence.update_one({"id": evidence.id}, {"$set": {"provenance.provider": "generated_draft"}})
    result = await prepare_locally(db, "alice", goal, step)
    assert result.error_type == "preparation_sources_required"


@pytest.mark.asyncio
@pytest.mark.parametrize("review", [None, {"verified": False}, {"verified": True, "content": "Unsupported", "evidence_ids": ["invented"]}])
async def test_failed_review_never_persists_draft(monkeypatch, review):
    db, goal, evidence, step = await fixture()
    model = AsyncMock(side_effect=[{"content": "Prima bozza", "evidence_ids": [evidence.id]}, review])
    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await prepare_locally(db, "alice", goal, step)
    saved = await db.agent_goals.find_one({"id": goal.id})
    assert result.status == "unavailable"
    assert not saved.get("prepared_text") and not goal.prepared_text
    assert model.await_count == 2


@pytest.mark.asyncio
async def test_only_source_reviewed_content_is_persisted(monkeypatch):
    db, goal, evidence, step = await fixture()
    corrected = "Costo annuo 120 euro; nessun rimborso."
    model = AsyncMock(side_effect=[
        {"content": "Sei obbligato a restare dodici mesi.", "evidence_ids": [evidence.id]},
        {"verified": True, "content": corrected, "evidence_ids": [evidence.id]},
    ])
    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await prepare_locally(db, "alice", goal, step)
    saved = await db.agent_goals.find_one({"id": goal.id})
    assert result.status == "succeeded"
    assert saved["prepared_text"] == goal.prepared_text == corrected
    assert "obbligato" not in result.claims[0].text


@pytest.mark.asyncio
async def test_calendar_conflict_prepares_exact_safe_request_without_model(monkeypatch):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from home.manual_event import create_manual_event, archive_manual_event, home_event_times
    db = AsyncMongoMockClient().test
    # Far enough in the future for a stable test independent of the clock.
    day = (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=2)).date().isoformat()
    first_start, first_end = home_event_times(day, "10:00", "Europe/Rome")
    second_start, second_end = home_event_times(day, "10:15", "Europe/Rome")
    first = await create_manual_event(db, "alice", title="Ritiro modulo", start=first_start,
        end=first_end, tz_name="Europe/Rome", description="Portare il modulo originale")
    second = await create_manual_event(db, "alice", title="Consegna al tecnico", start=second_start,
        end=second_end, tz_name="Europe/Rome")
    refs = ["calendar:" + first["id"], "calendar:" + second["id"]]
    goal = AutonomousGoal(owner_id="alice", objective="Risolvere il conflitto", desired_outcome="Un piano",
        status="active", source_kind="opportunity", opportunity_id="opp_1", source_refs=refs)
    await db.agent_goals.insert_one(goal.model_dump())
    for ref in refs:
        await db.agent_evidence.insert_one(AgentEvidence(owner_id="alice", goal_id=goal.id,
            claim="Impegno letto dal calendario", supports=ref,
            provenance=ResultProvenance(source_class="internal_observation", provider="ora_local_calendar")).model_dump())
    model = AsyncMock()
    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await prepare_locally(db, "alice", goal, ActionStep(intent="Prepara la richiesta", step_type="prepare"))
    assert result.status == "succeeded" and "45 minuti" in goal.prepared_text
    assert "nessun messaggio è stato inviato" in goal.prepared_text.lower()
    assert "corriere" not in goal.prepared_text.lower()
    assert "disponibilità alternativa" in goal.prepared_text
    assert len(goal.prepared_sources) == 2
    model.assert_not_awaited()
    await archive_manual_event(db, "alice", second["id"])
    another = await prepare_locally(db, "alice", goal, ActionStep(intent="Rivedi", step_type="prepare"))
    assert another.error_type == "preparation_calendar_changed"


@pytest.mark.asyncio
async def test_active_home_overlap_admits_preparation_without_unnecessary_address_question(monkeypatch):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from home.manual_event import create_manual_event, archive_manual_event, home_event_times
    from agent.calendar_conflict import active_home_pair
    from agent.needs import NeedService
    from agent.service import AgentService
    db = AsyncMongoMockClient().test
    day = (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=2)).date().isoformat()
    a, a_end = home_event_times(day, "10:00", "Europe/Rome")
    b, b_end = home_event_times(day, "10:15", "Europe/Rome")
    first = await create_manual_event(db, "alice", title="Ritiro documento", start=a, end=a_end, tz_name="Europe/Rome")
    second = await create_manual_event(db, "alice", title="Consegna", start=b, end=b_end, tz_name="Europe/Rome")
    await db.opportunities.insert_one({"id": "opp_pair", "owner_id": "alice", "agent_review_revision": "rev"})
    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())
    delivery = AsyncMock()
    monkeypatch.setattr(NeedService, "offer_to_delivery", delivery)
    decision = AsyncMock(side_effect=AssertionError("no model decision for an established overlap"))
    monkeypatch.setattr(reasoning, "decide_goal", decision)
    refs = ["calendar:" + first["id"], "calendar:" + second["id"]]
    result = await AgentService(db).consider("alice", situation={"waiting_on_an_answer": True},
        opportunity_id="opp_pair", source_kind="opportunity", source_refs=refs)
    assert result["outcome"] == "create_goal"
    goal = await db.agent_goals.find_one({"id": result["goal_id"]})
    assert goal["decision_provenance"] == "code" and goal["source_refs"] == refs
    assert goal["status"] == "waiting" and goal["next_run_at"] is None
    assert "45 minuti" in goal["prepared_text"]
    assert "nessun messaggio è stato inviato" in goal["prepared_text"].lower()
    assert len(goal["prepared_sources"]) == 2
    assert goal["requires_user_input"] is True
    plan = await db.agent_plans.find_one({"goal_id": goal["id"]})
    assert plan["status"] == "waiting" and len(plan["steps"]) == 1
    assert plan["steps"][0]["step_type"] == "ask_user"
    assert plan["steps"][0]["status"] == "blocked"
    assert plan["steps"][0]["ask_kind"] == "knowledge"
    need = await db.agent_needs.find_one({"goal_id": goal["id"], "status": "open"})
    assert need["requires_response"] is True and need["response_kind"] == "information"
    assert "quale dei due impegni" in need["summary"].lower()
    delivery.assert_awaited_once()
    decision.assert_not_awaited()
    from agent.clarifications import work_view
    await db.opportunities.update_one({"id": "opp_pair"}, {"$set": {
        "status": "active", "agent_review_state": "settled",
        "agent_review_outcome": "create_goal", "agent_review_goal_id": goal["id"]}})
    ready = await work_view(db, "alice", "opp_pair")
    assert ready["status"] == "needs_user"
    assert "45 minuti" in ready["result"]["ora_text"]
    assert ready["result"]["route"] == f"/ora?needId={need['id']}&goalId={goal['id']}"
    await archive_manual_event(db, "alice", second["id"])
    assert await active_home_pair(db, "alice", refs) is None
    stale = await work_view(db, "alice", "opp_pair")
    assert stale["result"]["ora_text"] is None
