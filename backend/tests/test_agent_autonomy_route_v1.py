"""Regression: static /agent/autonomy must win over dynamic /agent/{goal_id}.

The production failure was POST /agent/autonomy/mode = 200 followed by
GET /agent/autonomy = 404, leaving a saved preference invisible on iPhone.
All requests use an in-memory database and a synthetic authenticated owner.
"""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient
from starlette.routing import Match

import deps
from agent.router import router, autonomy
from deps import get_current_user

OWNER = "synthetic-autonomy-route-owner"


def test_static_settings_route_precedes_dynamic_goal_route():
    scope = {"type": "http", "path": "/agent/autonomy", "method": "GET", "root_path": ""}
    chosen = next((route for route in router.routes
                   if route.matches(scope)[0] == Match.FULL), None)
    assert chosen is not None
    assert chosen.endpoint is autonomy


@pytest.mark.asyncio
async def test_saving_mode_can_be_read_back_and_grant_is_visible(monkeypatch):
    database = AsyncMongoMockClient().autonomy_route_regression
    monkeypatch.setattr(deps, "db", database)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": OWNER}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/agent/autonomy")
        assert first.status_code == 200, first.text
        assert first.json()["chosen_by_user"] is False

        write = await client.post("/agent/autonomy/mode",
                                  json={"mode": "act_within_grants"})
        assert write.status_code == 200, write.text
        assert write.json()["ok"] is True

        read = await client.get("/agent/autonomy")
        assert read.status_code == 200, read.text
        assert read.json()["mode"] == "act_within_grants"
        assert read.json()["chosen_by_user"] is True

        grant = await client.post("/agent/autonomy/grant", json={
            "capability": "calendar.local.write",
            "scope_note": "Aggiungere nuovi impegni personali al calendario ORA.",
        })
        assert grant.status_code == 200, grant.text
        detail = await client.get("/agent/autonomy")
        assert detail.status_code == 200, detail.text
        grants = detail.json()["grants"]
        assert len(grants) == 1
        assert grants[0]["capability"] == "calendar.local.write"
        assert grants[0]["effect_scope"] == ["create"]

        # The mode is merely a ceiling: the explicit permission stays separate.
        revoke = await client.post("/agent/autonomy/revoke", json={
            "capability": "calendar.local.write",
            "grant_id": grants[0]["id"],
        })
        assert revoke.status_code == 200
        after = await client.get("/agent/autonomy")
        assert after.status_code == 200
        assert after.json()["mode"] == "act_within_grants"
        assert after.json()["grants"] == []
