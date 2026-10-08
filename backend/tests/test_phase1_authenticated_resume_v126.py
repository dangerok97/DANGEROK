"""HTTP authentication and persisted retry together, on synthetic accounts.

Uses the real FastAPI router, JWT verification/revocation, orchestrator,
cognitive loop and session repository. Only model decisions and storage are
synthetic. No application lifespan or external account is started.
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient


@pytest.mark.asyncio
async def test_authenticated_lost_response_retry_and_token_revocation(monkeypatch):
    import deps
    import conversation_engine.router as conversation_router
    import conversation_engine.ai_core.orchestrator as core
    from conversation_engine.models import ConversationSession
    from conversation_engine.repository import ConversationRepository
    from session_revocation import revoke

    db = AsyncMongoMockClient().phase1_http_accounts
    monkeypatch.setattr(deps, "db", db)
    monkeypatch.setattr(deps, "JWT_SECRET", "synthetic-http-eval-signing-key-only")
    monkeypatch.setattr(conversation_router, "db", db)
    for owner in ("synthetic-http-owner", "synthetic-http-other"):
        await db.users.insert_one({"user_id": owner, "settings": {"location_mode": "off"}})
    session = ConversationSession(
        user_id="synthetic-http-owner", engine_version="ai-core-1.0",
        meta={"ui_mode": "ai_core", "ai_core": {}},
    )
    await ConversationRepository(db).insert(session)
    model_calls = 0

    async def decide(system, payload):
        nonlocal model_calls
        model_calls += 1
        return {
            "response_mode": "answer", "reasoning_status": "enough_information",
            "message_to_user": "La sessione sintetica è stata riletta correttamente.",
            "situation_update": {"operation": "none"},
        }

    original_loop = core.run_cognitive_loop

    async def controlled_loop(**kwargs):
        return await original_loop(**{**kwargs, "decision_fn": decide})

    monkeypatch.setattr(core, "run_cognitive_loop", controlled_loop)
    app = FastAPI()
    app.include_router(conversation_router.router, prefix="/api")
    transport = httpx.ASGITransport(app=app)
    endpoint = f"/api/conversation/ai-core/{session.id}/message"
    body = {"text": "Rileggi questo contesto.", "client_message_id": "http-stable-message"}
    token = deps.make_jwt(session.user_id)
    other_token = deps.make_jwt("synthetic-http-other")

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.post(endpoint, json=body)).status_code == 401
        assert (await client.post(endpoint, json=body, headers={"Authorization": "Bearer malformed"})).status_code == 401
        foreign = await client.post(endpoint, json=body, headers={"Authorization": "Bearer " + other_token})
        assert foreign.status_code == 404
        assert model_calls == 0

        headers = {"Authorization": "Bearer " + token}
        first = await client.post(endpoint, json={**body, "activity_request_id": "attempt_one"}, headers=headers)
        assert first.status_code == 200
        assert first.json()["ok"] and model_calls == 1
        stored = await ConversationRepository(db).get(session.user_id, session.id)

        # Every HTTP route call constructs a new orchestrator and reloads Mongo.
        # A transport retry has a new activity id but the same message id.
        retry = await client.post(endpoint, json={**body, "activity_request_id": "attempt_two"}, headers=headers)
        assert retry.status_code == 200 and retry.json() == first.json()
        assert model_calls == 1
        assert (await ConversationRepository(db).get(session.user_id, session.id)).model_dump() == stored.model_dump()
        assert token not in retry.text and other_token not in retry.text
        assert "request_fingerprint" not in retry.text and "result_receipt" not in retry.text

        changed = await client.post(endpoint, json={**body, "text": "Un lavoro diverso."}, headers=headers)
        assert changed.status_code == 400
        assert changed.json()["detail"] == "client_message_id_conflict"
        assert model_calls == 1

        expiry = int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp())
        await revoke(db, token, expiry)
        assert (await client.post(endpoint, json=body, headers=headers)).status_code == 401
        fresh_token = deps.make_jwt(session.user_id)
        recovered = await client.post(endpoint, json=body, headers={"Authorization": "Bearer " + fresh_token})
        assert recovered.status_code == 200 and recovered.json() == first.json()
        assert model_calls == 1
