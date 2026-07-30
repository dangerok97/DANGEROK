"""Iteration 8 — Permissions & Connectors + refactor regression tests.

Covers the review-request areas 1..6. All tests hit the PUBLIC preview URL.

Runs serially (`-n 0` recommended).
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict, List, Optional

import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL", "https://ora-decision-engine.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@ora.app"
DEMO_PASSWORD = "Demo!2026"

TIMEOUT = 30


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _unique_email(prefix: str = "iter8") -> str:
    return f"{prefix}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}@ora.app"


def _register(email: Optional[str] = None) -> Dict[str, Any]:
    email = email or _unique_email()
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": "Passw0rd!2026", "name": "Iter8"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    body = r.json()
    return {"token": body["token"], "user": body["user"], "email": email}


def _login(email: str, password: str) -> Dict[str, Any]:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": password},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    return {"token": body["token"], "user": body["user"]}


def _hdr(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ----------------------------------------------------------------------
# session-wide users
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def user_a() -> Dict[str, Any]:
    return _register(_unique_email("iter8a"))


@pytest.fixture(scope="module")
def user_b() -> Dict[str, Any]:
    return _register(_unique_email("iter8b"))


@pytest.fixture(scope="module")
def demo_user() -> Dict[str, Any]:
    """Login as the demo user (created by seed)."""
    try:
        return _login(DEMO_EMAIL, DEMO_PASSWORD)
    except AssertionError:
        # Try registering if not present.
        r = requests.post(
            f"{API}/auth/register",
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "name": "Demo"},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            body = r.json()
            return {"token": body["token"], "user": body["user"]}
        pytest.skip("Cannot obtain demo user")


# ======================================================================
# 1) REGRESSION — server.py → routers/* refactor
# ======================================================================
class TestRegressionAuth:
    def test_root(self):
        r = requests.get(f"{API}/", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("app") == "ORA"

    def test_register_ok_and_shape(self):
        u = _register(_unique_email("reg"))
        assert "user_id" in u["user"]
        assert u["user"]["email"] == u["email"]
        assert isinstance(u["token"], str) and u["token"]

    def test_login_and_me(self, user_a):
        r = requests.get(f"{API}/auth/me", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["email"] == user_a["email"]

    def test_me_no_token_401(self):
        r = requests.get(f"{API}/auth/me", timeout=TIMEOUT)
        assert r.status_code in (401, 403)

    def test_login_bad_password_401(self, user_a):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": user_a["email"], "password": "WRONG"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 401

    def test_google_session_bad_token(self):
        r = requests.post(
            f"{API}/auth/google-session",
            json={"session_token": "not-a-real-google-token"},
            timeout=TIMEOUT,
        )
        # Should fail with 401 (invalid session).
        assert r.status_code == 401, f"expected 401, got {r.status_code} {r.text}"

    def test_logout(self, user_a):
        r = requests.post(f"{API}/auth/logout", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200


class TestRegressionLegacy:
    def test_priorities(self, user_a):
        r = requests.get(f"{API}/priorities", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_tasks_list(self, user_a):
        r = requests.get(f"{API}/tasks", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200
        assert "items" in r.json()


class TestRegressionDecisions:
    def test_list_top_get(self, user_a):
        r = requests.get(f"{API}/decisions", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200
        items = r.json()["items"]
        assert isinstance(items, list)
        r = requests.get(f"{API}/decisions/top?limit=3", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200
        top = r.json()["items"]
        assert isinstance(top, list)
        if items:
            r = requests.get(f"{API}/decisions/{items[0]['id']}", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
            assert r.status_code == 200

    def test_create_dismiss_complete(self, user_a):
        r = requests.post(
            f"{API}/decisions",
            headers=_hdr(user_a["token"]),
            json={"title": "REG test decision", "urgency": 5, "importance": 5},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        did = r.json()["id"]
        r = requests.post(f"{API}/decisions/{did}/dismiss", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200
        # new decision to complete
        r = requests.post(
            f"{API}/decisions",
            headers=_hdr(user_a["token"]),
            json={"title": "REG test decision 2", "urgency": 5, "importance": 5},
            timeout=TIMEOUT,
        )
        did2 = r.json()["id"]
        r = requests.post(f"{API}/decisions/{did2}/complete", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200


class TestRegressionLifeGraph:
    def test_vocab_and_seed_and_nodes(self, user_a):
        r = requests.get(f"{API}/life-graph/vocabulary", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200
        r = requests.post(f"{API}/life-graph/seed", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200
        r = requests.get(f"{API}/life-graph/nodes", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200
        nodes = r.json()["items"] if "items" in r.json() else r.json()
        assert isinstance(nodes, list) and len(nodes) > 0


class TestRegressionKnowledge:
    def test_schemas(self, user_a):
        r = requests.get(f"{API}/knowledge/schemas", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200

    def test_node_knowledge_shape(self, user_a):
        # Ensure seeded first
        requests.post(f"{API}/life-graph/seed", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        r = requests.get(f"{API}/life-graph/nodes", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        nodes = r.json()["items"] if "items" in r.json() else r.json()
        car = next((n for n in nodes if n.get("type") == "vehicle"), nodes[0])
        r = requests.get(f"{API}/knowledge/nodes/{car['id']}", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        # Presence of properties field is enough per review-request
        assert r.status_code == 200
        assert "properties" in r.json()


class TestRegressionAutoLink:
    def test_list_and_analyze(self, user_a):
        # Create a decision then analyze
        r = requests.post(
            f"{API}/decisions",
            headers=_hdr(user_a["token"]),
            json={"title": "Pagare la bolletta", "urgency": 6, "importance": 6, "category": "bill"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        did = r.json()["id"]
        r = requests.post(f"{API}/auto-link/decisions/{did}/analyze", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200
        r = requests.get(f"{API}/auto-link/decisions/{did}/proposals", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200


class TestRegressionAdmin:
    def test_admin_demo_refresh(self, demo_user):
        r = requests.post(f"{API}/admin/demo/refresh", headers=_hdr(demo_user["token"]), timeout=TIMEOUT)
        assert r.status_code == 200


class TestRegressionMemory:
    def test_memory_post_get(self, user_a):
        r = requests.post(
            f"{API}/memory",
            headers=_hdr(user_a["token"]),
            json={"content": "Test memory iter8", "tags": ["iter8"]},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        r = requests.get(f"{API}/memory", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200


# ======================================================================
# 2) Uniform /latest envelope
# ======================================================================
class TestLatestEnvelope:
    def test_latest_available_shape(self, user_a):
        # create decision & assemble
        r = requests.post(
            f"{API}/decisions",
            headers=_hdr(user_a["token"]),
            json={"title": "For latest", "urgency": 5, "importance": 5},
            timeout=TIMEOUT,
        )
        did = r.json()["id"]
        r = requests.post(
            f"{API}/context/decisions/{did}/assemble",
            headers=_hdr(user_a["token"]),
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        r = requests.get(
            f"{API}/context/decisions/{did}/latest",
            headers=_hdr(user_a["token"]),
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"snapshot", "status", "generated_at", "assembler_version"}
        assert body["status"] == "available"
        assert body["snapshot"] is not None
        assert body["generated_at"] is not None
        assert body["assembler_version"] == "context_assembler/v1.0"

    def test_latest_not_found_shape(self, user_a):
        # Fresh decision, never assembled.
        r = requests.post(
            f"{API}/decisions",
            headers=_hdr(user_a["token"]),
            json={"title": "For latest NF", "urgency": 4, "importance": 4},
            timeout=TIMEOUT,
        )
        did = r.json()["id"]
        r = requests.get(
            f"{API}/context/decisions/{did}/latest",
            headers=_hdr(user_a["token"]),
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"snapshot", "status", "generated_at", "assembler_version"}
        assert body["snapshot"] is None
        assert body["status"] == "not_found"
        assert body["generated_at"] is None
        assert body["assembler_version"] == "context_assembler/v1.0"

    def test_latest_cross_user_404(self, user_a, user_b):
        r = requests.post(
            f"{API}/decisions",
            headers=_hdr(user_a["token"]),
            json={"title": "For xuser latest", "urgency": 3, "importance": 3},
            timeout=TIMEOUT,
        )
        did = r.json()["id"]
        r = requests.get(
            f"{API}/context/decisions/{did}/latest",
            headers=_hdr(user_b["token"]),
            timeout=TIMEOUT,
        )
        assert r.status_code == 404

    def test_latest_no_token_401(self, user_a):
        r = requests.get(f"{API}/context/decisions/whatever/latest", timeout=TIMEOUT)
        assert r.status_code in (401, 403)


# ======================================================================
# 3) node_ids in POST /api/decisions
# ======================================================================
class TestDecisionNodeIds:
    def _seed(self, token: str) -> List[Dict[str, Any]]:
        requests.post(f"{API}/life-graph/seed", headers=_hdr(token), timeout=TIMEOUT)
        r = requests.get(f"{API}/life-graph/nodes", headers=_hdr(token), timeout=TIMEOUT)
        body = r.json()
        return body["items"] if "items" in body else body

    def test_create_with_node_ids_links_and_history(self, user_a):
        nodes = self._seed(user_a["token"])
        assert len(nodes) >= 2
        nid1, nid2 = nodes[0]["id"], nodes[1]["id"]
        r = requests.post(
            f"{API}/decisions",
            headers=_hdr(user_a["token"]),
            json={
                "title": "With node_ids",
                "urgency": 5,
                "importance": 5,
                "node_ids": [nid1, nid2],
            },
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text
        doc = r.json()
        assert set(doc.get("node_ids") or []) == {nid1, nid2}
        # History events use key "event" (see decision_engine/service.py:145)
        hist_types = [h.get("event") or h.get("type") for h in (doc.get("history") or [])]
        assert "created" in hist_types
        assert "life_graph.linked" in hist_types, f"history={hist_types}"

    def test_create_with_unknown_node_400_and_rollback(self, user_a):
        # count before
        r = requests.get(f"{API}/decisions", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        before = len(r.json()["items"])
        r = requests.post(
            f"{API}/decisions",
            headers=_hdr(user_a["token"]),
            json={
                "title": "Should fail",
                "urgency": 5,
                "importance": 5,
                "node_ids": ["node_INEXISTENT"],
            },
            timeout=TIMEOUT,
        )
        assert r.status_code == 400, r.text
        r = requests.get(f"{API}/decisions", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        after = len(r.json()["items"])
        assert after == before, f"decisions count changed: {before} -> {after} (rollback broken)"

    def test_create_without_node_ids_still_works(self, user_a):
        r = requests.post(
            f"{API}/decisions",
            headers=_hdr(user_a["token"]),
            json={"title": "Plain no nodes", "urgency": 5, "importance": 5},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        doc = r.json()
        assert doc.get("node_ids") in (None, [])

    def test_create_with_cross_user_node_id_400(self, user_a, user_b):
        # get a node owned by user_b
        requests.post(f"{API}/life-graph/seed", headers=_hdr(user_b["token"]), timeout=TIMEOUT)
        r = requests.get(f"{API}/life-graph/nodes", headers=_hdr(user_b["token"]), timeout=TIMEOUT)
        body = r.json()
        b_nodes = body["items"] if "items" in body else body
        b_nid = b_nodes[0]["id"]
        # user_a tries to link to b's node
        r = requests.post(
            f"{API}/decisions",
            headers=_hdr(user_a["token"]),
            json={
                "title": "Cross-user attack",
                "urgency": 5,
                "importance": 5,
                "node_ids": [b_nid],
            },
            timeout=TIMEOUT,
        )
        assert r.status_code == 400, r.text


# ======================================================================
# 4) Permissions module
# ======================================================================
class TestPermissionsRegistry:
    def test_registry_shape_11_items(self, user_a):
        r = requests.get(f"{API}/permissions/registry", timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert body["capability_registry_version"] == "1.0.0"
        items = body["items"]
        assert len(items) == 11, f"expected 11 items, got {len(items)}"
        required = {"id", "connector_domain", "verb", "data_categories", "sensitivity",
                    "platforms", "requires_oauth", "purposes", "default_status", "enabled"}
        for it in items:
            missing = required - set(it.keys())
            assert not missing, f"item {it.get('id')} missing keys: {missing}"

    def test_registry_by_id_known_and_unknown(self):
        r = requests.get(f"{API}/permissions/registry/calendar.read", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["id"] == "calendar.read"
        r = requests.get(f"{API}/permissions/registry/does.not.exist", timeout=TIMEOUT)
        assert r.status_code == 404


class TestPermissionsConsent:
    def test_grant_list_regrant_revoke(self, user_a):
        h = _hdr(user_a["token"])
        payload = {
            "capability_id": "calendar.read",
            "connector_id": "calendar_google",
            "connector_instance_id": "acct-A",
            "purpose_id": "scheduling",
        }
        # grant
        r = requests.post(f"{API}/permissions/consents/grant", headers=h, json=payload, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        doc1 = r.json()
        assert doc1["status"] == "active"
        v1 = doc1.get("version", 1)

        # list active
        r = requests.get(f"{API}/permissions/consents?status=active", headers=h, timeout=TIMEOUT)
        assert r.status_code == 200
        ids = [(c["capability_id"], c["connector_id"], c["connector_instance_id"]) for c in r.json()["items"]]
        assert ("calendar.read", "calendar_google", "acct-A") in ids

        # re-grant → version increments
        r = requests.post(f"{API}/permissions/consents/grant", headers=h, json=payload, timeout=TIMEOUT)
        assert r.status_code == 200
        doc2 = r.json()
        v2 = doc2.get("version", 1)
        assert v2 > v1, f"version did not increment: v1={v1} v2={v2}"

        # revoke
        r = requests.post(f"{API}/permissions/consents/revoke", headers=h, json={
            "capability_id": payload["capability_id"],
            "connector_id": payload["connector_id"],
            "connector_instance_id": payload["connector_instance_id"],
        }, timeout=TIMEOUT)
        assert r.status_code == 200
        drev = r.json()
        assert drev["status"] == "revoked"
        assert drev.get("revoked_at")

        # list active — should NOT contain
        r = requests.get(f"{API}/permissions/consents?status=active", headers=h, timeout=TIMEOUT)
        ids = [(c["capability_id"], c["connector_id"], c["connector_instance_id"]) for c in r.json()["items"]]
        assert ("calendar.read", "calendar_google", "acct-A") not in ids

    def test_grant_unknown_capability_404(self, user_a):
        r = requests.post(
            f"{API}/permissions/consents/grant",
            headers=_hdr(user_a["token"]),
            json={"capability_id": "does.not.exist", "connector_id": "x", "connector_instance_id": "y"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 404

    def test_revoke_all_for_connector(self, user_a):
        h = _hdr(user_a["token"])
        # grant two consents on same connector
        for inst in ("inst-1", "inst-2"):
            requests.post(f"{API}/permissions/consents/grant", headers=h, json={
                "capability_id": "calendar.read",
                "connector_id": "calendar_apple",
                "connector_instance_id": inst,
            }, timeout=TIMEOUT)
        r = requests.post(f"{API}/permissions/consents/revoke-all", headers=h,
                          json={"connector_id": "calendar_apple"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["revoked_count"] >= 1

    def test_wildcard_grant(self, user_a):
        h = _hdr(user_a["token"])
        r = requests.post(f"{API}/permissions/consents/grant", headers=h, json={
            "capability_id": "mail.metadata",
            "connector_id": "mail_gmail",
            "connector_instance_id": "*",
            "purpose_id": "bill_detection",
        }, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["connector_instance_id"] == "*"

    def test_audit_contains_events(self, user_a):
        r = requests.get(f"{API}/permissions/audit?limit=200", headers=_hdr(user_a["token"]), timeout=TIMEOUT)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) > 0
        types = {i["event_type"] for i in items}
        assert "consent.grant" in types
        assert "consent.revoke" in types
        # each event has required fields
        for ev in items[:20]:
            for k in ("event_id", "timestamp", "retention_until", "success", "reason_code"):
                assert k in ev, f"event missing {k}: {ev}"


class TestPermissionsAdminGuard:
    def test_admin_toggle_forbidden_for_non_demo(self, user_a):
        r = requests.patch(
            f"{API}/permissions/admin/registry/calendar.read",
            headers=_hdr(user_a["token"]),
            json={"enabled": True},
            timeout=TIMEOUT,
        )
        assert r.status_code == 403

    def test_admin_toggle_ok_for_demo(self, demo_user):
        r = requests.patch(
            f"{API}/permissions/admin/registry/calendar.read",
            headers=_hdr(demo_user["token"]),
            json={"enabled": True},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200


# ======================================================================
# 5) Connectors module
# ======================================================================
class TestConnectors:
    def test_registry_shape(self):
        r = requests.get(f"{API}/connectors/registry", timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        items = body["items"]
        assert len(items) == 14, f"expected 14 connectors, got {len(items)}"
        allowed = {"stub", "planned", "available", "disabled"}
        required = {"id", "category", "provider", "platforms", "required_capabilities", "status"}
        for c in items:
            miss = required - set(c.keys())
            assert not miss, f"{c.get('id')} missing {miss}"
            assert c["status"] in allowed

    def test_registry_by_id(self):
        r = requests.get(f"{API}/connectors/registry/calendar_google", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["id"] == "calendar_google"
        r = requests.get(f"{API}/connectors/registry/nope_nope", timeout=TIMEOUT)
        assert r.status_code == 404

    def test_status_requires_auth(self):
        r = requests.get(f"{API}/connectors/status", timeout=TIMEOUT)
        assert r.status_code in (401, 403)

    def test_status_snapshot_shape_and_grant_effect(self, user_a):
        h = _hdr(user_a["token"])
        # Clean any prior on this connector
        requests.post(f"{API}/permissions/consents/revoke-all", headers=h,
                      json={"connector_id": "calendar_google"}, timeout=TIMEOUT)
        # Snapshot before
        r = requests.get(f"{API}/connectors/status", headers=h, timeout=TIMEOUT)
        assert r.status_code == 200
        items = r.json()["items"]
        assert isinstance(items, list) and len(items) > 0
        sample = items[0]
        assert "consents" in sample and "summary" in sample
        for k in ("granted", "missing_capabilities", "instances"):
            assert k in sample["summary"], f"summary missing {k}"

        # Grant calendar.read for calendar_google
        r = requests.post(f"{API}/permissions/consents/grant", headers=h, json={
            "capability_id": "calendar.read",
            "connector_id": "calendar_google",
            "connector_instance_id": "primary",
            "purpose_id": "scheduling",
        }, timeout=TIMEOUT)
        assert r.status_code == 200
        # Query filtered status
        r = requests.get(f"{API}/connectors/status?connector_id=calendar_google", headers=h, timeout=TIMEOUT)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        cs = items[0]
        assert cs["summary"]["granted"] == 1, cs
        assert cs["summary"]["missing_capabilities"] == [], cs

    def test_no_connect_oauth_sync_webhook_endpoints(self):
        for suffix in (
            "/connectors/calendar_google/connect",
            "/connectors/calendar_google/oauth",
            "/connectors/calendar_google/sync",
            "/connectors/calendar_google/webhook",
            "/connectors/connect/calendar_google",
        ):
            r = requests.get(f"{API}{suffix}", timeout=TIMEOUT)
            assert r.status_code == 404, f"{suffix} unexpectedly {r.status_code}"
            r = requests.post(f"{API}{suffix}", timeout=TIMEOUT)
            assert r.status_code == 404, f"POST {suffix} unexpectedly {r.status_code}"


# ======================================================================
# 6) Context Assembler + Permissions provider default OFF
# ======================================================================
class TestAssemblerPermissionsFlagOff:
    def test_providers_run_includes_permissions_zero_signals_stable_hash(self, user_a):
        h = _hdr(user_a["token"])
        # create a fresh decision to guarantee an assemble path
        r = requests.post(
            f"{API}/decisions",
            headers=h,
            json={"title": "For provider check", "urgency": 5, "importance": 5},
            timeout=TIMEOUT,
        )
        did = r.json()["id"]
        r1 = requests.post(f"{API}/context/decisions/{did}/assemble", headers=h, timeout=TIMEOUT)
        assert r1.status_code == 200
        snap1 = r1.json()

        providers_run = (snap1.get("provenance") or {}).get("providers_run") or []
        assert "permissions" in providers_run, f"providers_run={providers_run}"

        # zero signals with source_module == permissions (flag OFF)
        perms_signals = [s for s in (snap1.get("signals") or []) if s.get("source_module") == "permissions"]
        assert len(perms_signals) == 0, f"expected 0 permissions signals, got {len(perms_signals)}"

        # same decision, second assemble → same context_hash (byte-stable)
        r2 = requests.post(f"{API}/context/decisions/{did}/assemble", headers=h, timeout=TIMEOUT)
        assert r2.status_code == 200
        snap2 = r2.json()
        assert snap1.get("context_hash") == snap2.get("context_hash"), (
            f"hash changed: {snap1.get('context_hash')} vs {snap2.get('context_hash')}"
        )
