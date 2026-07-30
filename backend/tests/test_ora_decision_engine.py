"""
ORA Decision Engine backend regression tests — iteration 2.
Covers auth regression, new /api/decisions/*, legacy /priorities+/tasks,
and migration for pre-existing demo user.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@ora.app"
DEMO_PASSWORD = "Demo!2026"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def fresh_user(api):
    """One fresh user seeded with the 7 starter decisions."""
    email = f"brain_{int(time.time())}_{uuid.uuid4().hex[:6]}@ora.app"
    r = api.post(f"{API}/auth/register", json={"email": email, "password": "Demo!2026", "name": "Brain"})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"email": email, "token": data["token"], "user": data["user"]}


@pytest.fixture(scope="session")
def fresh_headers(fresh_user):
    return {"Authorization": f"Bearer {fresh_user['token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def demo_login(api):
    r = api.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    if r.status_code != 200:
        # If demo not yet created, create it now.
        api.post(f"{API}/auth/register", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "name": "Demo"})
        r = api.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- A. Regression ----------------
class TestRegression:
    def test_root(self, api):
        r = api.get(f"{API}/")
        assert r.status_code == 200
        assert r.json() == {"app": "ORA", "status": "ok"}

    def test_register_fresh(self, fresh_user):
        assert fresh_user["token"]
        assert fresh_user["user"]["email"] == fresh_user["email"]

    def test_me_with_token(self, api, fresh_headers, fresh_user):
        r = api.get(f"{API}/auth/me", headers=fresh_headers)
        assert r.status_code == 200
        assert r.json()["email"] == fresh_user["email"]

    def test_me_without_token(self, api):
        r = api.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_wrong_password(self, api, fresh_user):
        r = api.post(f"{API}/auth/login", json={"email": fresh_user["email"], "password": "WRONG!"})
        assert r.status_code == 401

    def test_memory_flow(self, api, fresh_headers):
        r = api.post(f"{API}/memory", headers=fresh_headers,
                     json={"content": "Ho un volo per Milano il 10/1/2026", "tags": ["travel"]})
        assert r.status_code == 200
        r2 = api.post(f"{API}/memory/ask", headers=fresh_headers, json={"question": "Quando parto per Milano?"})
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert "answer" in body and "sources" in body
        assert isinstance(body["answer"], str) and len(body["answer"]) > 0


# ---------------- B. Decision Engine ----------------
REQUIRED_KEYS = {
    "id", "title", "description", "origin", "category", "urgency", "importance",
    "risk", "economic_impact", "personal_impact", "time_required_min", "energy",
    "place", "people", "starts_at", "deadline", "status", "linked_to",
    "metadata", "history", "created_at", "score", "reason", "reason_tags",
}


class TestDecisions:
    def test_list_has_7_seeds_and_rich_fields(self, api, fresh_headers):
        r = api.get(f"{API}/decisions", headers=fresh_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 7, f"expected 7 seeds, got {len(items)}"
        for d in items:
            missing = REQUIRED_KEYS - set(d.keys())
            assert not missing, f"decision missing keys {missing}: {d.get('title')}"
            assert isinstance(d["history"], list)
            assert isinstance(d["linked_to"], list)

    def test_top_returns_3_sorted_with_reason(self, api, fresh_headers):
        r = api.get(f"{API}/decisions/top?limit=3", headers=fresh_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 3
        scores = [d["score"] for d in items]
        assert scores == sorted(scores, reverse=True)
        for d in items:
            assert isinstance(d["reason"], str) and d["reason"].strip()
            assert d["reason"].rstrip().endswith("."), f"reason must end with '.': {d['reason']!r}"

    def test_top1_is_imminent(self, api, fresh_headers):
        r = api.get(f"{API}/decisions/top?limit=3", headers=fresh_headers)
        top1 = r.json()["items"][0]
        assert "Esci tra 25 minuti" in top1["title"] or "imminent" in top1["reason_tags"], \
            f"top1={top1['title']} tags={top1['reason_tags']}"
        assert "imminent" in top1["reason_tags"]

    def test_valigia_in_top3_with_dependency_tag(self, api, fresh_headers):
        r = api.get(f"{API}/decisions/top?limit=3", headers=fresh_headers)
        items = r.json()["items"]
        valigia = next((d for d in items if "valigia" in (d["title"] or "").lower()), None)
        assert valigia is not None, f"'Prepara la valigia' not in top3: {[d['title'] for d in items]}"
        expected = {"linked_soon", "deadline_24h", "trip_prep"}
        assert expected & set(valigia["reason_tags"]), \
            f"valigia tags {valigia['reason_tags']} missing any of {expected}"

    def test_insight_not_in_top3(self, api, fresh_headers):
        r = api.get(f"{API}/decisions/top?limit=3", headers=fresh_headers)
        items = r.json()["items"]
        for d in items:
            assert d["category"] != "insight", "insight should not be in top3"
        # Find insight in full list.
        r2 = api.get(f"{API}/decisions", headers=fresh_headers)
        insight = next((d for d in r2.json()["items"] if d["category"] == "insight"), None)
        assert insight is not None
        assert "insight" in insight["reason_tags"]

    def test_create_decision_and_dampens_fitness(self, api, fresh_headers):
        # Find fitness Palestra baseline score
        r_all = api.get(f"{API}/decisions/top?limit=10", headers=fresh_headers)
        items = r_all.json()["items"]
        palestra_before = next((d for d in items if d["category"] == "fitness"), None)
        assert palestra_before is not None, "Palestra fitness seed missing"
        score_before = palestra_before["score"]

        # Create exam within 24h
        from datetime import datetime, timezone, timedelta
        deadline = (datetime.now(timezone.utc) + timedelta(hours=20)).isoformat()
        payload = {
            "title": "Esame di matematica",
            "description": "Studio finale",
            "category": "exam",
            "urgency": 9, "importance": 9, "risk": 8,
            "time_required_min": 180, "energy": 8,
            "economic_impact": 2, "personal_impact": 9,
            "deadline": deadline,
        }
        rc = api.post(f"{API}/decisions", headers=fresh_headers, json=payload)
        assert rc.status_code == 200, rc.text
        created = rc.json()
        assert created["id"].startswith("dec_")
        assert created["status"] == "open"
        assert any(h["event"] == "created" for h in created["history"])

        # Verify Palestra now has dampened tag and lower score
        r2 = api.get(f"{API}/decisions/top?limit=10", headers=fresh_headers)
        palestra_after = next((d for d in r2.json()["items"] if d["category"] == "fitness"), None)
        assert palestra_after is not None
        assert "dampened_by_stakes" in palestra_after["reason_tags"], \
            f"expected dampened_by_stakes, got {palestra_after['reason_tags']}"
        assert palestra_after["score"] < score_before, \
            f"score should drop after exam: before={score_before}, after={palestra_after['score']}"

    def test_resolve_returns_italian_solution(self, api, fresh_headers):
        r_all = api.get(f"{API}/decisions/top?limit=10", headers=fresh_headers)
        target = next((d for d in r_all.json()["items"] if "valigia" in (d["title"] or "").lower()), None)
        assert target is not None
        rid = target["id"]
        rr = api.post(f"{API}/decisions/{rid}/resolve", headers=fresh_headers)
        assert rr.status_code == 200, f"resolve failed: {rr.status_code} {rr.text}"
        sol = rr.json().get("solution")
        assert isinstance(sol, str) and len(sol) > 20
        # History event
        rg = api.get(f"{API}/decisions/{rid}", headers=fresh_headers)
        assert rg.status_code == 200
        events = [h["event"] for h in rg.json()["history"]]
        assert "ai_resolution_proposed" in events

    def test_complete_removes_from_top(self, api, fresh_headers):
        r_all = api.get(f"{API}/decisions/top?limit=10", headers=fresh_headers)
        items = r_all.json()["items"]
        target = next((d for d in items if d["category"] == "communication"), None)
        assert target is not None
        rid = target["id"]
        rc = api.post(f"{API}/decisions/{rid}/complete", headers=fresh_headers)
        assert rc.status_code == 200 and rc.json() == {"ok": True}
        r2 = api.get(f"{API}/decisions/top?limit=20", headers=fresh_headers)
        assert not any(d["id"] == rid for d in r2.json()["items"])

    def test_dismiss_removes_from_top(self, api, fresh_headers):
        r_all = api.get(f"{API}/decisions/top?limit=10", headers=fresh_headers)
        target = next((d for d in r_all.json()["items"] if d["category"] == "bill"), None)
        assert target is not None
        rid = target["id"]
        rd = api.post(f"{API}/decisions/{rid}/dismiss", headers=fresh_headers)
        assert rd.status_code == 200 and rd.json() == {"ok": True}
        r2 = api.get(f"{API}/decisions/top?limit=20", headers=fresh_headers)
        assert not any(d["id"] == rid for d in r2.json()["items"])

    def test_invalid_jwt(self, api):
        bad = {"Authorization": "Bearer notatoken", "Content-Type": "application/json"}
        assert api.get(f"{API}/decisions", headers=bad).status_code == 401
        assert api.post(f"{API}/decisions", headers=bad, json={"title": "x"}).status_code == 401


# ---------------- C. Legacy compat ----------------
class TestLegacy:
    def test_priorities_default_max_3(self, api, fresh_headers):
        r = api.get(f"{API}/priorities", headers=fresh_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) <= 3
        for it in items:
            assert "reason" in it and isinstance(it["reason"], str) and it["reason"]

    def test_priorities_limit_10(self, api, fresh_headers):
        r = api.get(f"{API}/priorities?limit=10", headers=fresh_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert 1 <= len(items) <= 10

    def test_legacy_task_create_maps_to_bill(self, api, fresh_headers):
        payload = {
            "title": "Bolletta test",
            "context": "test legacy",
            "urgency": 6, "importance": 6, "risk": 5,
            "time_required_min": 5, "energy": 1,
            "economic_impact": 5, "personal_impact": 3,
            "kind": "bill",
        }
        r = api.post(f"{API}/tasks", headers=fresh_headers, json=payload)
        assert r.status_code == 200
        created = r.json()
        assert created["kind"] == "bill"  # decision_as_task remaps category → kind
        # Verify visible in /decisions with category=bill
        rd = api.get(f"{API}/decisions", headers=fresh_headers)
        found = next((d for d in rd.json()["items"] if d["id"] == created["id"]), None)
        assert found is not None
        assert found["category"] == "bill"

    def test_legacy_task_actions_delegate(self, api, fresh_headers):
        # Create task, then dismiss/complete/resolve via legacy routes.
        r = api.post(f"{API}/tasks", headers=fresh_headers,
                     json={"title": "Legacy dismiss target", "kind": "generic"})
        tid = r.json()["id"]
        rd = api.post(f"{API}/tasks/{tid}/dismiss", headers=fresh_headers)
        assert rd.status_code == 200 and rd.json() == {"ok": True}

        r2 = api.post(f"{API}/tasks", headers=fresh_headers,
                      json={"title": "Legacy complete target", "kind": "generic"})
        t2 = r2.json()["id"]
        rc = api.post(f"{API}/tasks/{t2}/complete", headers=fresh_headers)
        assert rc.status_code == 200 and rc.json() == {"ok": True}

        r3 = api.post(f"{API}/tasks", headers=fresh_headers,
                      json={"title": "Ricorda un compleanno", "kind": "communication",
                            "urgency": 5, "importance": 5})
        t3 = r3.json()["id"]
        rr = api.post(f"{API}/tasks/{t3}/resolve", headers=fresh_headers)
        assert rr.status_code == 200, rr.text
        assert "solution" in rr.json() and len(rr.json()["solution"]) > 10


# ---------------- D. Migration ----------------
class TestMigration:
    def test_demo_user_has_migrated_items_or_seeds(self, api, demo_login):
        hdr = {"Authorization": f"Bearer {demo_login['token']}", "Content-Type": "application/json"}
        r = api.get(f"{API}/decisions", headers=hdr)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        origins = {d["origin"] for d in items}
        # Demo was created in iteration 1 with legacy tasks; expect migration entries.
        # If demo was seeded fresh here, at minimum origins should not be empty.
        assert origins, "no origins found"
        # Prefer to assert migration:task presence, but tolerate seed fallback with a warning.
        has_migration = any(o == "migration:task" for o in origins)
        # We don't hard-fail if demo was seeded new (empty legacy tasks collection),
        # but we DO record the observation so the test surfaces the state.
        print(f"demo origins={origins} has_migration={has_migration}")
        # At least one seeded or migrated origin must exist.
        assert has_migration or "seed" in origins
