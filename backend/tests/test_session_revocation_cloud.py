import pytest
from unittest.mock import AsyncMock, MagicMock
from session_revocation import revoke, is_revoked, token_digest, ensure_indexes

@pytest.mark.asyncio
async def test_revocation_persists_only_hash_and_expiry():
    db = MagicMock()
    db.revoked_sessions.update_one = AsyncMock()
    await revoke(db, "synthetic-bearer", 1900000000)
    query, update = db.revoked_sessions.update_one.call_args.args
    assert query == {"_id": token_digest("synthetic-bearer")}
    assert "synthetic-bearer" not in str((query, update))
    assert update["$set"]["expires_at"].timestamp() == 1900000000

@pytest.mark.asyncio
async def test_revoked_and_unrevoked_tokens():
    db = MagicMock()
    db.revoked_sessions.find_one = AsyncMock(side_effect=[{"_id": "hash"}, None])
    assert await is_revoked(db, "first")
    assert not await is_revoked(db, "second")

@pytest.mark.asyncio
async def test_expired_revocations_are_cleaned_up():
    db = MagicMock()
    db.revoked_sessions.create_index = AsyncMock()
    await ensure_indexes(db)
    db.revoked_sessions.create_index.assert_awaited_once_with("expires_at", expireAfterSeconds=0)

@pytest.mark.asyncio
async def test_auth_rejects_revoked_token_and_accepts_new_login(monkeypatch):
    import deps
    db = MagicMock()
    db.revoked_sessions.find_one = AsyncMock(side_effect=[{"_id": "hash"}, None])
    db.users.find_one = AsyncMock(return_value={"user_id": "fixture"})
    monkeypatch.setattr(deps, "db", db)
    old, new = deps.make_jwt("fixture"), deps.make_jwt("fixture")
    assert old != new
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user("Bearer " + old)
    assert exc.value.status_code == 401
    assert await deps.get_current_user("Bearer " + new) == {"user_id": "fixture"}

@pytest.mark.asyncio
@pytest.mark.parametrize("database_up", [True, False])
async def test_health_http_status_reflects_database(monkeypatch, database_up):
    import ast
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    from fastapi import Response
    source = ast.parse((Path(__file__).parents[1] / "server.py").read_text())
    handler = next(n for n in source.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "health")
    handler.decorator_list = []
    client = SimpleNamespace(admin=SimpleNamespace(command=AsyncMock(
        side_effect=None if database_up else RuntimeError("offline"))))
    monkeypatch.setitem(sys.modules, "llm", SimpleNamespace(llm_status=lambda: {}))
    scope = {"client": client, "Response": Response}
    exec(compile(ast.Module(body=[handler], type_ignores=[]), "health_handler", "exec"), scope)
    response = Response()
    result = await scope["health"](response)
    assert response.status_code == (200 if database_up else 503)
    assert result["database"]["ok"] == database_up
