"""A new dated occurrence must get its own Situation id and history.

The 19 Oct laundry test was incorrectly attached to a Situation created on
16 Oct: the stored start became 19 Oct without changing created_at.
This owner-isolated Mongo regression exercises the REAL mutation boundary,
not just a prompt. No weather, physical events, user accounts, or pushes.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from situations.models import SituationState, SituationUpdate
from situations.service import SituationService
from situations.episode_identity import fresh_declared_episode

OWNER = "synthetic-fresh-episode-owner"
OTHER = "synthetic-foreign-owner"


def when(days=0, hours=0):
    return (datetime.now(timezone.utc)
            + timedelta(days=days, hours=hours)).isoformat()


async def old_situation(db, *, status="active", summary="Panni stesi a Tarquinia",
                        started=True, temporal_scope=None):
    old = SituationState(
        id="sit_existing_previous", user_id=OWNER, session_id="ces_previous",
        summary=summary, location_label="Tarquinia",
        temporal_scope=temporal_scope, status=status,
        created_at=when(days=-3), updated_at=when(days=-2),
        started_at=when(days=-3) if started else None,
        attention_intent="Segui i panni di quel giorno",
    )
    await db.situations.insert_one(old.model_dump())
    return old


def update(*, status="update", started=None, summary="Panni appena stesi a Tarquinia"):
    return SituationUpdate(
        operation=status, situation_id="sit_existing_previous",
        expected_revision=1, summary=summary, started_at=started,
        location_label="Tarquinia", attention_intent="Controlla il meteo dei nuovi panni",
        source_refs=["situation:sit_existing_previous", "user_conversation"],
        source="user_conversation",
    )


@pytest.mark.asyncio
async def test_real_mutation_splits_new_laundry_and_never_rewrites_three_day_history(monkeypatch):
    db = AsyncMongoMockClient().fresh_episode_main
    service = SituationService(db)
    monkeypatch.setattr(service, "_note_opportunity_change", AsyncMock(return_value=None))
    old = await old_situation(db)
    old_before = await db.situations.find_one({"user_id": OWNER, "id": old.id}, {"_id": 0})
    cmd = update(started=when())
    spoken = ("TEST AUTONOMIA 2. Ho steso i panni a Tarquinia adesso. "
              "Voglio che tu segua la situazione e controlli il meteo.")

    response = await service.apply(
        user_id=OWNER, session_id="ces_new", reasoning_epoch="new_episode_oct19",
        update=cmd, user_message=spoken,
    )
    assert response["status"] == "success"
    assert response["operation"] == "create", response
    assert response["new_episode"] is True
    assert response["previous_situation_id"] == old.id
    new_id = response["situation"]["id"]
    assert new_id != old.id
    assert await db.situations.count_documents({"user_id": OWNER}) == 2
    fresh = await db.situations.find_one({"user_id": OWNER, "id": new_id}, {"_id": 0})
    assert fresh["session_id"] == "ces_new"
    assert fresh["status"] == "active"
    assert fresh["attention_intent"] == "Controlla il meteo dei nuovi panni"
    assert fresh["location_label"] == "Tarquinia"
    assert "situation:sit_existing_previous" not in fresh["source_refs"]
    assert (datetime.now(timezone.utc) - datetime.fromisoformat(fresh["created_at"])).total_seconds() < 40
    assert abs((datetime.now(timezone.utc) - datetime.fromisoformat(fresh["started_at"])).total_seconds()) < 90*60
    assert fresh["history"][0]["operation"] == "create"
    assert "new_episode_oct19" in fresh["applied_epochs"]
    old_after = await db.situations.find_one({"user_id": OWNER, "id": old.id}, {"_id": 0})
    assert old_after == old_before, "new physical occurrence must not rewrite old record"
    assert cmd.operation == "update", "caller/model proposal must not be mutated in place"

    # A repeated exact reasoning epoch is an idempotent replay, never a second
    # incident or an update to the old record.
    again = await service.apply(
        user_id=OWNER, session_id="ces_new", reasoning_epoch="new_episode_oct19",
        update=cmd, user_message=spoken,
    )
    assert again["operation"] == "create" and again["deduped"] is True
    assert again["situation"]["id"] == new_id
    assert await db.situations.count_documents({"user_id": OWNER}) == 2


@pytest.mark.asyncio
async def test_explicit_correction_of_previous_start_updates_old_not_creates(monkeypatch):
    db = AsyncMongoMockClient().episode_correction
    service = SituationService(db)
    monkeypatch.setattr(service, "_note_opportunity_change", AsyncMock(return_value=None))
    old = await old_situation(db)
    reply = await service.apply(
        user_id=OWNER, session_id="ces_same", reasoning_epoch="explicit_correction",
        update=update(started=when()),
        user_message="Ho sbagliato: in realtà ho steso i panni adesso, correggi l'orario del vecchio episodio.",
    )
    assert reply["operation"] == "update"
    assert reply.get("new_episode") is None
    assert reply["situation"]["id"] == old.id
    assert await db.situations.count_documents({"user_id": OWNER}) == 1


@pytest.mark.asyncio
async def test_assistant_name_or_older_status_does_not_create_new_event(monkeypatch):
    db = AsyncMongoMockClient().episode_status
    service = SituationService(db)
    monkeypatch.setattr(service, "_note_opportunity_change", AsyncMock(return_value=None))
    await old_situation(db)
    for msg in (
        "ORA, ho steso i panni tre giorni fa. A che punto siamo?",
        "Ho steso i panni ieri. Ora voglio soltanto sapere la situazione.",
        "Ho steso quei panni prima; sono ancora stesi adesso, continua a seguirli.",
    ):
        # The model might incorrectly supply a present started_at; the
        # conversation never declared a NEW physical occurrence.
        decision = fresh_declared_episode(
            old=SituationState.model_validate(
                await db.situations.find_one({"user_id": OWNER, "id": "sit_existing_previous"})
            ),
            update=update(started=when()), user_message=msg,
        )
        assert decision is None, msg


@pytest.mark.asyncio
async def test_new_user_episode_after_closed_prior_event_never_reopens_it(monkeypatch):
    db = AsyncMongoMockClient().episode_closed
    service = SituationService(db)
    monkeypatch.setattr(service, "_note_opportunity_change", AsyncMock(return_value=None))
    old = await old_situation(db, status="cancelled")
    r = await service.apply(
        user_id=OWNER, session_id="ces_next", reasoning_epoch="next_day_new_event",
        update=update(started=when()),
        user_message="Ho steso i panni a Tarquinia adesso, segui questi nuovi panni.",
    )
    assert r["operation"] == "create"
    assert r["new_episode"] is True
    assert await db.situations.count_documents({"user_id": OWNER, "status": "cancelled"}) == 1
    assert await db.situations.count_documents({"user_id": OWNER, "status": "active"}) == 1
    assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_predeclared_future_plan_can_start_without_duplicating_it(monkeypatch):
    db = AsyncMongoMockClient().episode_planned
    service = SituationService(db)
    monkeypatch.setattr(service, "_note_opportunity_change", AsyncMock(return_value=None))
    await old_situation(db, started=False, summary="Domani stenderò i panni a Tarquinia")
    r = await service.apply(
        user_id=OWNER, session_id="ces_planned", reasoning_epoch="plan_began",
        update=update(started=when()), user_message="Ho appena steso i panni adesso.",
    )
    assert r["operation"] == "update"
    assert r.get("new_episode") is None
    assert await db.situations.count_documents({"user_id": OWNER}) == 1


@pytest.mark.asyncio
async def test_no_owner_cross_or_unsourced_new_episode(monkeypatch):
    db = AsyncMongoMockClient().episode_scope
    service = SituationService(db)
    monkeypatch.setattr(service, "_note_opportunity_change", AsyncMock(return_value=None))
    await old_situation(db)
    foreign = await service.repo.get(OTHER, "sit_existing_previous")
    assert foreign is None
    with pytest.raises(Exception):
        await service.apply(
            user_id=OTHER, session_id="ces_not_owned", reasoning_epoch="foreign_new",
            update=update(started=when()),
            user_message="Ho steso i panni adesso.",
        )
    assert await db.situations.count_documents({"user_id": OTHER}) == 0
    assert fresh_declared_episode(
        old=SituationState.model_validate(
            await db.situations.find_one({"id": "sit_existing_previous"})
        ),
        update=update(started=when(days=-4)),
        user_message="Ho steso i panni adesso.",
    ) is None, "old model-authored start cannot establish present user occurrence"


@pytest.mark.asyncio
async def test_stale_revision_on_old_episode_cannot_block_user_new_event(monkeypatch):
    db = AsyncMongoMockClient().episode_old_revision
    service = SituationService(db)
    monkeypatch.setattr(service, "_note_opportunity_change", AsyncMock(return_value=None))
    old = await old_situation(db)
    await db.situations.update_one(
        {"id": old.id, "user_id": OWNER}, {"$set": {"revision": 7}},
    )
    before = await db.situations.find_one(
        {"id": old.id, "user_id": OWNER}, {"_id": 0},
    )
    # The AI's reference may have been one revision old while the person
    # independently began a new physical event.
    new = await service.apply(
        user_id=OWNER, session_id="ces_future",
        reasoning_epoch="new_after_old_concurrent_edits",
        update=update(started=when()),
        user_message="Ho steso adesso un altro carico e voglio seguirlo.",
    )
    assert new["new_episode"] is True
    assert new["operation"] == "create"
    assert new["situation"]["id"] != old.id
    assert await db.situations.find_one(
        {"id": old.id, "user_id": OWNER}, {"_id": 0}
    ) == before
    assert await db.situations.count_documents({"user_id": OWNER}) == 2
