"""Export everything (without secrets) and delete everything, for one account only."""
from datetime import datetime, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

import account_lifecycle as al

UID, OTHER = "user_me", "user_other"


async def _seed(db):
    await db.users.insert_many([
        {"user_id": UID, "email": "me@example.com", "password_hash": "x", "name": "Me"},
        {"user_id": OTHER, "email": "other@example.com", "name": "Other"},
    ])
    await db.user_identities.insert_one({"user_id": UID, "provider": "password", "email": "me@example.com"})
    await db.situations.insert_many([{"id": "s1", "user_id": UID, "summary": "Panni"},
                                     {"id": "s2", "user_id": OTHER, "summary": "Altro"}])
    await db.agent_goals.insert_one({"id": "g1", "owner_id": UID, "at": datetime.now(timezone.utc)})
    await db.connector_instances.insert_one({"user_id": UID, "access_token": "SECRET", "refresh_token": "R",
                                             "meta": {"client_secret": "S", "label": "Gmail"}})


@pytest.mark.asyncio
async def test_export_has_my_data_and_no_secrets():
    db = AsyncMongoMockClient().acct_export_v1
    await _seed(db)
    data = await al.export(db, UID)
    cols = data["collections"]
    assert {"users", "situations", "agent_goals", "connector_instances", "user_identities"} <= set(cols)
    assert [s["id"] for s in cols["situations"]] == ["s1"]
    text = str(data)
    assert "SECRET" not in text and "client_secret': 'S'" not in text and "password_hash': 'x'" not in text
    assert cols["connector_instances"][0]["meta"]["label"] == "Gmail"


@pytest.mark.asyncio
async def test_delete_erases_only_me(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path))
    (tmp_path / UID / "ab").mkdir(parents=True)
    (tmp_path / UID / "ab" / "x.bin").write_bytes(b"1")
    (tmp_path / OTHER).mkdir()
    db = AsyncMongoMockClient().acct_delete_v1
    await _seed(db)
    out = await al.delete(db, UID, "me@example.com")
    assert out["ok"] and out["files"] == 1 and out["records"] >= 5
    for name in ("users", "situations", "agent_goals", "connector_instances", "user_identities"):
        assert await db[name].count_documents({"$or": [{"user_id": UID}, {"owner_id": UID}]}) == 0
    assert await db.users.count_documents({"user_id": OTHER}) == 1
    assert await db.situations.count_documents({"user_id": OTHER}) == 1
    assert not (tmp_path / UID).exists() and (tmp_path / OTHER).exists()
    audit = await db.account_deletions.find_one({})
    assert UID not in str(audit) and audit["records"] == out["records"]


def test_routes_exist_and_require_confirmation():
    import inspect
    from routers import auth

    src = inspect.getsource(auth.delete_account)
    assert "ELIMINA" in src and "verify_password" in src
    paths = {r.path for r in auth.router.routes}
    assert {"/auth/account/export", "/auth/account/delete"} <= paths


def test_backup_retention_has_a_floor(monkeypatch):
    pytest.importorskip("boto3")
    from ops.backup_restore import retention_days

    monkeypatch.setenv("BACKUP_RETENTION_DAYS", "2")
    assert retention_days() == 7
    monkeypatch.delenv("BACKUP_RETENTION_DAYS")
    assert retention_days() == 30
