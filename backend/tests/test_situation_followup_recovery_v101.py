"""V101 — unattended temporary Situations recover without another user message.

These tests exercise only the deterministic safety net and review dispatch.
They do not claim live AI judgement, provider accuracy, or notification receipt.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from ambient.eligibility import EligibilityService
from ambient.models import AmbientWake
from ambient.service import AmbientService
from situations.models import SituationState
from situations.repository import SituationRepository


OWNER = "v101-owner"
SID = "sit_v101_unattended"


async def make_db():
    db = AsyncMongoMockClient().test
    await db.ambient_wakes.create_index("identity", unique=True)
    await db.agent_goals.create_index("id", unique=True)
    return db


async def insert_situation(db, *, attention=True):
    state = SituationState(
        id=SID,
        user_id=OWNER,
        summary="Situazione temporanea da seguire.",
        attention_intent="Rivalutare le condizioni al momento utile." if attention else None,
        next_check_summary="Ricontrollare più tardi." if attention else None,
    )
    await SituationRepository(db).insert(state)
    return state


@pytest.mark.asyncio
async def test_active_attention_situation_without_goal_is_recovery_reason():
    db = await make_db()
    await insert_situation(db)
    service = EligibilityService(db)

    reasons = await service.reasons_to_look_again(OWNER)
    assert "situation_unattended" in reasons
    assert OWNER in await service._candidates(datetime.now(timezone.utc), 20)


@pytest.mark.asyncio
async def test_open_goal_for_same_situation_prevents_recovery_duplicate():
    db = await make_db()
    await insert_situation(db)
    await db.agent_goals.insert_one({
        "id": "goal-existing",
        "owner_id": OWNER,
        "status": "waiting",
        "source_kind": "situation_followup",
        "source_refs": [f"situation:{SID}"],
    })

    reasons = await EligibilityService(db).reasons_to_look_again(OWNER)
    assert "situation_unattended" not in reasons


@pytest.mark.asyncio
async def test_plain_active_situation_without_attention_is_not_auto_recovered():
    db = await make_db()
    await insert_situation(db, attention=False)

    reasons = await EligibilityService(db).reasons_to_look_again(OWNER)
    assert "situation_unattended" not in reasons


@pytest.mark.asyncio
async def test_recovery_wake_forces_review_even_when_snapshot_would_be_unchanged(monkeypatch):
    db = await make_db()
    review = AsyncMock(return_value=SimpleNamespace(
        ran=False, retry_after_seconds=None, unavailable=False, scan=None
    ))

    from opportunities.discovery import OpportunityDiscovery
    monkeypatch.setattr(OpportunityDiscovery, "review", review)
    monkeypatch.setattr(OpportunityDiscovery, "__init__", lambda self, _db: setattr(self, "changes", SimpleNamespace(
        pending=AsyncMock(return_value=[])
    )) or setattr(self, "db", _db))

    wake = AmbientWake(
        owner_id=OWNER,
        reason="ambient_review",
        scheduled_for=datetime.now(timezone.utc).isoformat(),
        source_ref="situation_unattended",
    )
    out = await AmbientService(db).review_life(wake)

    assert out.handled is True
    assert review.await_count == 1
    assert review.await_args.kwargs["scheduled"] is True
    assert review.await_args.kwargs["force"] is True


@pytest.mark.asyncio
async def test_unrelated_ambient_review_does_not_force_model_review(monkeypatch):
    db = await make_db()
    review = AsyncMock(return_value=SimpleNamespace(
        ran=False, retry_after_seconds=None, unavailable=False, scan=None
    ))

    from opportunities.discovery import OpportunityDiscovery
    monkeypatch.setattr(OpportunityDiscovery, "review", review)
    monkeypatch.setattr(OpportunityDiscovery, "__init__", lambda self, _db: setattr(self, "changes", SimpleNamespace(
        pending=AsyncMock(return_value=[])
    )) or setattr(self, "db", _db))

    wake = AmbientWake(
        owner_id=OWNER,
        reason="ambient_review",
        scheduled_for=datetime.now(timezone.utc).isoformat(),
        source_ref="delivery_pending",
    )
    await AmbientService(db).review_life(wake)

    assert review.await_args.kwargs["force"] is False
