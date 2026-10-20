"""Regression: a model can invent an ID even when a real Situation was saved.

The original ORA acceptance response showed 'sit_f8b2e3c1d4a5' (12 hex
characters), but canonical SituationService ids contain 16 hex characters.
Only confirmed server-side writes may supply IDs/created_at/started_at.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock
import re

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.situation_receipt import verified_situation_receipt
from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.models import ConversationSession
from situations.service import SituationService

OWNER = "synthetic-situation-receipt-owner"
FALSE_ID = "sit_f8b2e3c1d4a5"
OLD_ID = "sit_ba5be5cb2ff847be"


def fixture_receipt(*, operation="create", sid="sit_a3f95d840bc9e1ab"):
    return {
        "status": "success", "operation": operation,
        "previous_situation_id": OLD_ID,
        "situation": {
            "id": sid, "status": "active",
            "summary": "Synthetic new user event",
            "created_at": "2026-10-20T12:16:02+00:00",
            "started_at": "2026-10-20T12:16:02+00:00",
        },
    }


def test_false_model_id_and_dates_never_replace_canonical_write_receipt():
    model = (
        "Ho registrato la nuova Situazione di test con ID " + FALSE_ID + ".\n"
        "- Data creazione (created_at): 2026-10-19T17:00:00+02:00\n"
        "- Data inizio (started_at): 2026-10-19T17:00:00+02:00\n"
        "Ho confermato che la situazione precedente " + OLD_ID + " è distinta."
    )
    answer = verified_situation_receipt(model, fixture_receipt())
    assert FALSE_ID not in answer, answer
    assert "sit_a3f95d840bc9e1ab" in answer
    assert OLD_ID in answer
    assert "2026-10-19T17:00:00" not in answer
    assert "2026-10-20T12:16:02+00:00" in answer
    assert "[ID non verificato]" in answer
    assert answer.count("**Conferma archivio ORA") == 1


def test_missing_write_blocked_instead_of_12char_phantom_id():
    text = f"Ho registrato una nuova Situazione temporanea, ID {FALSE_ID}."
    result = verified_situation_receipt(text, None)
    assert FALSE_ID not in result
    assert "non ho conferma" in result.lower()


def test_normal_update_is_not_cluttered_but_misleading_create_claim_is_corrected():
    done = fixture_receipt(operation="update")
    quiet = "Ho aggiornato la descrizione della situazione, come richiesto."
    assert verified_situation_receipt(quiet, done) == quiet
    claim = f"Ho registrato la nuova Situazione con ID {FALSE_ID}."
    fixed = verified_situation_receipt(claim, done)
    assert FALSE_ID not in fixed
    assert "Nessun nuovo ID creato" in fixed


@pytest.mark.asyncio
async def test_real_ai_core_new_situation_receipt_is_db_owned(monkeypatch):
    db = AsyncMongoMockClient().test_verified_receipt
    monkeypatch.setenv("AMBIENT_RUNTIME", "0")
    monkeypatch.setattr(
        SituationService, "_note_opportunity_change",
        AsyncMock(return_value=None),
    )
    user = ConversationSession(
        user_id=OWNER,
        meta={"ui_mode": "ai_core", "ai_core": {}},
    )
    instant = datetime.now(timezone.utc).isoformat()

    async def decide(_system, _payload):
        return {
            "response_mode": "answer",
            "message_to_user": (
                "Ho registrato la nuova Situazione di test.\n"
                f"ID: {FALSE_ID}\n"
                "Data creazione (created_at): 2026-10-19T17:00:00+02:00\n"
                "La vecchia situazione era " + OLD_ID + "."
            ),
            "situation_update": {
                "operation": "create",
                "source": "user_conversation",
                "summary": "Simulazione nuova attività temporanea",
                "started_at": instant,
                "location_label": "Tarquinia",
                "source_refs": ["user_conversation"],
            },
        }

    turn = await run_cognitive_loop(
        sess=user,
        user_message="Questa è una simulazione. Ho iniziato un nuovo evento adesso. Registralo per prova.",
        db=db,
        decision_fn=decide,
    )
    docs = await db.situations.find({"user_id": OWNER}, {"_id": 0}).to_list(10)
    assert turn.ok, turn
    assert len(docs) == 1, docs
    sid = docs[0]["id"]
    assert re.fullmatch(r"sit_[0-9a-f]{16}", sid), sid
    assert sid in turn.ora_text, turn.ora_text
    assert FALSE_ID not in turn.ora_text, turn.ora_text
    assert docs[0]["created_at"] in turn.ora_text
    assert docs[0]["started_at"] in turn.ora_text
    assert "2026-10-19T17:00:00+02:00" not in turn.ora_text
    assert await db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_invalid_model_id_returns_actual_owner_candidates_without_reassigning_checks(monkeypatch):
    from situations.models import SituationState
    from situations.followup import get_situation_followup

    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    db = AsyncMongoMockClient().test_receipt_recovery
    real_id = "sit_f8b2e3c1d4a5dead"
    await db.situations.insert_one(SituationState(
        id=real_id, user_id=OWNER, summary="Synthetic new independent test",
        location_label="Tarquinia",
    ).model_dump())
    await db.situations.insert_one(SituationState(
        id="sit_0123456789abcdef", user_id="other-owner",
        summary="Other account's private context", location_label="Leesburg",
    ).model_dump())
    obs = await get_situation_followup({
        "situation_id": FALSE_ID,
    }, {"db": db, "user_id": OWNER,
        "user_message": "Qual è lo stato del controllo di questa Situazione?"})
    assert obs.status == "error"
    assert obs.payload["read_failure_code"] == "situation_not_found_or_not_owned"
    candidates = obs.payload["recent_owner_candidates"]
    assert len(candidates) == 1, candidates
    assert candidates[0]["situation_id"] == real_id
    assert "Leesburg" not in str(obs.model_dump())
    assert "other-owner" not in str(obs.model_dump())
    assert obs.payload["last_checked_at"] is None
    assert obs.payload["next_check_at"] is None
    assert "non attribuire automaticamente" in obs.payload["recovery_diagnosis"]
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0
