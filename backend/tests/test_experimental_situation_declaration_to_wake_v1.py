"""Experimental acceptance: one recovered user Situation becomes a real wake.

Exercise the *joined* path, not only each isolated unit:
failed model declaration -> validated CREATE -> owned canonical Situation
-> initial Agent review wake -> model-chosen persistent next check.
This is NOT weather evidence or a prediction that physical items are dry.
All owners, conditions and checkpoints are synthetic. No messages or push.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from ambient.repository import AmbientRepository
from conversation_engine.ai_core.declaration_recovery import recover_incomplete_create
from opportunities.discovery import OpportunityDiscovery
from situations.followup import (
    INITIAL_KIND, KIND, arrange_followup, goal_id_for, read_followup,
)
from situations.models import SituationUpdate
from situations.service import SituationService

OWNER = "synthetic-owner-recovered-situation"
OTHER = "synthetic-owner-not-allowed"
ERRORS = [
    "situation_create_missing_source_refs",
    "situation_create_missing_linked_object_refs",
]


@pytest.mark.asyncio
async def test_recovered_situation_continues_to_persisted_checkpoint(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    # Other proactive signals are independent and cannot establish this wake.
    monkeypatch.setattr(
        OpportunityDiscovery, "note",
        AsyncMock(return_value={"outcome": "accepted"}),
    )
    db = AsyncMongoMockClient().exp_situation_declaration_to_wake
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index(
        "identity", unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "claimed"]}},
    )
    declaration = {
        "response_mode": "tool",
        "situation_update": {
            "operation": "create",
            "source": "user_conversation",
            "summary": "TEST: bucato immaginario appeso fuori",
            "location_label": "Tarquinia",
            "desired_outcome": "Sapere se conviene raccogliere il bucato di prova",
            "attention_intent": "Controllare nuove evidenze e comunicare il momento utile",
        },
        "tool_call": {
            "capability": "schedule_situation_check",
            "arguments": {"check_at": "no verified time"},
        },
    }
    original = deepcopy(declaration)
    recovered = recover_incomplete_create(declaration, ERRORS)
    assert recovered is not None
    assert recovered["tool_call"] is None, "not allowed to manufacture a wake"
    assert declaration == original, "never rewrite the original AI evidence"
    assert "non risulta ancora programmato" in recovered["message_to_user"]

    saved = await SituationService(db).apply(
        user_id=OWNER,
        session_id="synthetic-conversation",
        reasoning_epoch="original-model-turn",
        update=SituationUpdate.model_validate(recovered["situation_update"]),
    )
    assert saved["status"] == "success", saved
    sid = saved["situation"]["id"]
    goal_id = goal_id_for(OWNER, sid)
    goal = await db.agent_goals.find_one(
        {"id": goal_id, "owner_id": OWNER}, {"_id": 0},
    )
    assert goal is not None and goal["source_kind"] == INITIAL_KIND

    review = await read_followup(db, OWNER, sid)
    assert review["status"] == "review_pending", review
    assert review["next_check_at"] is None
    # A genuine initial assessment wake must exist; it is NOT a check whose
    # result ORA may present as a verified real-world observation.
    initial = await db.ambient_wakes.find_one(
        {"owner_id": OWNER, "source_ref": f"goal:{goal_id}", "status": "pending"},
        {"_id": 0},
    )
    assert initial is not None and initial["reason"] == "opportunity_revisit"

    due = (datetime.now(timezone.utc) + timedelta(minutes=37)).isoformat()
    kwargs = dict(
        situation_id=sid, expected_revision=saved["situation"]["revision"],
        check_at=due, purpose="Rileggere fonti verificabili aggiornate",
        notify_when="Se compare un rischio anticipato che cambia la decisione",
        completion_when="Quando i dati consentono un consiglio utile",
    )
    cross_owner = await arrange_followup(db, OTHER, **kwargs)
    assert cross_owner["ok"] is False

    scheduled = await arrange_followup(db, OWNER, **kwargs)
    assert scheduled["ok"] is True and scheduled["status"] == "scheduled", scheduled
    assert scheduled["next_check_at"] == due
    # After process restart, the canonical readback still proves the wake.
    fresh_service = SituationService(db)
    assert await fresh_service.repo.get(OWNER, sid) is not None
    readback = await read_followup(db, OWNER, sid)
    assert readback["status"] == "scheduled"
    assert readback["next_check_at"] == due
    stored = await db.agent_goals.find_one(
        {"id": goal_id, "owner_id": OWNER}, {"_id": 0},
    )
    assert stored["source_kind"] == KIND
    wakes = await db.ambient_wakes.find(
        {"owner_id": OWNER, "source_ref": f"goal:{goal_id}",
         "status": {"$in": ["pending", "claimed"]}}, {"_id": 0},
    ).to_list(10)
    assert len(wakes) == 1 and wakes[0]["scheduled_for"] == due
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert await db.ambient_wakes.count_documents({"owner_id": OTHER}) == 0

    # Repeated arrival/reasoning never silently shifts or duplicates the job.
    replay = await arrange_followup(
        db, OWNER, **{**kwargs, "check_at":
                     (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()},
    )
    assert replay["ok"] and replay.get("reused") is True
    assert (await read_followup(db, OWNER, sid))["next_check_at"] == due
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal_id}",
        "status": {"$in": ["pending", "claimed"]},
    }) == 1
    assert (await db.situations.find_one(
        {"user_id": OWNER, "id": sid}
    ))["status"] == "active", "scheduling does not prove physical completion"


@pytest.mark.asyncio
async def test_recovered_note_does_not_claim_scheduled_when_worker_disabled(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "0")
    db = AsyncMongoMockClient().exp_disabled_situation
    recovered = recover_incomplete_create({
        "response_mode": "tool",
        "situation_update": {
            "operation": "create", "source": "user_conversation",
            "summary": "TEST: macchina lasciata in carica",
            "location_label": "",
            "desired_outcome": "Sapere se devo scollegarla",
            "attention_intent": "Verificare il momento utile",
        },
        "tool_call": {
            "capability": "schedule_situation_check", "arguments": {}
        },
    }, ERRORS)
    assert recovered is not None
    out = await SituationService(db).apply(
        user_id=OWNER, session_id="synthetic-chat",
        reasoning_epoch="disabled-runtime-model-turn",
        update=SituationUpdate.model_validate(recovered["situation_update"]),
    )
    assert out["status"] == "success"
    state = await read_followup(db, OWNER, out["situation"]["id"])
    assert state["status"] not in ("scheduled", "due", "running")
    assert await db.ambient_wakes.count_documents({}) == 0
