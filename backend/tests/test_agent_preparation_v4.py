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

@pytest.mark.asyncio
async def test_calendar_conflict_choice_becomes_one_authorised_verified_local_move(monkeypatch):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from home import manual_event as manual_calendar
    from home.manual_event import create_manual_event, get_manual_event, home_event_times
    from agent.needs import NeedService
    from agent.service import AgentService

    db = AsyncMongoMockClient().test
    day = (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=3)).date().isoformat()
    a, a_end = home_event_times(day, "10:00", "Europe/Rome")
    b, b_end = home_event_times(day, "10:15", "Europe/Rome")
    first = await create_manual_event(db, "alice", title="Ritiro documento",
        start=a, end=a_end, tz_name="Europe/Rome")
    second = await create_manual_event(db, "alice", title="Consegna al tecnico",
        start=b, end=b_end, tz_name="Europe/Rome")
    refs = ["calendar:" + first["id"], "calendar:" + second["id"]]
    await db.opportunities.insert_one({
        "id": "opp_move", "owner_id": "alice", "status": "active",
        "agent_review_revision": "rev_move",
    })

    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())
    monkeypatch.setattr(AgentService, "_consider_visibility", AsyncMock(return_value=None))
    monkeypatch.setattr(NeedService, "offer_to_delivery", AsyncMock())
    monkeypatch.setattr(reasoning, "decide_goal",
        AsyncMock(side_effect=AssertionError("established overlap is code-grounded")))
    monkeypatch.setattr(reasoning, "interpret_calendar_conflict_choice", AsyncMock(
        return_value={"target_ref": refs[1], "requested_time": "12:00",
                      "requested_date": "", "reasoning": "Ha scelto il secondo."}))
    monkeypatch.setattr(reasoning, "interpret_calendar_coordination", AsyncMock(
        return_value={"mode": "direct", "reasoning": "È un impegno personale."}))
    monkeypatch.setattr(reasoning, "choose_next_action", AsyncMock(
        return_value={"decision": "execute", "step_id": "", "reasoning": "La scelta è completa."}))
    monkeypatch.setattr(reasoning, "assess_authority", AsyncMock(return_value={
        "outcome": "prepare_then_confirm", "reasoning": "È una modifica personale reversibile.",
        "reversibility": "easily", "financial_effect": False,
        "external_communication": False, "third_party_impact": False,
        "privacy_disclosure": False, "legal_effect": False, "security_effect": False,
    }))
    monkeypatch.setattr(reasoning, "verify_goal", AsyncMock(return_value={
        "outcome": "achieved", "reasoning": "Il secondo impegno risulta spostato e riletto.",
        "what_is_missing": "", "revisit_in_hours": None,
    }))
    monkeypatch.setattr(manual_calendar, "_wake", AsyncMock())

    service = AgentService(db)
    created = await service.consider("alice", situation={},
        opportunity_id="opp_move", source_kind="opportunity", source_refs=refs)
    goal_id = created["goal_id"]
    before = await get_manual_event(db, "alice", second["id"])

    coordination = await service.answer(
        "alice", goal_id, reply="Tieni il primo e sposta il secondo alle 12"
    )
    assert coordination["state"] == "waiting_for_person"
    assert "confermato" in coordination["asks"].lower()
    still = await get_manual_event(db, "alice", second["id"])
    assert still["attributes"]["starts_at"] == before["attributes"]["starts_at"]

    prepared = await service.answer(
        "alice", goal_id,
        reply="È solo un impegno mio: puoi spostarlo direttamente."
    )
    assert prepared["state"] == "awaiting_authority"
    plan = await service.repo.plan_for("alice", goal_id)
    move = [s for s in plan.steps if s.step_type == "execute"][-1]
    assert move.status == "blocked"
    assert move.capability_needed == "calendar.local.write"
    assert move.effect_type == "modify"
    assert move.input_refs == [refs[1]]
    assert move.parameters["expected_revision"] == before["updated_at"]

    done = await service.authorise("alice", goal_id)
    assert done["state"] == "completed"
    after = await get_manual_event(db, "alice", second["id"])
    assert datetime.fromisoformat(after["attributes"]["starts_at"]).strftime("%H:%M") == "12:00"
    first_after = await get_manual_event(db, "alice", first["id"])
    assert first_after["attributes"]["starts_at"] == a
    receipts = await db.agent_receipts.find(
        {"owner_id": "alice", "goal_id": goal_id}, {"_id": 0}
    ).to_list(10)
    assert len(receipts) == 1
    assert receipts[0]["provider"] == "ora_calendar"
    assert receipts[0]["provider_status"] == "succeeded"
    attempts = await db.agent_action_attempts.find(
        {"owner_id": "alice", "goal_id": goal_id}, {"_id": 0}
    ).to_list(10)
    assert len(attempts) == 1 and attempts[0]["status"] == "verified"


@pytest.mark.asyncio
async def test_local_calendar_agent_write_refuses_stale_revision(monkeypatch):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from home import manual_event as manual_calendar
    from home.manual_event import create_manual_event, get_manual_event, home_event_times, update_manual_event
    from agent.execution import StepExecutor
    from agent.models import ActionStep, AutonomousGoal

    db = AsyncMongoMockClient().test
    day = (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=4)).date().isoformat()
    start, end = home_event_times(day, "09:00", "Europe/Rome")
    event = await create_manual_event(db, "alice", title="Impegno",
        start=start, end=end, tz_name="Europe/Rome")
    monkeypatch.setattr(manual_calendar, "_wake", AsyncMock())
    original = await get_manual_event(db, "alice", event["id"])
    await update_manual_event(
        db, "alice", event["id"], {"location": "Nuovo luogo"},
        expected_updated_at=original["updated_at"],
    )

    new_start, new_end = home_event_times(day, "12:00", "Europe/Rome")
    step = ActionStep(
        intent="Spostare l'impegno", step_type="execute",
        capability_needed="calendar.local.write",
        input_refs=["calendar:" + event["id"]],
        effect_type="modify", external_effect=True,
        effect_target="il tuo calendario ORA",
        parameters={"start_datetime": new_start, "end_datetime": new_end,
                    "timezone": "Europe/Rome",
                    "expected_revision": original["updated_at"]},
    )
    goal = AutonomousGoal(owner_id="alice", objective="Spostare",
        desired_outcome="Impegno spostato", status="active")
    result = await StepExecutor(db).run(
        "alice", goal, step, may_touch_the_world=True
    )
    assert result.status == "failed"
    assert result.error_type == "event_changed"
    current = await get_manual_event(db, "alice", event["id"])
    assert datetime.fromisoformat(current["attributes"]["starts_at"]).strftime("%H:%M") == "09:00"



@pytest.mark.asyncio
async def test_calendar_conflict_authorisation_survives_service_restart(monkeypatch):
    """A process restart between proposal and approval resumes the same effect once."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from home import manual_event as manual_calendar
    from home.manual_event import create_manual_event, get_manual_event, home_event_times
    from agent.needs import NeedService
    from agent.service import AgentService

    db = AsyncMongoMockClient().test
    day = (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=5)).date().isoformat()
    first_start, first_end = home_event_times(day, "10:00", "Europe/Rome")
    second_start, second_end = home_event_times(day, "10:15", "Europe/Rome")
    first = await create_manual_event(db, "alice", title="Primo impegno",
        start=first_start, end=first_end, tz_name="Europe/Rome")
    second = await create_manual_event(db, "alice", title="Secondo impegno",
        start=second_start, end=second_end, tz_name="Europe/Rome")
    refs = ["calendar:" + first["id"], "calendar:" + second["id"]]
    await db.opportunities.insert_one({
        "id": "opp_restart", "owner_id": "alice", "status": "active",
        "agent_review_revision": "rev_restart",
    })

    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())
    monkeypatch.setattr(AgentService, "_consider_visibility", AsyncMock(return_value=None))
    monkeypatch.setattr(NeedService, "offer_to_delivery", AsyncMock())
    monkeypatch.setattr(reasoning, "decide_goal",
        AsyncMock(side_effect=AssertionError("overlap is code-grounded")))
    monkeypatch.setattr(reasoning, "interpret_calendar_conflict_choice", AsyncMock(
        return_value={"target_ref": refs[1], "requested_time": "12:00",
                      "requested_date": "", "reasoning": "secondo alle dodici"}))
    monkeypatch.setattr(reasoning, "interpret_calendar_coordination", AsyncMock(
        return_value={"mode": "direct", "reasoning": "È un impegno personale."}))
    monkeypatch.setattr(reasoning, "choose_next_action", AsyncMock(
        return_value={"decision": "execute", "step_id": "", "reasoning": "procedi"}))
    monkeypatch.setattr(reasoning, "assess_authority", AsyncMock(return_value={
        "outcome": "prepare_then_confirm", "reasoning": "modifica personale",
        "reversibility": "easily", "financial_effect": False,
        "external_communication": False, "third_party_impact": False,
        "privacy_disclosure": False, "legal_effect": False, "security_effect": False,
    }))
    monkeypatch.setattr(reasoning, "verify_goal", AsyncMock(return_value={
        "outcome": "achieved", "reasoning": "spostamento riletto",
        "what_is_missing": "", "revisit_in_hours": None,
    }))
    monkeypatch.setattr(manual_calendar, "_wake", AsyncMock())

    before_restart = AgentService(db)
    created = await before_restart.consider("alice", situation={},
        opportunity_id="opp_restart", source_kind="opportunity", source_refs=refs)
    goal_id = created["goal_id"]
    coordination = await before_restart.answer(
        "alice", goal_id, reply="Lascia il primo e sposta il secondo alle 12"
    )
    assert coordination["state"] == "waiting_for_person"
    waiting = await before_restart.answer(
        "alice", goal_id, reply="È soltanto mio, spostalo nel calendario."
    )
    assert waiting["state"] == "awaiting_authority"

    # New service instance: nothing useful may live only in process memory.
    after_restart = AgentService(db)
    done = await after_restart.authorise("alice", goal_id)
    assert done["state"] == "completed"
    moved = await get_manual_event(db, "alice", second["id"])
    assert datetime.fromisoformat(moved["attributes"]["starts_at"]).strftime("%H:%M") == "12:00"
    assert await db.agent_receipts.count_documents(
        {"owner_id": "alice", "goal_id": goal_id}) == 1
    assert await db.agent_action_attempts.count_documents(
        {"owner_id": "alice", "goal_id": goal_id}) == 1

    # A repeated approval after completion cannot create a second effect.
    again = await AgentService(db).authorise("alice", goal_id)
    assert again["ok"] is False
    assert await db.agent_receipts.count_documents(
        {"owner_id": "alice", "goal_id": goal_id}) == 1


@pytest.mark.asyncio
async def test_calendar_conflict_concurrent_change_wins_over_old_approval(monkeypatch):
    """If the target changes after the proposal, the old approval cannot overwrite it."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from home import manual_event as manual_calendar
    from home.manual_event import create_manual_event, get_manual_event, home_event_times, update_manual_event
    from agent.needs import NeedService
    from agent.service import AgentService

    db = AsyncMongoMockClient().test
    day = (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=6)).date().isoformat()
    first_start, first_end = home_event_times(day, "10:00", "Europe/Rome")
    second_start, second_end = home_event_times(day, "10:15", "Europe/Rome")
    first = await create_manual_event(db, "alice", title="Primo impegno",
        start=first_start, end=first_end, tz_name="Europe/Rome")
    second = await create_manual_event(db, "alice", title="Secondo impegno",
        start=second_start, end=second_end, tz_name="Europe/Rome")
    refs = ["calendar:" + first["id"], "calendar:" + second["id"]]
    await db.opportunities.insert_one({
        "id": "opp_concurrent", "owner_id": "alice", "status": "active",
        "agent_review_revision": "rev_concurrent",
    })

    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())
    monkeypatch.setattr(AgentService, "_consider_visibility", AsyncMock(return_value=None))
    monkeypatch.setattr(NeedService, "offer_to_delivery", AsyncMock())
    monkeypatch.setattr(reasoning, "decide_goal",
        AsyncMock(side_effect=AssertionError("overlap is code-grounded")))
    monkeypatch.setattr(reasoning, "interpret_calendar_conflict_choice", AsyncMock(
        return_value={"target_ref": refs[1], "requested_time": "12:00",
                      "requested_date": "", "reasoning": "secondo alle dodici"}))
    monkeypatch.setattr(reasoning, "interpret_calendar_coordination", AsyncMock(
        return_value={"mode": "direct", "reasoning": "È un impegno personale."}))
    monkeypatch.setattr(reasoning, "choose_next_action", AsyncMock(
        return_value={"decision": "execute", "step_id": "", "reasoning": "procedi"}))
    monkeypatch.setattr(reasoning, "assess_authority", AsyncMock(return_value={
        "outcome": "prepare_then_confirm", "reasoning": "modifica personale",
        "reversibility": "easily", "financial_effect": False,
        "external_communication": False, "third_party_impact": False,
        "privacy_disclosure": False, "legal_effect": False, "security_effect": False,
    }))
    # A stale proposal must stop/replan honestly, never be verified as completed.
    monkeypatch.setattr(reasoning, "reconsider", AsyncMock(return_value={
        "decision": "abandon",
        "reasoning": "L'impegno è cambiato dopo la proposta; serve ripartire dai dati correnti.",
        "revised_steps": [], "wait_hours": None, "asks": "", "ask_kind": None,
    }))
    monkeypatch.setattr(manual_calendar, "_wake", AsyncMock())

    service = AgentService(db)
    created = await service.consider("alice", situation={},
        opportunity_id="opp_concurrent", source_kind="opportunity", source_refs=refs)
    goal_id = created["goal_id"]
    coordination = await service.answer(
        "alice", goal_id, reply="Lascia il primo e sposta il secondo alle 12"
    )
    assert coordination["state"] == "waiting_for_person"
    waiting = await service.answer(
        "alice", goal_id, reply="È soltanto mio, spostalo nel calendario."
    )
    assert waiting["state"] == "awaiting_authority"

    proposed = await get_manual_event(db, "alice", second["id"])
    concurrent_start, concurrent_end = home_event_times(day, "13:00", "Europe/Rome")
    changed = await update_manual_event(
        db, "alice", second["id"],
        {"start_datetime": concurrent_start, "end_datetime": concurrent_end},
        expected_updated_at=proposed["updated_at"],
    )
    assert datetime.fromisoformat(changed["starts_at"]).strftime("%H:%M") == "13:00"

    result = await AgentService(db).authorise("alice", goal_id)
    assert result["state"] == "abandoned"
    current = await get_manual_event(db, "alice", second["id"])
    assert datetime.fromisoformat(current["attributes"]["starts_at"]).strftime("%H:%M") == "13:00"
    receipts = await db.agent_receipts.find(
        {"owner_id": "alice", "goal_id": goal_id}, {"_id": 0}
    ).to_list(10)
    assert receipts and receipts[-1]["provider_status"] == "failed"
    assert receipts[-1]["error_type"] == "event_changed"
    attempts = await db.agent_action_attempts.find(
        {"owner_id": "alice", "goal_id": goal_id}, {"_id": 0}
    ).to_list(10)
    assert len(attempts) == 1
    assert attempts[0]["status"] == "prepared"


@pytest.mark.asyncio
async def test_external_calendar_commitment_is_not_moved_without_real_confirmation(monkeypatch):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from home.manual_event import create_manual_event, get_manual_event, home_event_times
    from agent.needs import NeedService
    from agent.service import AgentService

    db = AsyncMongoMockClient().test
    day = (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=7)).date().isoformat()
    first_start, first_end = home_event_times(day, "10:00", "Europe/Rome")
    second_start, second_end = home_event_times(day, "10:15", "Europe/Rome")
    first = await create_manual_event(
        db, "alice", title="Ritiro documento",
        start=first_start, end=first_end, tz_name="Europe/Rome",
    )
    second = await create_manual_event(
        db, "alice", title="Appuntamento con il tecnico",
        start=second_start, end=second_end, tz_name="Europe/Rome",
    )
    refs = ["calendar:" + first["id"], "calendar:" + second["id"]]
    await db.opportunities.insert_one({
        "id": "opp_external", "owner_id": "alice", "status": "active",
        "agent_review_revision": "rev_external",
    })

    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())
    monkeypatch.setattr(NeedService, "offer_to_delivery", AsyncMock())
    monkeypatch.setattr(reasoning, "decide_goal",
        AsyncMock(side_effect=AssertionError("overlap is code-grounded")))
    monkeypatch.setattr(reasoning, "interpret_calendar_conflict_choice", AsyncMock(
        return_value={"target_ref": refs[1], "requested_time": "12:00",
                      "requested_date": "", "reasoning": "secondo alle dodici"}))
    monkeypatch.setattr(reasoning, "interpret_calendar_coordination", AsyncMock(
        return_value={"mode": "needs_confirmation",
                      "reasoning": "Il tecnico deve accettare il nuovo orario."}))

    service = AgentService(db)
    created = await service.consider(
        "alice", situation={}, opportunity_id="opp_external",
        source_kind="opportunity", source_refs=refs,
    )
    goal_id = created["goal_id"]
    before = await get_manual_event(db, "alice", second["id"])

    coordination = await service.answer(
        "alice", goal_id, reply="Sposta il tecnico alle 12"
    )
    assert coordination["state"] == "waiting_for_person"
    external = await service.answer(
        "alice", goal_id,
        reply="Deve confermarlo il tecnico, non posso deciderlo da solo."
    )
    assert external["state"] == "waiting_for_person"
    assert "non sposto ancora" in external["asks"].lower()

    after = await get_manual_event(db, "alice", second["id"])
    assert after["attributes"]["starts_at"] == before["attributes"]["starts_at"]
    assert await db.agent_action_attempts.count_documents(
        {"owner_id": "alice", "goal_id": goal_id}
    ) == 0
    assert await db.agent_receipts.count_documents(
        {"owner_id": "alice", "goal_id": goal_id}
    ) == 0
