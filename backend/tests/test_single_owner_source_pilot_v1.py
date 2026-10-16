"""Owner-authenticated one-account canary, fresh signals only.

All identities, mail and LLM calls are synthetic. No production account or
provider is contacted. No wildcard/global enrollment is ever accepted.
"""
import hashlib
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

import deps
from agent.router import router
from deps import get_current_user
from agent.authority import AuthorityService
from connected import core_work
from connected.core_work import enroll_owner, ready_for_owner, SourceCoreWorker
from connected.models import ConnectedSignal, FieldChange
from connected.signals import SignalService
from delivery.source_results import enabled_owners_in

OWNER = "synthetic-ora-pilot-user"
EMAIL = "pilot-user@example.invalid"


@pytest.mark.asyncio
async def test_owner_only_canary_enrollment_never_creates_permissions(monkeypatch):
    db = AsyncMongoMockClient().single_owner_pilot
    monkeypatch.setattr(deps, "db", db)
    monkeypatch.setenv(
        "ORA_SOURCE_SINGLE_PILOT_EMAIL_SHA256",
        hashlib.sha256(EMAIL.encode()).hexdigest(),
    )
    monkeypatch.setenv("ORA_SOURCE_MODEL_CONTRACT", '{"synthetic":"scripted"}')
    monkeypatch.delenv("ORA_SOURCE_CORE_PILOT_OWNERS", raising=False)
    monkeypatch.delenv("ORA_SOURCE_RESULT_DELIVERY_OWNERS", raising=False)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": OWNER, "email": EMAIL,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/agent/autonomy/pilot-enroll")
        assert first.status_code == 403
        assert not await db.source_pilot_enrollments.count_documents({})
        assert not await db.autonomy_grants.count_documents({})

        mode = await client.post("/agent/autonomy/mode", json={"mode": "act_within_grants"})
        assert mode.status_code == 200
        grant = await client.post("/agent/autonomy/grant", json={
            "capability": "calendar.local.write",
            "scope_note": "Solo appuntamenti confermati nel calendario ORA",
        })
        assert grant.status_code == 200
        assert await ready_for_owner(db, OWNER) is False
        enrolled = await client.post("/agent/autonomy/pilot-enroll")
        assert enrolled.status_code == 200
        assert enrolled.json() == {"ok": True, "already_active": False}
        assert await ready_for_owner(db, OWNER) is True
        assert (await client.post("/agent/autonomy/pilot-enroll")).json()["already_active"] is True

        status = (await client.get("/agent/autonomy/pilot-status")).json()
        assert status["source_pilot_enrolled"]
        assert status["source_pilot_ready"]
        assert status["delivery_pilot_enrolled"]
        assert OWNER not in str(status)
        assert await enabled_owners_in(db) == {OWNER}

        # Code never adds a new grant for another account.
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": "synthetic-other", "email": "other@example.invalid",
        }
        no = await client.post("/agent/autonomy/pilot-enroll")
        assert no.status_code == 403
        assert await db.source_pilot_enrollments.count_documents({}) == 1

        # Removing the rollout value makes the pilot inaccessible immediately.
        monkeypatch.delenv("ORA_SOURCE_SINGLE_PILOT_EMAIL_SHA256")
        assert await ready_for_owner(db, OWNER) is False
        assert await enabled_owners_in(db) == set()


@pytest.mark.asyncio
async def test_canary_ignores_old_signals_and_respects_grant_revocation(monkeypatch):
    from connectors.gmail.scopes import CONNECTOR_ID
    db = AsyncMongoMockClient().canary_fresh_signals
    monkeypatch.setenv(
        "ORA_SOURCE_SINGLE_PILOT_EMAIL_SHA256",
        hashlib.sha256(EMAIL.encode()).hexdigest(),
    )
    monkeypatch.delenv("ORA_SOURCE_CORE_PILOT_OWNERS", raising=False)
    monkeypatch.delenv("ORA_SOURCE_RESULT_DELIVERY_OWNERS", raising=False)
    await db.users.insert_one({"user_id": OWNER, "email": EMAIL})
    await db.connector_instances.insert_one({
        "id": "synthetic-mail", "user_id": OWNER,
        "connector_id": CONNECTOR_ID, "status": "connected", "metadata": {},
    })
    signals = SignalService(db)
    old, _ = await signals.record(ConnectedSignal(
        owner_id=OWNER, source_id="synthetic-mail", source_type="email",
        signal_type="email.message.added", source_object_ref="old-email",
        payload_summary="Old email before enrollment",
        changed_fields=[FieldChange(field="body", content_withheld=True)],
    ))
    auth = AuthorityService(db)
    await auth.set_mode(OWNER, "act_within_grants")
    grant = await auth.grant(OWNER, "calendar.local.write",
                             effect_scope=["create"], by="user")
    result = await enroll_owner(db, OWNER, EMAIL)
    assert result["ok"]
    assert await ready_for_owner(db, OWNER)

    new, _ = await signals.record(ConnectedSignal(
        owner_id=OWNER, source_id="synthetic-mail", source_type="email",
        signal_type="email.message.added", source_object_ref="new-email",
        payload_summary="New event from an external sender",
        changed_fields=[FieldChange(field="body", content_withheld=True)],
    ))
    worker = SourceCoreWorker(db)
    run = AsyncMock(return_value={
        "state": "reviewed_no_effect",
        "home_visible": False,
        "notifications_sent": False,
    })
    monkeypatch.setattr(worker, "process_one", run)
    out = await worker.process_pending(OWNER, limit=4)
    assert out["looked_at"] == 1
    run.assert_awaited_once_with(OWNER, new.id)
    assert await db.connected_signals.find_one({"id": old.id, "status": "pending"})

    await auth.revoke(OWNER, "calendar.local.write",
                      grant_id=grant["grant"]["id"])
    assert not await ready_for_owner(db, OWNER)
    assert OWNER not in await enabled_owners_in(db)
