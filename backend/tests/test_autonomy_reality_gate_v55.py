from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AgentBudget
from agent.service import AgentService
from opportunities.models import EvidenceRef, Opportunity
from opportunities.repository import OpportunityRepository


OWNER = "alice"
MAIL_REF = "mail:m1"
CAL_REF = "calendar:event_123"


def _future_appointment():
    """The real-world appointment in this gate must still be actionable.

    Fixed 06/10/2026 became past on 09/10/2026; that made the new source
    guard correctly refuse the test's supposedly actionable workflow.
    """
    here = datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=3)
    first = here.replace(hour=15, minute=0, second=0, microsecond=0)
    return {
        "starts_at": first.isoformat(),
        "ends_at": first.replace(hour=16).isoformat(),
        "proposed_start": first.replace(hour=16, minute=30).isoformat(),
        "proposed_end": first.replace(hour=17, minute=30).isoformat(),
        "date_label": first.strftime("%d/%m"),
    }


async def _connected_sources(db, appointment):
    now = datetime.now(timezone.utc).isoformat()
    await db.users.insert_one({
        "user_id": OWNER,
        "settings": {"location_mode": "while_using"},
        "preferences": {"place_monitoring_enabled": True},
    })
    await db.connector_instances.insert_many([
        {
            "id": "gmail_1",
            "user_id": OWNER,
            "connector_id": "mail_gmail",
            "status": "connected",
            "updated_at": now,
        },
        {
            "id": "gcal_1",
            "user_id": OWNER,
            "connector_id": "calendar_google",
            "status": "connected",
            "updated_at": now,
        },
    ])
    await db.ingestion_events.insert_one({
        "id": "ing_mail_1",
        "user_id": OWNER,
        "connector_id": "mail_gmail",
        "connector_instance_id": "gmail_1",
        "source_record_type": "email_message",
        "external_id": "m1",
        "ingested_at": now,
        "normalized_payload": {
            "message_ref": "m1",
            "subject": "Appuntamento spostato",
            "sender_relationship": "known_person",
            "received_at": now,
        },
    })

    # The source is an actual future owner-owned appointment, not merely a
    # static mocked calendar response or an orphaned connected link.
    await db.calendar_events.insert_one({
        "user_id": OWNER, "id": "event_123", "title": "Dentista",
        "status": "active", "start_at": appointment["starts_at"],
        "end_at": appointment["ends_at"], "timezone": "Europe/Rome",
    })

    from permissions.service import PermissionService
    permissions = PermissionService(db)
    await permissions.grant(
        user_id=OWNER,
        capability_id="mail.read",
        connector_id="mail_gmail",
        connector_instance_id="gmail_1",
        purpose_id="context_assembly",
        scopes=["message:read"],
        actor_type="user",
    )
    await permissions.grant(
        user_id=OWNER,
        capability_id="calendar.write",
        connector_id="calendar_google",
        connector_instance_id="gcal_1",
        purpose_id="scheduling",
        scopes=["events:write"],
        actor_type="user",
    )
    await permissions.grant(
        user_id=OWNER,
        capability_id="location.read",
        connector_id="location_device",
        purpose_id="context_assembly",
        scopes=["foreground", "places"],
        actor_type="user",
    )


async def _opportunity(db, appointment):
    await db.connected_situation_links.insert_one({
        "id": "link_1",
        "owner_id": OWNER,
        "signal_id": "sig_mail_1",
        "source_type": "email",
        "source_object_ref": "m1",
        "relationship": "same_situation",
        "target_kind": "appointment",
        "target_ref": "event_123",
        "confidence": 0.95,
        "reason_summary": "La mail parla dello stesso appuntamento.",
        "relied_on": ["subject", "calendar_time"],
        "disagreements": [{
            "about": "orario",
            "what_this_source_says": "L'orario è cambiato.",
            "what_the_other_says": f"{appointment['date_label']} alle 15:00",
        }],
        "decided_at": datetime.now(timezone.utc).isoformat(),
    })
    return await OpportunityRepository(db).save(Opportunity(
        owner_id=OWNER,
        identity_key="appointment_time:dentista",
        status="active",
        semantic_summary="Mail e calendario non concordano sull'orario del dentista.",
        why_it_matters="Partire all'orario sbagliato farebbe arrivare fuori appuntamento.",
        why_now="È arrivata una nuova comunicazione sullo stesso appuntamento.",
        initiative="prepare",
        evidence=[
            EvidenceRef(
                kind="disagreement",
                ref="link_1",
                summary="La comunicazione e il calendario dicono orari diversi.",
            )
        ],
    ))


@pytest.mark.asyncio
async def test_reality_gate_change_becomes_autonomous_work_then_exact_authority(monkeypatch):
    """
    Real cross-domain gate:
      opportunity -> durable goal -> immediate wake -> native place context ->
      one private mail read -> replan -> exact existing calendar target ->
      concrete authority handoff.

    Nothing outside ORA is changed before the final yes.
    """
    from agent import reasoning
    from agent.admission import drain
    from opportunities import snapshot
    from places.service import PlacesService
    import deps

    db = AsyncMongoMockClient().test
    appointment = _future_appointment()
    await _connected_sources(db, appointment)
    opportunity = await _opportunity(db, appointment)

    calendar_now = AsyncMock(return_value=[{
        "ref": "event_123",
        "title": "Dentista",
        "starts_at": appointment["starts_at"],
        "ends_at": appointment["ends_at"],
        "timezone": "Europe/Rome",
        "location": "Studio dentistico",
        "description": "",
        "all_day": False,
    }])
    monkeypatch.setattr(snapshot, "_calendar", calendar_now)

    monkeypatch.setattr(reasoning, "decide_goal", AsyncMock(return_value={
        "outcome": "create_goal",
        "objective": "Allineare l'appuntamento del dentista alla comunicazione verificata",
        "desired_outcome": "Il calendario contiene l'orario corretto del dentista",
        "why_now": "Una nuova comunicazione contraddice l'orario attuale.",
        "success_criteria": ["L'evento esistente usa l'orario verificato"],
        "stop_conditions": ["La comunicazione viene smentita o l'evento non esiste più"],
        "reasoning": "Serve verificare la comunicazione prima di proporre una modifica.",
    }))
    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())

    assert await drain(db, owner_id=OWNER, limit=1) == 1

    goal_row = await db.agent_goals.find_one(
        {"owner_id": OWNER, "opportunity_id": opportunity.id}, {"_id": 0}
    )
    assert goal_row is not None
    assert goal_row["source_refs"] == ["link_1", MAIL_REF, CAL_REF]
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER,
        "source_ref": f"goal:{goal_row['id']}",
        "status": "pending",
    }) == 1

    seen = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(PlacesService, "where_now", AsyncMock(return_value={
        "at_a_known_place": True,
        "place": "Casa",
        "place_id": "place_home",
        "since": seen,
        "last_seen_at": seen,
        "seconds_here": 600,
    }))

    raw_mail = (
        "Ciao, il dentista ha spostato l'appuntamento alle 16:30. "
        "CODICE-PRIVATO-NON-PERSISTERE."
    )
    mail = SimpleNamespace(body_for=AsyncMock(return_value=raw_mail))
    monkeypatch.setattr(deps, "get_gmail_service", lambda: mail)
    monkeypatch.setattr(reasoning, "distill_private_mail", AsyncMock(return_value={
        "facts": ["Il dentista ha spostato l'appuntamento alle 16:30."],
        "enough_for_this_step": True,
        "reasoning": "La comunicazione contiene il nuovo orario.",
    }))

    monkeypatch.setattr(reasoning, "make_plan", AsyncMock(return_value={
        "plan_summary": "Verificare contesto, leggere la comunicazione e correggere l'evento esistente.",
        "expected_outcome": "Calendario coerente con la comunicazione verificata.",
        "assumptions": [],
        "known_constraints": ["Nessun orario viene inventato."],
        "steps": [
            {
                "intent": "Verificare dove si trova adesso la persona",
                "step_type": "inspect",
                "capability_needed": "location.read",
                "input_refs": [],
                "parameters": {},
                "expected_result": "Contesto di luogo aggiornato",
                "external_effect": False,
                "reversibility": "easily",
            },
            {
                "intent": "Leggere la comunicazione che contraddice il calendario",
                "step_type": "inspect",
                "capability_needed": "mail.read",
                "input_refs": [MAIL_REF],
                "parameters": {},
                "expected_result": "Nuovo orario verificato",
                "external_effect": False,
                "reversibility": "easily",
            },
            {
                "intent": "Correggere l'evento dopo aver verificato il nuovo orario",
                "step_type": "execute",
                "capability_needed": "calendar.write",
                "input_refs": [CAL_REF],
                "parameters": {"title": "Dentista"},
                "expected_result": "L'evento esistente usa il nuovo orario",
                "external_effect": True,
                "effect_type": "modify",
                "effect_target": "Dentista",
                "reaches_somebody_else": False,
                "reversibility": "easily",
            },
        ],
    }))

    choose_calls = []

    async def choose_next(goal, *, plan, candidates, evidence, capabilities, clock_context=None, language="it"):
        choose_calls.append([c.get("capability_needed") for c in candidates])
        mail_steps = [c for c in candidates if c.get("capability_needed") == "mail.read"]
        if mail_steps:
            return {
                "decision": "execute",
                "step_id": mail_steps[0]["id"],
                "reasoning": "La mail è la fonte che può stabilire il nuovo orario.",
                "asks": "",
                "ask_kind": None,
            }
        calendar_steps = [
            c for c in candidates if c.get("capability_needed") == "calendar.write"
        ]
        complete = [
            c for c in calendar_steps
            if (c.get("execution_parameters") or c.get("prepared_parameters") or {}).get("starts_at")
        ]
        if complete:
            return {
                "decision": "execute",
                "step_id": complete[0]["id"],
                "reasoning": "La modifica è ora completamente preparata.",
                "asks": "",
                "ask_kind": None,
            }
        return {
            "decision": "replan",
            "step_id": "",
            "reasoning": "Il nuovo orario è noto e il passo di modifica va aggiornato.",
            "asks": "",
            "ask_kind": None,
        }

    monkeypatch.setattr(reasoning, "choose_next_action", choose_next)

    async def reconsider(goal, *, plan, what_happened, capabilities, clock_context=None, language="it"):
        old = next(
            step for step in plan["steps"]
            if step.get("capability_needed") == "calendar.write"
            and step.get("status") == "pending"
        )
        return {
            "decision": "modify",
            "reasoning": "Sostituisco il passo incompleto con la modifica verificata.",
            "replace_step_ids": [old["id"]],
            "revised_steps": [{
                "intent": "Applicare il nuovo orario verificato al Dentista",
                "step_type": "execute",
                "capability_needed": "calendar.write",
                "input_refs": [CAL_REF],
                "parameters": {
                    "title": "Dentista",
                    "starts_at": appointment["proposed_start"],
                    "ends_at": appointment["proposed_end"],
                    "timezone": "Europe/Rome",
                },
                "expected_result": "Dentista alle 16:30 nello stesso evento",
                "external_effect": True,
                "effect_type": "modify",
                "effect_target": "Dentista",
                "reaches_somebody_else": False,
                "reversibility": "easily",
            }],
            "wait_hours": None,
            "asks": "",
            "ask_kind": None,
        }

    monkeypatch.setattr(reasoning, "reconsider", reconsider)

    service = AgentService(db)
    monkeypatch.setattr(service, "_consider_visibility", AsyncMock())
    monkeypatch.setattr(service, "_authority_for", AsyncMock(return_value=SimpleNamespace(
        effective_outcome="ask_authority",
        code_reason="specific_write_needs_user",
        reasoning="La modifica è pronta ma serve il via libera.",
        public=lambda: {"outcome": "ask_authority"},
    )))
    monkeypatch.setattr(
        service.authority,
        "effective_authority",
        AsyncMock(return_value=SimpleNamespace(
            may_execute=False,
            reason_code="specific_write_needs_user",
            public=lambda: {"may_execute": False},
        )),
    )

    result = await service.advance(
        OWNER,
        goal_row["id"],
        worker_id="ambient:reality_gate",
        budget=AgentBudget(max_cognitive_calls=8, max_capability_calls=8),
    )

    assert result["state"] == "awaiting_authority"
    assert "Dentista" in result["asks"]
    assert f"{appointment['date_label']} alle 16:30" in result["asks"]
    assert "Vuoi che applichi questa modifica?" in result["asks"]

    plan = await service.repo.plan_for(OWNER, goal_row["id"])
    assert plan is not None

    location_step = next(s for s in plan.steps if s.capability_needed == "location.read")
    mail_step = next(s for s in plan.steps if s.capability_needed == "mail.read")
    old_calendar = next(
        s for s in plan.steps
        if s.intent.startswith("Correggere l'evento dopo")
    )
    prepared_calendar = next(
        s for s in plan.steps
        if s.intent.startswith("Applicare il nuovo orario")
    )

    assert location_step.status == "succeeded"
    assert mail_step.status == "succeeded"
    assert old_calendar.status == "skipped"
    assert old_calendar.note == "Sostituito dal piano aggiornato."
    assert prepared_calendar.status == "blocked"
    assert service.executor._intent_for(
        OWNER,
        await service.repo.get_goal(OWNER, goal_row["id"]),
        prepared_calendar,
    ).target_ref == CAL_REF

    evidence = await db.agent_evidence.find(
        {"owner_id": OWNER, "goal_id": goal_row["id"]}, {"_id": 0}
    ).to_list(50)
    serialized = str(evidence)
    assert "Casa" in serialized
    assert "16:30" in serialized
    assert "CODICE-PRIVATO-NON-PERSISTERE" not in serialized

    saved_goal = await service.repo.get_goal(OWNER, goal_row["id"])
    assert saved_goal is not None
    assert saved_goal.status == "waiting"
    assert saved_goal.requires_user_authority is True
    assert saved_goal.next_run_at is None


@pytest.mark.asyncio
async def test_replan_never_rewrites_completed_work_or_unknown_step_ids(monkeypatch):
    """Only explicitly named still-open steps may be retired by a modify replan."""
    from agent.models import ActionPlan, ActionStep, AgentRun
    from agent import reasoning

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = SimpleNamespace(
        id="goal_1",
        owner_id=OWNER,
        for_ai=lambda: {"objective": "x"},
    )
    done = ActionStep(
        id="done_1",
        ordinal=0,
        intent="Fatto già verificato",
        step_type="inspect",
        capability_needed="information.read",
        status="succeeded",
    )
    pending = ActionStep(
        id="pending_1",
        ordinal=1,
        intent="Vecchia strada",
        step_type="execute",
        capability_needed="calendar.write",
        status="pending",
    )
    plan = ActionPlan(
        owner_id=OWNER,
        goal_id="goal_1",
        status="active",
        steps=[done, pending],
    )
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=[]))
    monkeypatch.setattr(reasoning, "reconsider", AsyncMock(return_value={
        "decision": "modify",
        "reasoning": "Cambio solo ciò che è ancora da fare.",
        "replace_step_ids": ["done_1", "pending_1", "invented_id"],
        "revised_steps": [{
            "intent": "Nuova strada",
            "step_type": "inspect",
            "capability_needed": "information.read",
            "input_refs": [],
            "parameters": {},
            "expected_result": "Nuovo controllo",
            "external_effect": False,
            "reversibility": "easily",
        }],
    }))

    out = await service._reconsider(
        OWNER,
        goal,
        plan,
        AgentRun(owner_id=OWNER, goal_id="goal_1"),
        AgentBudget(max_cognitive_calls=8),
        what_happened={"problem": "nuova evidenza"},
        language="it",
    )

    assert out is None
    assert done.status == "succeeded"
    assert pending.status == "skipped"
    assert pending.note == "Sostituito dal piano aggiornato."
    assert plan.steps[-1].intent == "Nuova strada"
