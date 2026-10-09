"""v144 — real situations and stale travel concerns, owner-isolated.

No provider responses are invented and no third-party notification is sent.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

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
