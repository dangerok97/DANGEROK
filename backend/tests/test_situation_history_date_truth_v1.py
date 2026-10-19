"""A historical title is NOT evidence that the dated, localized event is the same.

Regression from the real October 19 Test 2B: a cancelled Oct 11 'panni'
record must not be reported as the Oct 19 laundry check, nor a Leesburg
weather summary as verified Tarquinia weather. All data is synthetic.
"""
from unittest.mock import AsyncMock
from datetime import datetime, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from situations.models import SituationState
from situations.followup import (
    list_situation_followups, get_situation_followup, read_followup, goal_id_for,
)
from situations.history_identity import (
    explicit_dates, record_event_day, authoritative_place,
)

OWNER = "test2b-owner"
FOREIGN = "other-owner"


def context(db, message, **extra):
    return {"db": db, "user_id": OWNER, "user_message": message, **extra}


async def insert(db, *, sid, created, updated=None, label="Tarquinia",
                 summary="Panni stesi", started=None, owner=OWNER, status="resolved"):
    state = SituationState(
        id=sid, user_id=owner, summary=summary,
        location_label=label, status=status,
        created_at=created, updated_at=updated or created,
        started_at=started,
    )
    await db.situations.insert_one(state.model_dump())


async def journal(db, *, owner, sid, when, note, step_id="step_syn"):
    await db.agent_journal.insert_one({
        "owner_id": owner, "goal_id": goal_id_for(owner, sid),
        "kind": "step_done",
        "detail": {
            "really_happened": True, "status": "succeeded", "step_id": step_id,
        },
        "at": when, "note": note,
    })


@pytest.mark.asyncio
async def test_october_nineteen_must_never_return_october_eleven_or_wrong_city(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().history_oct_day
    await insert(db, sid="sit_old_11", created="2026-10-11T12:00:00+00:00",
                 summary="Vecchi panni stesi a Tarquinia")
    await insert(db, sid="sit_today_19", created="2026-10-19T12:00:00+00:00",
                 summary="Panni stesi a Tarquinia il 19 ottobre")
    await insert(db, sid="sit_19_wrong_place", created="2026-10-19T12:01:00+00:00",
                 label="Leesburg", summary="Meteo Leesburg")
    await insert(db, sid="sit_foreign", created="2026-10-19T12:02:00+00:00",
                 owner=FOREIGN, summary="Privato")
    await journal(db, owner=OWNER, sid="sit_old_11",
                  when="2026-10-11T17:03:00+00:00",
                  note="Condizioni meteorologiche a Leesburg: umidità 92%")
    await journal(db, owner=OWNER, sid="sit_today_19",
                  when="2026-10-19T14:09:00+00:00",
                  note="Bucato asciutto secondo Leesburg")

    msg = ("Recupera la Situazione dei panni del 19 ottobre 2026 "
           "a Tarquinia. Non inventare verifiche.")
    out = await list_situation_followups({"place_query": "Tarquinia"}, context(db, msg))
    assert out.status == "ok", out
    payload = out.payload
    assert payload["requested_date"] == "2026-10-19", payload
    assert payload["requested_place"] == "tarquinia"
    assert payload["match_status"] == "matched"
    assert payload["count"] == 1
    item = payload["items"][0]
    assert item["situation_id"] == "sit_today_19"
    assert item["created_at"] == "2026-10-19T12:00:00+00:00"
    assert item["event_date"] == "2026-10-19"
    assert item["identity_date_match"] is True
    assert item["identity_place_match"] is True
    assert item["last_result"] is None, "Unstructured Leesburg note is not Tarquinia weather"
    assert item["last_checked_at"] is None
    assert item["last_step_at"] == "2026-10-19T14:09:00+00:00"
    assert item["last_result_verification"] == "location_not_proven"
    assert "Leesburg" not in str(out.model_dump())
    assert "sit_old_11" not in str(out.model_dump())
    assert "sit_foreign" not in str(out.model_dump())

    # The model may have guessed a stale exact ID; this server guard prevents
    # the bypass even when it skips the list capability entirely.
    old = await get_situation_followup(
        {"situation_id": "sit_old_11", "place_query": "Tarquinia"},
        context(db, msg),
    )
    assert old.status == "error"
    assert old.payload["reason"] == "SITUATION_DATE_NOT_USER_REQUESTED"
    assert old.payload["recorded_event_date"] == "2026-10-11"
    assert "Leesburg" not in str(old.model_dump())
    assert await db.ambient_wakes.count_documents({}) == 0
    assert await db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_no_match_is_explicit_not_reattributed_to_an_older_record(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().history_only_old
    await insert(db, sid="sit_11", created="2026-10-11T12:00:00+00:00")
    out = await list_situation_followups(
        {"place_query": "Tarquinia"},
        context(db, "Controlla i panni di Tarquinia del 19 ottobre 2026."),
    )
    assert out.status == "ok"
    assert out.payload["items"] == []
    assert out.payload["count"] == 0
    assert out.payload["match_status"] == "no_exact_match_in_recent_records"
    assert out.payload["requested_date"] == "2026-10-19"
    assert await db.situations.count_documents({"user_id": OWNER}) == 1


@pytest.mark.asyncio
async def test_source_grounding_and_timezone_boundaries_fail_closed(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().history_mismatch
    await insert(db, sid="sit_utc_local_next_day",
                 created="2026-10-19T23:30:00+00:00",
                 label="Tarquinia")
    message = "Panni a Tarquinia il 19 ottobre 2026."
    result = await list_situation_followups({"place_query": "Tarquinia"}, context(db, message))
    assert result.payload["count"] == 0, "23:30 UTC is October 20 in Rome"
    fraud = await list_situation_followups(
        {"place_query": "Leesburg"}, context(db, message)
    )
    assert fraud.status == "error"
    assert fraud.payload["reason"] == "place_not_user_grounded"

    ambiguous = await list_situation_followups({}, context(
        db, "Confronta il 19 ottobre 2026 e l'11 ottobre 2026."
    ))
    assert ambiguous.status == "error"
    assert ambiguous.payload["reason"] == "multiple_explicit_dates"

    assert explicit_dates("test 19/10/2026") == ("2026-10-19", None)
    assert explicit_dates("test 2026-10-19") == ("2026-10-19", None)
    assert explicit_dates("test 19 ottobre 2026") == ("2026-10-19", None)
    assert explicit_dates("test 31 febbraio 2026") == (None, None)
    assert authoritative_place(message, "Tarquinia", ["Tarquinia"]) == ("tarquinia", None)


@pytest.mark.asyncio
async def test_geobound_structured_evidence_can_validate_an_actual_weather_step(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().history_evidence_bound
    await insert(db, sid="sit_geo", created="2026-10-19T12:00:00+00:00")
    await journal(db, owner=OWNER, sid="sit_geo", step_id="st_geo",
                  when="2026-10-19T14:09:00+00:00",
                  note="Real weather check for Tarquinia")
    await db.agent_evidence.insert_one({
        "owner_id": OWNER, "goal_id": goal_id_for(OWNER, "sit_geo"),
        "step_id": "st_geo",
        "provenance": {
            "source_class": "real_provider", "capability": "weather.read",
            "source_refs": ["situation:sit_geo:revision:1", "google_place:tarquinia"],
        },
    })
    status = await read_followup(db, OWNER, "sit_geo")
    assert status["status"] == "stopped"
    assert status["last_checked_at"] == "2026-10-19T14:09:00+00:00"
    assert status["last_result"] == "Real weather check for Tarquinia"
    assert status["last_result_verification"] == "exact_step_geobound_evidence"

    bad = await get_situation_followup(
        {"situation_id": "sit_geo", "place_query": "Leesburg"},
        context(db, "Verifica Leesburg per il 19 ottobre 2026"),
    )
    assert bad.status == "error"
    assert bad.payload["reason"] == "SITUATION_LOCALITY_NOT_USER_REQUESTED"


@pytest.mark.asyncio
async def test_explicit_start_time_dominates_recent_update_date(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().history_declared_start
    await insert(db, sid="sit_started_11_created_19",
                 created="2026-10-19T12:00:00+00:00",
                 started="2026-10-11T12:00:00+00:00",
                 updated="2026-10-19T14:00:00+00:00")
    out = await list_situation_followups({"place_query": "Tarquinia"}, context(
        db, "Cerca i panni stesi a Tarquinia il 19 ottobre 2026."
    ))
    assert out.payload["count"] == 0
    _, origin = record_event_day({
        "created_at": "2026-10-19T12:00:00+00:00",
        "started_at": "2026-10-11T12:00:00+00:00",
    }, "Europe/Rome")
    assert origin == "started_at"


@pytest.mark.asyncio
async def test_model_omits_place_argument_but_town_is_spoken(monkeypatch):
    """Location still fences records when the LLM forgets place_query."""
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().history_omitted_place
    await insert(db, sid="sit_wrong_same_day", label="Leesburg",
                 created="2026-10-19T12:00:00+00:00",
                 summary="Synthetic weather for another city")
    msg = "Cerca i panni del 19 ottobre 2026 a Tarquinia."
    out = await list_situation_followups({}, context(db, msg))
    assert out.status == "ok"
    assert out.payload["requested_place"] == "tarquinia"
    assert out.payload["requested_date"] == "2026-10-19"
    assert out.payload["count"] == 0

    wrong = await get_situation_followup(
        {"situation_id": "sit_wrong_same_day"}, context(db, msg),
    )
    assert wrong.status == "error"
    assert wrong.payload["reason"] == "SITUATION_LOCALITY_NOT_USER_REQUESTED"
    assert "Synthetic weather" not in str(wrong.model_dump())
