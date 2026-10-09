"""V143 owner-scoped, explicit lifecycle feedback — no invented completion."""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from situations.models import SituationState
from situations.router import SituationFeedback, update_situation_feedback
from situations.repository import SituationRepository


OWNER, SID = "synthetic-owner", "sit_feedback_test"


async def fixture(monkeypatch, db):
    import situations.router as module
    from situations.service import SituationService

    monkeypatch.setattr(module, "db", db)
    # The test examines the actual governed Situation and history; keep any
    # independent discovery provider out of this local test.
    monkeypatch.setattr(SituationService, "_note_opportunity_change", AsyncMock())
    await SituationRepository(db).insert(SituationState(
        id=SID, user_id=OWNER, summary="Attività temporanea avviata.",
        facts=["L'attività è stata lasciata all'aperto."],
        current_state_summary="All'aperto",
        attention_intent="Avvisami soltanto se il rischio cambia.",
    ))
    return {"user_id": OWNER}


@pytest.mark.asyncio
async def test_user_reports_moved_location_without_claiming_outcome(monkeypatch):
    db = AsyncMongoMockClient().v143_changed
    user = await fixture(monkeypatch, db)
    response = await update_situation_feedback(
        SID,
        SituationFeedback(
            action="changed", expected_revision=1,
            description="Ho spostato l'attività in un luogo coperto.",
        ),
        user=user,
    )
    assert response["ok"] is True
    saved = await SituationRepository(db).get(OWNER, SID)
    assert saved.status == "changed", "changing a location is not completion"
    assert saved.revision == 2
    assert saved.current_state_summary == "Ho spostato l'attività in un luogo coperto."
    assert saved.facts == ["Ho spostato l'attività in un luogo coperto."]
    assert saved.history[-1].source == "user_conversation"
    assert saved.resolved_at is None


@pytest.mark.asyncio
async def test_completion_and_stop_are_distinct_and_persistent(monkeypatch):
    db = AsyncMongoMockClient().v143_closed
    user = await fixture(monkeypatch, db)
    complete = await update_situation_feedback(
        SID, SituationFeedback(action="resolved", expected_revision=1), user=user,
    )
    assert complete["ok"]
    saved = await SituationRepository(db).get(OWNER, SID)
    assert saved.status == "resolved"
    assert saved.resolved_at is not None

    # Another Situation can be stopped without saying the physical process
    # finished; this is just the person's choice to no longer monitor it.
    await SituationRepository(db).insert(SituationState(
        id="sit_other", user_id=OWNER,
        summary="Attività che non voglio più monitorare.",
    ))
    stopped = await update_situation_feedback(
        "sit_other",
        SituationFeedback(action="stop_monitoring", expected_revision=1),
        user=user,
    )
    assert stopped["ok"]
    assert (await SituationRepository(db).get(OWNER, "sit_other")).status == "cancelled"


@pytest.mark.asyncio
async def test_foreign_owner_and_stale_revision_fail_closed(monkeypatch):
    db = AsyncMongoMockClient().v143_isolation
    await fixture(monkeypatch, db)
    with pytest.raises(HTTPException) as foreign:
        await update_situation_feedback(
            SID, SituationFeedback(action="resolved", expected_revision=1),
            user={"user_id": "other-person"},
        )
    assert foreign.value.status_code == 404

    with pytest.raises(HTTPException) as old:
        await update_situation_feedback(
            SID, SituationFeedback(action="changed", expected_revision=4,
                                   description="Una modifica"),
            user={"user_id": OWNER},
        )
    assert old.value.status_code == 409
    assert (await SituationRepository(db).get(OWNER, SID)).status == "active"


@pytest.mark.asyncio
async def test_generic_short_reply_does_not_change_real_world_state(monkeypatch):
    db = AsyncMongoMockClient().v143_empty_reply
    await fixture(monkeypatch, db)
    with pytest.raises(HTTPException) as short:
        await update_situation_feedback(
            SID, SituationFeedback(
                action="changed", expected_revision=1, description="sì",
            ),
            user={"user_id": OWNER},
        )
    assert short.value.status_code == 422
    assert (await SituationRepository(db).get(OWNER, SID)).revision == 1
