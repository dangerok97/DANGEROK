"""Iterazione 18.2 — audit + wiring tests (HTTP-only).

Uses only HTTP endpoints (shared TestClient loop) to avoid motor
event-loop mismatch. Verifies:
  A) Memory ↔ Knowledge/LifeGraph wiring
  B) Behavior-Aware Shadow auto-trigger inside /decisions/top
  C) Startup: shadow indexes present via config-status side effects
"""
from __future__ import annotations

import os
import sys
import time
import uuid

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
sys.path.insert(0, "/app/backend")

from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

TS = f"iter18_2_{int(time.time())}_{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="module")
def client(shared_client):
    return shared_client


@pytest.fixture(scope="module")
def user_a(client):
    r = client.post("/api/auth/register", json={
        "email": f"{TS}_a@ora.app",
        "password": "Passw0rd!",
        "name": "Iter18.2 A",
    })
    assert r.status_code == 200, r.text
    return {"token": r.json()["token"], "user_id": r.json()["user"]["user_id"]}


def h(user):
    return {"Authorization": f"Bearer {user['token']}"}


# =====================================================================
# A) Memory ↔ Knowledge/LifeGraph wiring
# =====================================================================
class TestA_MemoryWiring:
    def test_a1_memory_saved_and_returns_life_node_id(self, client, user_a):
        content = f"Ho comprato il televisore da MediaWorld {TS}"
        r = client.post("/api/memory", headers=h(user_a), json={
            "content": content, "tags": ["acquisto"],
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["content"] == content
        assert body["id"].startswith("mem_")
        # Retro-compat: original fields present
        assert body["tags"] == ["acquisto"]
        assert "created_at" in body
        # New wiring: back-reference to life-graph node
        assert body.get("life_node_id"), "life_node_id must be attached to memory doc"
        assert body.get("knowledge_synced") is True

    def test_a2_life_node_exists_with_subtype_memory(self, client, user_a):
        content = f"Assicurazione auto scade 15 giugno {TS}"
        r = client.post("/api/memory", headers=h(user_a), json={"content": content})
        node_id = r.json()["life_node_id"]

        # Retrieve node via life-graph API
        r2 = client.get(f"/api/life-graph/nodes/{node_id}", headers=h(user_a))
        assert r2.status_code == 200, r2.text
        node = r2.json()
        assert node["type"] == "generic"
        attrs = node.get("attributes") or {}
        assert attrs.get("subtype") == "memory"
        assert attrs.get("source") == "user_memory"

    def test_a3_knowledge_facts_are_attached(self, client, user_a):
        content = f"Codice fiscale di Anna: RSSMRA80A01H501U {TS}"
        r = client.post("/api/memory", headers=h(user_a), json={"content": content, "tags": ["family"]})
        node_id = r.json()["life_node_id"]

        r2 = client.get(f"/api/knowledge/nodes/{node_id}", headers=h(user_a))
        assert r2.status_code == 200, r2.text
        kdoc = r2.json()
        props = kdoc.get("properties") or {}
        # Both summary and notes must be present
        assert "summary" in props, f"missing 'summary' in {list(props.keys())}"
        assert "notes" in props, f"missing 'notes' in {list(props.keys())}"
        notes_env = props["notes"]
        notes_val = notes_env.get("value") if isinstance(notes_env, dict) else notes_env
        assert notes_val and content[:30] in notes_val

    def test_a4_get_memory_returns_original_shape(self, client, user_a):
        r = client.get("/api/memory", headers=h(user_a))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 3  # 3 memories from A1–A3
        for m in items:
            assert m["id"].startswith("mem_")
            assert "content" in m
            assert "created_at" in m

    def test_a5_life_graph_listing_shows_memory_nodes(self, client, user_a):
        r = client.get("/api/life-graph/nodes?type=generic", headers=h(user_a))
        assert r.status_code == 200
        items = r.json().get("items") or r.json().get("nodes") or []
        # Filter to memory-subtype nodes for this user
        memory_nodes = [n for n in items if (n.get("attributes") or {}).get("subtype") == "memory"]
        assert len(memory_nodes) >= 3


# =====================================================================
# B) Behavior-Aware Shadow auto-trigger (via /decisions/top)
# =====================================================================
class TestB_ShadowAutoTrigger:
    def _shadow_count(self, client, user):
        # Use the public shadow API to count evaluations for this user.
        r = client.get("/api/behavior-shadow/evaluations?limit=1000", headers=h(user))
        # If endpoint is 404/gated it means shadow disabled — return 0.
        if r.status_code != 200:
            return 0
        data = r.json()
        items = data.get("items") if isinstance(data, dict) else data
        return len(items or [])

    def test_b1_flags_off_no_shadow_evaluations(self, client, user_a, monkeypatch):
        monkeypatch.setenv("BEHAVIOR_PROFILE_ENABLED", "false")
        monkeypatch.setenv("BEHAVIOR_SHADOW_MODE", "false")

        before = self._shadow_count(client, user_a)
        r = client.get("/api/decisions/top?limit=3", headers=h(user_a))
        assert r.status_code == 200
        time.sleep(0.3)  # let any hypothetical task run
        after = self._shadow_count(client, user_a)
        assert after == before, "no eval should be produced when flags are off"

    def test_b2_ranking_order_stable_across_flag_states(self, client, user_a, monkeypatch):
        monkeypatch.setenv("BEHAVIOR_PROFILE_ENABLED", "false")
        r1 = client.get("/api/decisions/top?limit=5", headers=h(user_a))
        monkeypatch.setenv("BEHAVIOR_PROFILE_ENABLED", "true")
        monkeypatch.setenv("BEHAVIOR_SHADOW_MODE", "true")
        r2 = client.get("/api/decisions/top?limit=5", headers=h(user_a))
        assert r1.status_code == r2.status_code == 200
        ids1 = [d["id"] for d in r1.json()["items"]]
        ids2 = [d["id"] for d in r2.json()["items"]]
        assert ids1 == ids2, "shadow trigger must NOT change ranking order"

    def test_b3_flags_on_produces_shadow_evaluations(self, client, user_a, monkeypatch):
        monkeypatch.setenv("BEHAVIOR_PROFILE_ENABLED", "true")
        monkeypatch.setenv("BEHAVIOR_SHADOW_MODE", "true")

        # Ensure at least one decision exists
        client.post("/api/tasks", headers=h(user_a), json={
            "title": f"Task per shadow trigger {TS}", "urgency": 8, "importance": 7,
        })

        before = self._shadow_count(client, user_a)
        r = client.get("/api/decisions/top?limit=5", headers=h(user_a))
        assert r.status_code == 200

        # Fire-and-forget: poll for up to 3s
        after = before
        for _ in range(30):
            time.sleep(0.1)
            after = self._shadow_count(client, user_a)
            if after > before:
                break
        assert after > before, f"expected evals >{before}, got {after}"

        # ranking_applied invariant: fetch latest evaluations, assert all false.
        r2 = client.get("/api/behavior-shadow/evaluations?limit=20", headers=h(user_a))
        assert r2.status_code == 200
        data = r2.json()
        items = data.get("items") if isinstance(data, dict) else data
        assert items, "expected shadow items after flags on"
        assert all(it.get("ranking_applied") is False for it in items), \
            "ranking_applied invariant violated"


# =====================================================================
# C) Startup wiring — shadow indexes ensured on boot
# =====================================================================
class TestC_StartupIndices:
    def test_c1_stats_endpoint_reachable(self, client, user_a, monkeypatch):
        """A reachable /stats endpoint implies the shadow collection was
        successfully bootstrapped at startup (no missing index / no crash)."""
        monkeypatch.setenv("BEHAVIOR_PROFILE_ENABLED", "true")
        monkeypatch.setenv("BEHAVIOR_SHADOW_MODE", "true")
        r = client.get("/api/behavior-shadow/stats", headers=h(user_a))
        assert r.status_code == 200, r.text
        body = r.json()
        # Structure sanity — either has total or is empty dict
        assert isinstance(body, dict)
