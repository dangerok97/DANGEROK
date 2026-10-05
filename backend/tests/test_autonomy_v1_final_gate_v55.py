from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import (
    ActionPlan,
    ActionStep,
    AgentBudget,
    AgentRun,
    AuthorityAssessment,
)
from agent.service import AgentService
from connected.models import ConnectedSignal, FieldChange
from connected.situations import record_link
from opportunities.models import EvidenceRef, Opportunity
from opportunities.repository import OpportunityRepository
from permissions.service import PermissionService


class CalendarHarness:
    def __init__(self):
        from connectors.google_calendar.provider import FakeGoogleCalendarProvider

        self.provider = FakeGoogleCalendarProvider()
        self.provider.seed_calendar(
            calendar_id="primary", summary="Primary", primary=True
        )

    async def _get_access_token(self, *, user_id, instance):
        return "fake-access"

    async def list_calendars_for_instance(self, *, user_id, instance_id):
        return [{"id": "primary", "primary": True}]


def _iso_after(hours: int) -> str:
    return (
        datetime.now(timezone.utc) + timedelta(hours=hours)
    ).replace(second=0, microsecond=0).isoformat()


def _signal() -> ConnectedSignal:
    return ConnectedSignal(
        owner_id="alice",
        source_id="gmail_1",
        source_type="email",
        signal_type="email.message.added",
        observed_at=datetime.now(timezone.utc).isoformat(),
        effective_at=datetime.now(timezone.utc).isoformat(),
        source_object_ref="m1",
        payload_summary="È arrivato un messaggio: «Dentista spostato».",
        after="Dentista spostato",
        changed_fields=[FieldChange(field="subject", after="Dentista spostato")],
        provenance={"thread_ref": "t1"},
    )


async def _permissions_and_sources(db):
    now = datetime.now(timezone.utc).isoformat()
    await db.connector_instances.insert_many([
        {
            "id": "gmail_1",
            "user_id": "alice",
            "connector_id": "mail_gmail",
            "status": "connected",
            "updated_at": now,
        },
        {
            "id": "gcal_1",
            "user_id": "alice",
            "connector_id": "calendar_google",
            "status": "connected",
            "metadata": {"default_calendar_id": "primary"},
            "updated_at": now,
        },
    ])
    permissions = PermissionService(db)
    await permissions.grant(
        user_id="alice",
        capability_id="mail.read",
        connector_id="mail_gmail",
        connector_instance_id="gmail_1",
        purpose_id="context_assembly",
        scopes=["body:read"],
        actor_type="user",
    )
    await permissions.grant(
        user_id="alice",
        capability_id="calendar.write",
        connector_id="calendar_google",
        connector_instance_id="gcal_1",
        purpose_id="scheduling",
        scopes=["events:write"],
        actor_type="user",
    )


@pytest.mark.asyncio
async def test_autonomy_v1_reality_gate_email_change_to_verified_calendar_update(
    monkeypatch,
):
    """
    AUTONOMY V1 REALITY GATE

    One external change must survive every boundary:
      signal -> linked situation -> opportunity -> autonomous goal/wake
      -> transient source read -> bounded evidence -> prepared external effect
      -> exact authority question -> one-time approval -> real provider write
      -> provider read-back -> verified completion.

    Model calls are mocked because this test is about orchestration truth, not
    model quality. Storage, permission, source linking, evidence, authority,
    provider effect and verification gates are real application code.
    """
    db = AsyncMongoMockClient().test
    await _permissions_and_sources(db)

    old_start = _iso_after(24)
    new_start = _iso_after(26)
    old_end = (
        datetime.fromisoformat(old_start) + timedelta(hours=1)
    ).isoformat()
    new_end = (
        datetime.fromisoformat(new_start) + timedelta(hours=1)
    ).isoformat()

    # The current calendar fact used by admission/source-context.
    await db.calendar_events.insert_one({
        "id": "event_123",
        "user_id": "alice",
        "title": "Dentista",
        "start_at": old_start,
        "end_at": old_end,
        "all_day": False,
        "location": "Studio dentistico",
        "status": "active",
    })

    # Gmail metadata proves ORA observed this exact message before mail.read.
    await db.ingestion_events.insert_one({
        "id": "ing_mail_1",
        "user_id": "alice",
        "connector_id": "mail_gmail",
        "connector_instance_id": "gmail_1",
        "source_record_type": "email_message",
        "external_id": "m1",
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "normalized_payload": {
            "message_ref": "m1",
            "subject": "Dentista spostato",
            "sender_relationship": "known_person",
            "received_at": datetime.now(timezone.utc).isoformat(),
        },
    })

    # 1. External observation is linked to a real, already-known appointment.
    link = await record_link(
        db,
        "alice",
        _signal(),
        {
            "relationship": "same_situation",
            "target_ref": "event_123",
            "confidence": 0.95,
            "why": "La mail riguarda lo stesso appuntamento.",
            "relied_on": ["subject", "calendar"],
        },
        candidate={
            "kind": "appointment",
            "ref": "event_123",
            "what": "Dentista",
            "when": old_start,
            "last_observed": datetime.now(timezone.utc).isoformat(),
            "how_directly_it_knows": "the calendar itself holds this appointment",
        },
    )
    propagated = await db.meaningful_changes.find_one(
        {
            "owner_id": "alice",
            "source": "situations",
            "entity_ref": "event_123",
        },
        {"_id": 0},
    )
    assert propagated is not None
    assert propagated["kind"] == "linked_source_changed"

    # 2. Opportunity admission must inherit the actionable sources behind the
    # disagreement, then create a durable autonomous goal and first wake.
    opportunity = Opportunity(
        owner_id="alice",
        identity_key="dentista:orario:discordante",
        status="active",
        semantic_summary="Mail e calendario non concordano sull'orario del dentista.",
        why_it_matters="Partenza e agenda dipendono dall'orario corretto.",
        why_now="È arrivata una nuova comunicazione collegata all'appuntamento.",
        initiative="prepare",
        what_ora_can_do="Verificare la comunicazione e preparare la correzione.",
        evidence=[
            EvidenceRef(
                kind="disagreement",
                ref=link["id"],
                summary="La comunicazione e il calendario dicono cose diverse.",
            )
        ],
    )
    opportunity = await OpportunityRepository(db).save(opportunity)

    from agent import reasoning
    monkeypatch.setattr(
        reasoning,
        "decide_goal",
        AsyncMock(return_value={
            "outcome": "create_goal",
            "objective": "Allineare il dentista all'orario verificato",
            "desired_outcome": "L'evento esistente mostra il nuovo orario verificato",
            "why_now": "Una comunicazione nuova contraddice il calendario.",
            "success_criteria": [
                "Il messaggio rilevante è stato verificato",
                "L'evento esistente ha l'orario confermato",
            ],
            "stop_conditions": [],
            "reasoning": "C'è una conseguenza concreta da risolvere.",
        }),
    )
    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())

    from agent.admission import drain
    assert await drain(db, owner_id="alice", limit=1) == 1

    goal_row = await db.agent_goals.find_one(
        {"owner_id": "alice", "opportunity_id": opportunity.id},
        {"_id": 0},
    )
    assert goal_row is not None
    assert link["id"] in goal_row["source_refs"]
    assert "mail:m1" in goal_row["source_refs"]
    assert "calendar:event_123" in goal_row["source_refs"]
    assert await db.ambient_wakes.count_documents({
        "owner_id": "alice",
        "source_ref": f"goal:{goal_row['id']}",
        "status": "pending",
    }) == 1

    service = AgentService(db)
    goal = await service.repo.get_goal("alice", goal_row["id"])
    assert goal is not None

    # 3. Read one private mail body transiently. Only the distilled fact may
    # enter durable agent evidence.
    raw_body = (
        "Ciao, il dentista è stato spostato alle 16:30. "
        "SEGRETO-RAW-991 che non deve diventare evidenza."
    )
    gmail = type("Gmail", (), {})()
    gmail.body_for = AsyncMock(return_value=raw_body)
    monkeypatch.setattr("deps.get_gmail_service", lambda: gmail)
    monkeypatch.setattr(
        reasoning,
        "distill_private_mail",
        AsyncMock(return_value={
            "facts": ["Il dentista è stato spostato alle 16:30."],
            "enough_for_this_step": True,
            "reasoning": "La comunicazione contiene il nuovo orario.",
        }),
    )

    read_step = ActionStep(
        ordinal=0,
        intent="Leggere il messaggio collegato all'appuntamento.",
        step_type="inspect",
        capability_needed="mail.read",
        input_refs=["mail:m1"],
        expected_result="Il nuovo orario comunicato è noto.",
    )
    read_result = await service.executor.run(
        "alice",
        goal,
        read_step,
        may_touch_the_world=False,
        budget=AgentBudget(),
    )
    assert read_result.status == "succeeded"
    evidence = await service.evidence.for_goal("alice", goal.id)
    durable = " ".join(e.claim for e in evidence)
    assert "16:30" in durable
    assert "SEGRETO-RAW-991" not in durable
    assert raw_body not in durable

    # 4. A complete cross-domain modification must bind to the calendar ref,
    # not to the link or mail ref, and background work must stop at authority.
    modify_step = ActionStep(
        ordinal=1,
        intent="Spostare il dentista all'orario verificato.",
        step_type="execute",
        capability_needed="calendar.write",
        input_refs=[link["id"], "mail:m1", "calendar:event_123"],
        expected_result="L'evento Dentista risulta al nuovo orario verificato.",
        external_effect=True,
        effect_type="modify",
        effect_target="Dentista",
        reaches_somebody_else=False,
        reversibility="easily",
        parameters={
            "title": "Dentista",
            "starts_at": new_start,
            "ends_at": new_end,
            "timezone": "Europe/Rome",
        },
    )
    plan = ActionPlan(
        owner_id="alice",
        goal_id=goal.id,
        status="active",
        plan_summary="Verificare la comunicazione e correggere l'evento esistente.",
        expected_outcome=goal.desired_outcome,
        steps=[modify_step],
    )
    await service.repo.save_plan(plan)

    assessment = AuthorityAssessment(
        step_id=modify_step.id,
        capability="calendar.write",
        model_outcome="ask_before_execution",
        effective_outcome="prepare_then_confirm",
        reasoning="È una modifica esterna reversibile.",
        reversibility="easily",
    )
    monkeypatch.setattr(
        service,
        "_authority_for",
        AsyncMock(return_value=assessment),
    )

    background = await service._do_step(
        "alice",
        goal,
        plan,
        modify_step,
        AgentRun(owner_id="alice", goal_id=goal.id, background=True),
        AgentBudget(),
        language="it",
    )
    assert background is not None
    assert background["state"] == "awaiting_authority"
    assert "Dentista" in background["asks"]
    assert "16:30" in background["asks"]
    assert "event_123" not in background["asks"]

    # 5. Use the public authorisation path to mint a one-time yes bound to the
    # exact prepared effect. Do not execute inside this call yet.
    with monkeypatch.context() as local:
        local.setattr(
            service,
            "advance",
            AsyncMock(return_value={"ok": True, "state": "authorised_for_test"}),
        )
        authorised = await service.authorise("alice", goal.id)
    assert authorised["state"] == "authorised_for_test"

    goal = await service.repo.get_goal("alice", goal.id)
    plan = await service.repo.plan_for("alice", goal.id)
    assert goal is not None and plan is not None
    step = plan.steps[0]
    assert step.status == "pending"
    assert goal.requires_user_authority is False

    # 6. Foreground continuation consumes that exact consent, performs the real
    # adapter update against a fake Google provider, and reads it back.
    import agent.effects as effects

    calendar = CalendarHarness()
    calendar.provider.seed_event(
        calendar_id="primary",
        event={
            "id": "event_123",
            "summary": "Dentista",
            "description": "",
            "start": {"dateTime": old_start},
            "end": {"dateTime": old_end},
            "status": "confirmed",
            "etag": "v1",
        },
    )
    monkeypatch.setattr(effects, "_calendar_service", lambda _db: calendar)

    outcome = await service._do_step(
        "alice",
        goal,
        plan,
        step,
        AgentRun(owner_id="alice", goal_id=goal.id, background=False),
        AgentBudget(),
        language="it",
    )
    assert outcome is None

    changed = calendar.provider.events["primary"]["event_123"]
    assert changed["start"]["dateTime"] == new_start
    assert len(calendar.provider.events["primary"]) == 1

    receipts = await service.executor.receipts_for("alice", goal.id)
    assert receipts
    assert receipts[-1]["provider_status"] == "succeeded"
    assert receipts[-1]["external_ref"] == "event_123"

    consents = await db.agent_authority_consents.find(
        {"owner_id": "alice"}, {"_id": 0}
    ).to_list(10)
    assert len(consents) == 1
    assert consents[0]["used_at"]

    # 7. Completion is allowed only after the real read-back evidence exists.
    monkeypatch.setattr(
        reasoning,
        "verify_goal",
        AsyncMock(return_value={
            "outcome": "achieved",
            "reasoning": "Il calendario riletto mostra l'orario verificato.",
            "what_is_missing": "",
            "revisit_in_hours": None,
            "relied_on": [],
            "criteria_met": list(goal.success_criteria),
        }),
    )
    monkeypatch.setattr(service, "_observe_life_change", AsyncMock())

    goal = await service.repo.get_goal("alice", goal.id)
    plan = await service.repo.plan_for("alice", goal.id)
    result = await service._finish(
        "alice",
        goal,
        plan,
        AgentRun(owner_id="alice", goal_id=goal.id),
        AgentBudget(),
        language="it",
    )

    assert result["state"] == "completed"
    final_goal = await service.repo.get_goal("alice", goal.id)
    assert final_goal is not None
    assert final_goal.status == "completed"

    all_evidence = await service.evidence.for_goal("alice", goal.id)
    assert any(e.provenance.provider == "gmail_live_body" for e in all_evidence)
    assert any(e.provenance.provider == "calendar" for e in all_evidence)

    saved_opp = await db.opportunities.find_one(
        {"id": opportunity.id, "owner_id": "alice"}, {"_id": 0}
    )
    assert saved_opp["status"] == "resolved"
