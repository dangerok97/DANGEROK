"""ORA backend end-to-end tests."""
import os
import uuid
import time
import requests
import pytest

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_PUBLIC_BACKEND_URL") else "https://ora-decision-engine.preview.emergentagent.com"
API = f"{BASE_URL}/api"

# Unique test user per run
UNIQ = uuid.uuid4().hex[:8]
TEST_EMAIL = f"TEST_ora_{UNIQ}@example.com"
TEST_PASS = "TestPass!2026"
TEST_NAME = "TestOra"

STATE = {}


def _auth_headers(token=None):
    tok = token or STATE.get("token")
    return {"Authorization": f"Bearer {tok}"}


# 1) Root
def test_01_root_ok():
    r = requests.get(f"{API}/", timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("app") == "ORA"
    assert j.get("status") == "ok"


# 2) Register creates user + JWT + seeds 5
def test_02_register_creates_user_and_seeds():
    r = requests.post(f"{API}/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASS, "name": TEST_NAME}, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "token" in j and j["token"]
    assert j["user"]["email"] == TEST_EMAIL
    assert j["user"]["provider"] == "email"
    STATE["token"] = j["token"]
    STATE["user_id"] = j["user"]["user_id"]
    # verify 5 priorities
    p = requests.get(f"{API}/priorities", headers=_auth_headers(), timeout=15)
    assert p.status_code == 200
    items = p.json()["items"]
    assert len(items) == 5, f"expected 5 priorities, got {len(items)}"
    scores = [i["score"] for i in items]
    assert scores == sorted(scores, reverse=True), f"not sorted desc: {scores}"
    for it in items:
        assert it["status"] == "open"
        assert "_id" not in it


# 3) Register same email -> 409
def test_03_register_duplicate_409():
    r = requests.post(f"{API}/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASS, "name": TEST_NAME}, timeout=15)
    assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text}"


# 4) Login valid + wrong password
def test_04_login_valid_and_wrong():
    r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("token")

    r2 = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": "WRONG_PASS"}, timeout=15)
    assert r2.status_code == 401, f"expected 401, got {r2.status_code}"


# 5) /auth/me
def test_05_me_with_and_without_token():
    r = requests.get(f"{API}/auth/me", headers=_auth_headers(), timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("user_id", "email", "provider"):
        assert k in j
    assert j["email"] == TEST_EMAIL

    r2 = requests.get(f"{API}/auth/me", timeout=15)
    assert r2.status_code == 401


# 6) /priorities returns 5 sorted open (freshly registered) - already covered above, verify again
def test_06_priorities_shape():
    r = requests.get(f"{API}/priorities", headers=_auth_headers(), timeout=15)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 5
    assert all(i["status"] == "open" for i in items)
    assert all("_id" not in i for i in items)
    scores = [i["score"] for i in items]
    assert scores == sorted(scores, reverse=True)
    STATE["items"] = items


# 7) POST /tasks then GET /tasks; priorities capped at 5
def test_07_create_task():
    payload = {"title": "TEST_task extra", "context": "extra ctx", "urgency": 4, "importance": 4}
    r = requests.post(f"{API}/tasks", headers=_auth_headers(), json=payload, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "id" in j and "score" in j and "_id" not in j
    STATE["extra_task_id"] = j["id"]

    lst = requests.get(f"{API}/tasks", headers=_auth_headers(), timeout=15).json()["items"]
    assert any(t["id"] == j["id"] for t in lst)

    pri = requests.get(f"{API}/priorities", headers=_auth_headers(), timeout=15).json()["items"]
    assert len(pri) <= 5


# 8) Resolve task -> AI solution, italian, non-empty
def test_08_resolve_task_ai():
    # pick top priority
    items = requests.get(f"{API}/priorities", headers=_auth_headers(), timeout=15).json()["items"]
    tid = items[0]["id"]
    STATE["resolve_tid"] = tid
    r = requests.post(f"{API}/tasks/{tid}/resolve", headers=_auth_headers(), timeout=60)
    assert r.status_code == 200, f"AI resolve failed {r.status_code}: {r.text[:400]}"
    j = r.json()
    assert j.get("task_id") == tid
    sol = j.get("solution", "")
    assert isinstance(sol, str) and len(sol) > 10, f"solution too short: {sol!r}"


# 9) Complete task removes from priorities
def test_09_complete_removes_from_priorities():
    tid = STATE["resolve_tid"]
    r = requests.post(f"{API}/tasks/{tid}/complete", headers=_auth_headers(), timeout=15)
    assert r.status_code == 200, r.text
    pri = requests.get(f"{API}/priorities", headers=_auth_headers(), timeout=15).json()["items"]
    assert all(p["id"] != tid for p in pri)


# 10) Dismiss removes from priorities
def test_10_dismiss_removes_from_priorities():
    pri = requests.get(f"{API}/priorities", headers=_auth_headers(), timeout=15).json()["items"]
    assert len(pri) >= 1
    tid = pri[0]["id"]
    r = requests.post(f"{API}/tasks/{tid}/dismiss", headers=_auth_headers(), timeout=15)
    assert r.status_code == 200
    pri2 = requests.get(f"{API}/priorities", headers=_auth_headers(), timeout=15).json()["items"]
    assert all(p["id"] != tid for p in pri2)


# 11) Memory add + list + ask referencing content
def test_11_memory_crud_and_ask():
    content = "Ho comprato il televisore Samsung da MediaWorld a Milano il 12/03/2025. Garanzia 2 anni."
    r = requests.post(f"{API}/memory", headers=_auth_headers(), json={"content": content}, timeout=15)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["content"] == content and "_id" not in m

    lst = requests.get(f"{API}/memory", headers=_auth_headers(), timeout=15).json()["items"]
    assert any(x["content"] == content for x in lst)

    ask = requests.post(f"{API}/memory/ask", headers=_auth_headers(), json={"question": "Dove ho comprato il televisore?"}, timeout=60)
    assert ask.status_code == 200, ask.text
    j = ask.json()
    assert "answer" in j and "sources" in j
    ans = j["answer"].lower()
    # Answer should reference the stored content
    assert "mediaworld" in ans or "milano" in ans, f"answer doesn't reference stored content: {j['answer']!r}"


# 12) Invalid JWT -> 401
def test_12_invalid_jwt_returns_401():
    bad_headers = {"Authorization": "Bearer this.is.invalid.jwt"}
    r = requests.get(f"{API}/priorities", headers=bad_headers, timeout=15)
    assert r.status_code == 401
    r2 = requests.get(f"{API}/auth/me", headers=bad_headers, timeout=15)
    assert r2.status_code == 401
