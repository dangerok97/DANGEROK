"""Local documents workflow tests — auth, isolation, validation (no Emergent)."""
from __future__ import annotations

import os
import uuid

import httpx
import pytest

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ora_local_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("EMERGENT_GOOGLE_AUTH", "0")

LIVE = os.environ.get("ORA_LIVE_URL", "http://127.0.0.1:8000").rstrip("/")
BASE = f"{LIVE}/api"


def _live_ok() -> bool:
    try:
        r = httpx.get(f"{BASE}/health", timeout=2.0)
        return r.status_code == 200 and bool(r.json().get("database", {}).get("ok"))
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _live_ok(), reason="local uvicorn+Mongo not running")


def _register(client: httpx.Client, prefix: str) -> tuple[str, dict]:
    email = f"{prefix}.{uuid.uuid4().hex[:10]}@ora.app"
    password = "DocTest123!"
    r = client.post(
        f"{BASE}/auth/register",
        json={"email": email, "password": password, "name": prefix},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_unauthenticated_upload_rejected():
    with httpx.Client(timeout=20.0) as c:
        files = {"file": ("secret.txt", b"nope", "text/plain")}
        r = c.post(f"{BASE}/documents/upload", files=files)
        assert r.status_code in (401, 403)


def test_empty_list_valid():
    with httpx.Client(timeout=20.0) as c:
        token, _ = _register(c, "docempty")
        r = c.get(f"{BASE}/documents", headers=_auth(token), params={"archived": "false"})
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert body["items"] == []


def test_upload_list_detail_roundtrip():
    content = b"ORA documents local smoke file\nline 2\n"
    with httpx.Client(timeout=30.0) as c:
        token, user = _register(c, "docup")
        files = {"file": ("ora_smoke.txt", content, "text/plain")}
        data = {"notes": "test note", "tags": "smoke,local"}
        up = c.post(
            f"{BASE}/documents/upload",
            headers=_auth(token),
            files=files,
            data=data,
        )
        assert up.status_code == 200, up.text
        payload = up.json()
        assert payload.get("duplicate") is False
        doc = payload["document"]
        assert doc["user_id"] == user["user_id"]
        assert doc["filename"] == "ora_smoke.txt"
        assert doc["mime_type"] == "text/plain"
        assert doc["size"] == len(content)
        assert doc.get("created_at")
        assert doc.get("archived") is False
        doc_id = doc["id"]

        lst = c.get(
            f"{BASE}/documents",
            headers=_auth(token),
            params={"archived": "false"},
        )
        assert lst.status_code == 200
        ids = [d["id"] for d in lst.json()["items"]]
        assert doc_id in ids

        detail = c.get(f"{BASE}/documents/{doc_id}", headers=_auth(token))
        assert detail.status_code == 200
        d = detail.json()
        assert d["filename"] == "ora_smoke.txt"
        assert d["size"] == len(content)
        assert d["mime_type"] == "text/plain"


def test_user_isolation():
    content = b"private-for-user-a"
    with httpx.Client(timeout=30.0) as c:
        token_a, _ = _register(c, "doca")
        token_b, _ = _register(c, "docb")
        up = c.post(
            f"{BASE}/documents/upload",
            headers=_auth(token_a),
            files={"file": ("private_a.txt", content, "text/plain")},
        )
        assert up.status_code == 200, up.text
        doc_id = up.json()["document"]["id"]

        forbidden = c.get(f"{BASE}/documents/{doc_id}", headers=_auth(token_b))
        assert forbidden.status_code == 404

        list_b = c.get(
            f"{BASE}/documents",
            headers=_auth(token_b),
            params={"archived": "false"},
        )
        assert list_b.status_code == 200
        assert all(i["id"] != doc_id for i in list_b.json()["items"])


def test_invalid_mime_rejected():
    with httpx.Client(timeout=20.0) as c:
        token, _ = _register(c, "docmime")
        r = c.post(
            f"{BASE}/documents/upload",
            headers=_auth(token),
            files={"file": ("evil.exe", b"MZ\x00", "application/x-msdownload")},
        )
        assert r.status_code == 400
        detail = r.json().get("detail")
        assert detail is not None


def test_missing_document_404():
    with httpx.Client(timeout=20.0) as c:
        token, _ = _register(c, "doc404")
        r = c.get(f"{BASE}/documents/doc_doesnotexist99", headers=_auth(token))
        assert r.status_code == 404
