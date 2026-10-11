"""v144 — real situations and stale travel concerns, owner-isolated.

No provider responses are invented and no third-party notification is sent.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AutonomousGoal
from agent.situation_cards import concrete_need, situation_card
from opportunities.models import EvidenceRef, Opportunity
from opportunities.source_lifecycle import perishable_opportunity_expired, source_event_expired
from opportunities.surfacing import SurfacingService
from situations.models import SituationState
from situations.repository import SituationRepository


@pytest.mark.asyncio
async def test_legacy_calendar_disagreement_expires_from_actual_owner_event():
    db = AsyncMongoMockClient().updates_v144
    owner = "synthetic-owner"
    await db.ingestion_events.insert_one({
        "user_id": owner, "source_record_type": "calendar_event",
        "external_id": "trip-2026", "ingestion_status": "active",
        "ingested_at": "2026-10-01T10:00:00+00:00",
        "normalized_payload": {
            "title": "Partenza", "starts_at": "2026-10-08T07:00:00+02:00",
            "ends_at": "2026-10-08T09:00:00+02:00",
        },
    })
    await db.connected_situation_links.insert_one({
        "owner_id": owner, "id": "clash-trip-2026", "target_kind": "appointment",
        "target_ref": "trip-2026",
    })
    notice = Opportunity(
        owner_id=owner, identity_key="travel_time_conflict",
        status="active", surface_state="surfaced", time_sensitivity="perishable",
        semantic_summary="Orari discordanti del viaggio",
        why_it_matters="Decidere prima della partenza",
        evidence=[EvidenceRef(kind="disagreement", ref="clash-trip-2026")],
    )
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    assert await perishable_opportunity_expired(db, owner, notice, now=now)
    assert await SurfacingService(db)._current(owner, notice, now.isoformat()) is False
    assert not await perishable_opportunity_expired(db, "another-owner", notice, now=now)


@pytest.mark.asyncio
async def test_unknown_or_future_calendar_date_must_not_be_invented():
    db = AsyncMongoMockClient().future_v144
    await db.calendar_events.insert_one({
        "user_id": "owner", "id": "e2", "status": "active",
        "start_at": "2026-10-15T08:00:00+02:00",
        "end_at": "2026-10-15T10:00:00+02:00",
    })
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    assert not await source_event_expired(db, "owner", ["e2"], now=now)
    assert not await source_event_expired(db, "owner", ["does-not-exist"], now=now)
    assert not await source_event_expired(db, "other-owner", ["e2"], now=now)


@pytest.mark.asyncio
async def test_situation_card_reuses_saved_monitor_and_exposes_its_real_status(monkeypatch):
    import agent.situation_cards as cards

    db = AsyncMongoMockClient().situation_v144
    state = SituationState(
        id="sit_synthetic_laundry", user_id="owner", session_id="session-own",
        summary="Panni sul balcone",
        current_state_summary="Panni ancora fuori",
        expected_outcome_summary="Sapere se è utile ritirarli",
        attention_intent="Riconsiderare meteo e condizioni utili",
    )
    await SituationRepository(db).insert(state)
    goal = AutonomousGoal(
        id="gol_sit_synthetic", owner_id="owner", status="waiting",
        source_kind="situation_followup", source_refs=["situation:sit_synthetic_laundry"],
        objective="Generic internal monitor", desired_outcome="Risultato utile",
    )
    async def read(db_, owner, sid):
        assert owner == "owner" and sid == state.id
        return {
            "status": "scheduled", "next_check_label": "oggi alle 18:00",
            "next_check_at": "2026-10-09T18:00:00+02:00",
            "notify_when": "Se è prevista pioggia vicino a casa",
            "purpose": "Verificare il meteo senza supporre che i panni siano asciutti",
        }
    monkeypatch.setattr(cards, "read_followup", read)
    result = await situation_card(db, "owner", goal)
    assert result["situation"]["summary"] == "Panni sul balcone"
    assert result["situation"]["revision"] == 1
    assert result["situation"]["session_id"] == "session-own"
    assert result["situation"]["notify_when"].startswith("Se è prevista")
    assert (await situation_card(db, "other-owner", goal)) == {"inactive": True}


def test_internal_generic_need_is_never_presented_as_question():
    assert concrete_need(SimpleNamespace(
        what_is_missing="Mi manca un'informazione che sai solo tu",
        summary="Mi serve una tua risposta per continuare",
    )) == ""
    assert concrete_need(SimpleNamespace(
        what_is_missing="Dimmi se hai già riportato dentro i panni",
        summary="Serve la tua conferma",
    )) == "Dimmi se hai già riportato dentro i panni"


async def _monitor_fixture(monkeypatch, *, wake_status="pending"):
    import deps
    from ambient.models import AmbientWake
    from opportunities.discovery import OpportunityDiscovery

    db = AsyncMongoMockClient().stop_v144
    monkeypatch.setattr(deps, "db", db)
    monkeypatch.setattr(OpportunityDiscovery, "note", AsyncMock(return_value={"outcome": "accepted"}))
    situation = SituationState(
        id="sit_active", user_id="owner", session_id="session-own",
        summary="Situazione temporanea", attention_intent="Controllare prima di avvisare",
        next_check_summary="Verificare dopo nuove informazioni",
    )
    await SituationRepository(db).insert(situation)
    goal = AutonomousGoal(
        id="gol_sit_stop", owner_id="owner", status="waiting",
        source_kind="situation_followup", source_refs=["situation:sit_active"],
        objective="Monitor", desired_outcome="Controllo",
        next_run_at=(datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
    )
    await db.agent_goals.insert_one(goal.model_dump())
    wake = AmbientWake(
        owner_id="owner", source_ref=f"goal:{goal.id}", reason="opportunity_revisit",
        scheduled_for=goal.next_run_at, status=wake_status,
    )
    await db.ambient_wakes.insert_one(wake.model_dump())
    return db, situation, goal, wake


@pytest.mark.asyncio
async def test_user_can_stop_alerts_without_claiming_situation_resolved(monkeypatch):
    from agent.router import SituationAlertsIn, situation_alerts
    from agent.service import AgentService
    from ambient.models import AmbientWake

    db, situation, goal, _ = await _monitor_fixture(monkeypatch)
    foreign = AmbientWake(
        owner_id="other-owner", source_ref=f"goal:{goal.id}", reason="opportunity_revisit",
        scheduled_for=goal.next_run_at,
    )
    await db.ambient_wakes.insert_one(foreign.model_dump())
    cancelled = []
    real_cancel = AgentService.cancel

    async def cancel(service, owner, goal_id, *, reason=""):
        cancelled.append((owner, goal_id))
        return await real_cancel(service, owner, goal_id, reason=reason)

    monkeypatch.setattr(AgentService, "cancel", cancel)
    result = await situation_alerts(
        goal.id, SituationAlertsIn(decision="stop_alerts", expected_revision=1),
        user={"user_id": "owner"},
    )
    assert result["monitor_stopped"]
    after = await SituationRepository(db).get("owner", situation.id)
    assert after.status == "changed"
    assert not after.attention_intent
    assert not after.next_check_summary
    assert cancelled == [("owner", goal.id)]
    saved = await db.agent_goals.find_one({"id": goal.id, "owner_id": "owner"})
    assert saved["status"] == "cancelled" and saved["next_run_at"] is None
    assert "monitoraggio" in saved["rationale"]
    assert "risolta" not in saved["rationale"] and "annullata" not in saved["rationale"]
    assert await db.ambient_wakes.count_documents({
        "owner_id": "owner", "source_ref": f"goal:{goal.id}",
        "status": {"$in": ["pending", "claimed"]},
    }) == 0
    assert (await db.ambient_wakes.find_one({"id": foreign.id}))["status"] == "pending"


@pytest.mark.asyncio
async def test_stop_alerts_rejects_cancel_success_without_persisted_goal_stop(monkeypatch):
    from fastapi import HTTPException
    from agent.router import SituationAlertsIn, situation_alerts
    from agent.service import AgentService

    db, situation, goal, _ = await _monitor_fixture(monkeypatch)
    cancel = AsyncMock(return_value={"ok": True, "state": "cancelled"})
    monkeypatch.setattr(AgentService, "cancel", cancel)
    with pytest.raises(HTTPException) as raised:
        await situation_alerts(goal.id, SituationAlertsIn(decision="stop_alerts", expected_revision=1),
                               user={"user_id": "owner"})
    assert raised.value.status_code == 409 and raised.value.detail == "monitor_not_stopped"
    assert cancel.await_count == 1
    assert (await db.agent_goals.find_one({"id": goal.id}))["status"] == "waiting"
    after = await SituationRepository(db).get("owner", situation.id)
    assert after.status == "changed" and not after.attention_intent


@pytest.mark.asyncio
@pytest.mark.parametrize("wake_status", ["pending", "claimed"])
async def test_stop_alerts_rejects_durable_goal_stop_with_uncancelled_wake(monkeypatch, wake_status):
    from fastapi import HTTPException
    from agent.router import SituationAlertsIn, situation_alerts
    from ambient.repository import AmbientRepository

    db, _, goal, wake = await _monitor_fixture(monkeypatch, wake_status=wake_status)
    monkeypatch.setattr(AmbientRepository, "cancel_for", AsyncMock(
        side_effect=RuntimeError("synthetic wake persistence failure"),
    ))
    with pytest.raises(HTTPException) as raised:
        await situation_alerts(goal.id, SituationAlertsIn(decision="stop_alerts", expected_revision=1),
                               user={"user_id": "owner"})
    assert raised.value.status_code == 409 and raised.value.detail == "monitor_not_stopped"
    assert (await db.agent_goals.find_one({"id": goal.id}))["status"] == "cancelled"
    assert (await db.ambient_wakes.find_one({"id": wake.id}))["status"] == wake_status


@pytest.mark.asyncio
async def test_user_resolution_closes_situation_and_confirms_persisted_stop(monkeypatch):
    from agent.router import SituationAlertsIn, situation_alerts

    db, situation, goal, wake = await _monitor_fixture(monkeypatch)
    result = await situation_alerts(
        goal.id, SituationAlertsIn(decision="resolved", expected_revision=1), user={"user_id": "owner"},
    )
    assert result == {"ok": True, "decision": "resolved", "monitor_stopped": True}
    assert (await SituationRepository(db).get("owner", situation.id)).status == "resolved"
    assert (await db.agent_goals.find_one({"id": goal.id}))["status"] == "cancelled"
    assert (await db.ambient_wakes.find_one({"id": wake.id}))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_stop_alerts_does_not_cancel_a_new_cycle_or_confirm_old_stop(monkeypatch):
    from fastapi import HTTPException
    from agent.router import SituationAlertsIn, situation_alerts
    from agent.service import AgentService
    from opportunities.discovery import OpportunityDiscovery

    db, situation, goal, _ = await _monitor_fixture(monkeypatch)
    real_cancel = AgentService.cancel
    cancelled = []

    async def cancel(service, owner, goal_id, *, reason=""):
        cancelled.append((owner, goal_id))
        return await real_cancel(service, owner, goal_id, reason=reason)

    async def newer_cycle(*args, **kwargs):
        # Another request lands after the first cancellation, before apply
        # returns. Its source and goal are now the authoritative newer cycle.
        await db.situations.update_one({"id": situation.id, "user_id": "owner"}, {"$set": {
            "revision": 3, "attention_intent": "Nuova richiesta esplicita di controllo",
        }})
        await db.agent_goals.update_one({"id": goal.id, "owner_id": "owner"}, {"$set": {
            "status": "active", "next_run_at": goal.next_run_at,
        }})
        return {"outcome": "accepted"}

    monkeypatch.setattr(AgentService, "cancel", cancel)
    monkeypatch.setattr(OpportunityDiscovery, "note", newer_cycle)
    with pytest.raises(HTTPException) as raised:
        await situation_alerts(goal.id, SituationAlertsIn(decision="stop_alerts", expected_revision=1),
                               user={"user_id": "owner"})
    assert raised.value.status_code == 409 and raised.value.detail == "monitor_not_stopped"
    assert cancelled == [("owner", goal.id)]
    after = await SituationRepository(db).get("owner", situation.id)
    assert after.revision == 3 and after.attention_intent == "Nuova richiesta esplicita di controllo"
    assert (await db.agent_goals.find_one({"id": goal.id}))["status"] == "active"


@pytest.mark.asyncio
async def test_stale_revision_cannot_cancel_a_newer_situation(monkeypatch):
    import deps
    from fastapi import HTTPException
    from agent.router import SituationAlertsIn, situation_alerts

    db = AsyncMongoMockClient().revision_v144
    monkeypatch.setattr(deps, "db", db)
    state = SituationState(id="sit_updated", user_id="owner", summary="Stato aggiornato", revision=2)
    await SituationRepository(db).insert(state)
    goal = AutonomousGoal(
        id="gol_sit_revised", owner_id="owner", source_kind="situation_followup",
        source_refs=["situation:sit_updated"], objective="Monitoraggio",
        desired_outcome="Esito",
    )
    await db.agent_goals.insert_one(goal.model_dump())
    with pytest.raises(HTTPException) as raised:
        await situation_alerts(goal.id, SituationAlertsIn(decision="resolved", expected_revision=1),
                               user={"user_id": "owner"})
    assert raised.value.status_code == 409
    assert (await SituationRepository(db).get("owner", state.id)).status == "active"
