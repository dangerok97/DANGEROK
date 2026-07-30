"""
ORA — Life Graph Core + regression tests (iteration 3).

Covers: vocabulary, seed idempotency, node CRUD, edges + traversal,
decision <-> node linking, auth guards, cross-user isolation, and
regression on decisions/memory/auth.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://ora-decision-engine.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

TS = int(time.time())
USER_A_EMAIL = f"lifegraph_a_{TS}@ora.app"
USER_B_EMAIL = f"lifegraph_b_{TS}@ora.app"
PASSWORD = "Demo!2026"
DEMO_EMAIL = "demo@ora.app"


# ---------- shared session state ---------- #
STATE = {
    "token_a": None,
    "token_b": None,
    "seed_a": None,
    "seed_b": None,
    "created_node_id": None,
    "extra_edge_id": None,
    "bill_decision_id": None,
}


def _hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ============================================================
# 0. Setup: register fresh users
# ============================================================
class TestSetup:
    def test_register_user_a(self):
        r = requests.post(f"{API}/auth/register", json={"email": USER_A_EMAIL, "password": PASSWORD, "name": "A"})
        assert r.status_code == 200, r.text
        STATE["token_a"] = r.json()["token"]

    def test_register_user_b(self):
        r = requests.post(f"{API}/auth/register", json={"email": USER_B_EMAIL, "password": PASSWORD, "name": "B"})
        assert r.status_code == 200, r.text
        STATE["token_b"] = r.json()["token"]


# ============================================================
# A. Vocabulary + seed
# ============================================================
class TestVocabularyAndSeed:
    def test_1_vocabulary_no_auth(self):
        r = requests.get(f"{API}/life-graph/vocabulary")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "node_types" in data and "relation_types" in data
        required_nodes = {"home","car","person","job","university","trip","subscription",
                          "contract","document","purchase","health","pet","goal","event"}
        required_rels = {"owns","lives_at","belongs_to","pays_for","documents",
                         "assigned_to","has_member","related_to","parent_of"}
        assert required_nodes.issubset(set(data["node_types"])), data["node_types"]
        assert required_rels.issubset(set(data["relation_types"])), data["relation_types"]

    def test_2_seed_first_call(self):
        r = requests.post(f"{API}/life-graph/seed", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] == 8
        assert "root" in data
        for k in ("me","casa","auto","salute","uni","lavoro","bolletta","assic"):
            assert k in data["nodes"], data
        STATE["seed_a"] = data

    def test_2b_seed_second_call_noop(self):
        r = requests.post(f"{API}/life-graph/seed", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        data = r.json()
        assert data["created"] == 0
        assert data.get("reason") == "already_seeded"

    def test_3_list_nodes_after_seed(self):
        r = requests.get(f"{API}/life-graph/nodes", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 8, len(items)
        required_keys = {"id","user_id","type","label","description","attributes","status","origin","created_at","updated_at"}
        for it in items:
            missing = required_keys - set(it.keys())
            assert not missing, f"missing keys: {missing}"
            assert "_id" not in it
            assert it["status"] == "active"
        types = {it["type"] for it in items}
        assert {"person","home","car","health","university","job","subscription","contract"}.issubset(types)

    def test_4_filter_by_type_home(self):
        r = requests.get(f"{API}/life-graph/nodes?type=home", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["label"] == "Casa"


# ============================================================
# B. Node CRUD
# ============================================================
class TestNodeCRUD:
    def test_5_create_pet_node(self):
        r = requests.post(f"{API}/life-graph/nodes", headers=_hdr(STATE["token_a"]),
                          json={"type": "pet", "label": "Luna", "description": "Gatto"})
        assert r.status_code == 200, r.text
        node = r.json()
        assert node["id"].startswith("node_")
        assert node["type"] == "pet"
        STATE["created_node_id"] = node["id"]

    def test_6_get_created_node(self):
        nid = STATE["created_node_id"]
        r = requests.get(f"{API}/life-graph/nodes/{nid}", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        assert r.json()["label"] == "Luna"

    def test_7_patch_label(self):
        nid = STATE["created_node_id"]
        # ensure updated_at differs
        time.sleep(1.1)
        r = requests.patch(f"{API}/life-graph/nodes/{nid}", headers=_hdr(STATE["token_a"]),
                           json={"label": "Luna (gatta)"})
        assert r.status_code == 200
        n = r.json()
        assert n["label"] == "Luna (gatta)"
        assert n["updated_at"] != n["created_at"]

    def test_8_delete_soft_archive(self):
        nid = STATE["created_node_id"]
        r = requests.delete(f"{API}/life-graph/nodes/{nid}", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # default listing excludes archived
        r2 = requests.get(f"{API}/life-graph/nodes", headers=_hdr(STATE["token_a"]))
        ids = [i["id"] for i in r2.json()["items"]]
        assert nid not in ids

        # include_archived=true returns it
        r3 = requests.get(f"{API}/life-graph/nodes?include_archived=true", headers=_hdr(STATE["token_a"]))
        found = [i for i in r3.json()["items"] if i["id"] == nid]
        assert len(found) == 1
        assert found[0]["status"] == "archived"

    def test_9_unknown_node_404(self):
        for method in ("get", "delete"):
            r = getattr(requests, method)(f"{API}/life-graph/nodes/node_does_not_exist",
                                          headers=_hdr(STATE["token_a"]))
            assert r.status_code == 404, f"{method}: {r.status_code}"
        r = requests.patch(f"{API}/life-graph/nodes/node_does_not_exist", headers=_hdr(STATE["token_a"]),
                           json={"label": "x"})
        assert r.status_code == 404

    def test_10_unknown_type_normalizes_to_generic(self):
        r = requests.post(f"{API}/life-graph/nodes", headers=_hdr(STATE["token_a"]),
                          json={"type": "banana", "label": "Test"})
        assert r.status_code == 200
        assert r.json()["type"] == "generic"


# ============================================================
# C. Edges & traversal
# ============================================================
class TestEdgesAndTraversal:
    def test_11_list_edges_after_seed(self):
        r = requests.get(f"{API}/life-graph/edges", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 7, len(items)
        required = {"id","user_id","from_node","to_node","type","directed","attributes","created_at"}
        for e in items:
            assert not (required - set(e.keys()))
            assert "_id" not in e

    def test_12_create_edge_related_to(self):
        s = STATE["seed_a"]["nodes"]
        r = requests.post(f"{API}/life-graph/edges", headers=_hdr(STATE["token_a"]),
                          json={"from_node": s["salute"], "to_node": s["uni"], "type": "related_to"})
        assert r.status_code == 200, r.text
        edge = r.json()
        assert edge["directed"] is False
        assert edge["type"] == "related_to"
        STATE["extra_edge_id"] = edge["id"]

    def test_13_edge_same_endpoints_400(self):
        s = STATE["seed_a"]["nodes"]
        r = requests.post(f"{API}/life-graph/edges", headers=_hdr(STATE["token_a"]),
                          json={"from_node": s["casa"], "to_node": s["casa"], "type": "related_to"})
        assert r.status_code == 400

    def test_14_edge_missing_node_404(self):
        s = STATE["seed_a"]["nodes"]
        r = requests.post(f"{API}/life-graph/edges", headers=_hdr(STATE["token_a"]),
                          json={"from_node": s["casa"], "to_node": "node_missing", "type": "related_to"})
        assert r.status_code == 404

    def test_15_graph_depth_2(self):
        me = STATE["seed_a"]["nodes"]["me"]
        r = requests.get(f"{API}/life-graph/nodes/{me}/graph?depth=2", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        data = r.json()
        for k in ("root","nodes","edges","distances","decisions"):
            assert k in data, k
        assert data["root"]["id"] == me
        assert len(data["nodes"]) == 8
        assert len(data["edges"]) >= 7
        assert all(0 <= d <= 2 for d in data["distances"].values())

    def test_16_graph_depth_1_excludes_bolletta(self):
        me = STATE["seed_a"]["nodes"]["me"]
        casa = STATE["seed_a"]["nodes"]["casa"]
        bolletta = STATE["seed_a"]["nodes"]["bolletta"]
        r = requests.get(f"{API}/life-graph/nodes/{me}/graph?depth=1", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        data = r.json()
        node_ids = {n["id"] for n in data["nodes"]}
        assert casa in node_ids
        assert bolletta not in node_ids

    def test_17_delete_edge(self):
        eid = STATE["extra_edge_id"]
        r_before = requests.get(f"{API}/life-graph/edges", headers=_hdr(STATE["token_a"]))
        n_before = len(r_before.json()["items"])
        r = requests.delete(f"{API}/life-graph/edges/{eid}", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        r_after = requests.get(f"{API}/life-graph/edges", headers=_hdr(STATE["token_a"]))
        assert len(r_after.json()["items"]) == n_before - 1


# ============================================================
# D. Decision <-> Node linking
# ============================================================
class TestDecisionNodeLinking:
    def test_18_find_bill_decision_and_link(self):
        r = requests.get(f"{API}/decisions/top?limit=5", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        items = r.json()["items"]
        bill = next((d for d in items if d.get("category") == "bill"), None)
        assert bill is not None, [d.get("category") for d in items]
        STATE["bill_decision_id"] = bill["id"]

        s = STATE["seed_a"]["nodes"]
        r2 = requests.post(f"{API}/life-graph/decisions/{bill['id']}/nodes",
                           headers=_hdr(STATE["token_a"]),
                           json={"node_ids": [s["casa"], s["bolletta"]]})
        assert r2.status_code == 200, r2.text
        d = r2.json()
        assert s["casa"] in d.get("node_ids", [])
        assert s["bolletta"] in d.get("node_ids", [])

    def test_19_history_event_linked(self):
        did = STATE["bill_decision_id"]
        r = requests.get(f"{API}/decisions/{did}", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        d = r.json()
        history = d.get("history", [])
        assert history, "no history entries"
        assert history[-1]["event"] == "life_graph.linked"

    def test_20_link_idempotent(self):
        did = STATE["bill_decision_id"]
        s = STATE["seed_a"]["nodes"]
        r = requests.post(f"{API}/life-graph/decisions/{did}/nodes",
                          headers=_hdr(STATE["token_a"]),
                          json={"node_ids": [s["casa"], s["bolletta"]]})
        assert r.status_code == 200
        node_ids = r.json().get("node_ids", [])
        # no duplicates
        assert node_ids.count(s["casa"]) == 1
        assert node_ids.count(s["bolletta"]) == 1

    def test_21_link_unknown_node_404(self):
        did = STATE["bill_decision_id"]
        r = requests.post(f"{API}/life-graph/decisions/{did}/nodes",
                          headers=_hdr(STATE["token_a"]),
                          json={"node_ids": ["node_missing_xxx"]})
        assert r.status_code == 404

    def test_22_decisions_for_node_casa(self):
        casa = STATE["seed_a"]["nodes"]["casa"]
        r = requests.get(f"{API}/life-graph/nodes/{casa}/decisions", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        items = r.json()["items"]
        ids = [d["id"] for d in items]
        assert STATE["bill_decision_id"] in ids

    def test_23_unlink_bolletta(self):
        did = STATE["bill_decision_id"]
        s = STATE["seed_a"]["nodes"]
        r = requests.delete(f"{API}/life-graph/decisions/{did}/nodes/{s['bolletta']}",
                            headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200
        d = r.json()
        assert s["bolletta"] not in d.get("node_ids", [])
        assert s["casa"] in d.get("node_ids", [])
        assert d["history"][-1]["event"] == "life_graph.unlinked"

    def test_24_archive_casa_cascades(self):
        did = STATE["bill_decision_id"]
        s = STATE["seed_a"]["nodes"]
        casa = s["casa"]
        # Verify casa still linked
        r0 = requests.get(f"{API}/decisions/{did}", headers=_hdr(STATE["token_a"]))
        assert casa in r0.json().get("node_ids", [])

        # Count edges touching casa before
        r_edges = requests.get(f"{API}/life-graph/edges?node_id={casa}", headers=_hdr(STATE["token_a"]))
        edges_before = len(r_edges.json()["items"])
        assert edges_before >= 1

        # Archive
        r = requests.delete(f"{API}/life-graph/nodes/{casa}", headers=_hdr(STATE["token_a"]))
        assert r.status_code == 200

        # Decision no longer references casa
        r2 = requests.get(f"{API}/decisions/{did}", headers=_hdr(STATE["token_a"]))
        assert casa not in r2.json().get("node_ids", [])

        # Edges touching casa are gone
        r_edges_after = requests.get(f"{API}/life-graph/edges?node_id={casa}", headers=_hdr(STATE["token_a"]))
        assert len(r_edges_after.json()["items"]) == 0


# ============================================================
# E. Auth guards
# ============================================================
class TestAuthGuards:
    def test_25_no_token_401(self):
        endpoints = [
            ("get", f"{API}/life-graph/nodes"),
            ("post", f"{API}/life-graph/seed"),
            ("get", f"{API}/life-graph/edges"),
        ]
        for method, url in endpoints:
            r = getattr(requests, method)(url)
            assert r.status_code in (401, 403), f"{url}: {r.status_code}"

    def test_26_cross_user_isolation(self):
        # user B seeds
        rb = requests.post(f"{API}/life-graph/seed", headers=_hdr(STATE["token_b"]))
        assert rb.status_code == 200
        # Pick one of A's remaining nodes
        rA = requests.get(f"{API}/life-graph/nodes", headers=_hdr(STATE["token_a"]))
        a_node_id = rA.json()["items"][0]["id"]

        # B cannot GET A's node
        r = requests.get(f"{API}/life-graph/nodes/{a_node_id}", headers=_hdr(STATE["token_b"]))
        assert r.status_code == 404
        r = requests.patch(f"{API}/life-graph/nodes/{a_node_id}", headers=_hdr(STATE["token_b"]),
                           json={"label": "hack"})
        assert r.status_code == 404
        r = requests.delete(f"{API}/life-graph/nodes/{a_node_id}", headers=_hdr(STATE["token_b"]))
        assert r.status_code == 404


# ============================================================
# F. Regression: Decision Engine, memory, auth
# ============================================================
class TestRegression:
    demo_token = None

    def test_27_demo_login_and_top_3(self):
        r = requests.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": PASSWORD})
        assert r.status_code == 200, r.text
        TestRegression.demo_token = r.json()["token"]

        r2 = requests.get(f"{API}/decisions/top?limit=3", headers=_hdr(TestRegression.demo_token))
        assert r2.status_code == 200
        items = r2.json()["items"]
        assert len(items) == 3
        scores = [i["score"] for i in items]
        assert scores == sorted(scores, reverse=True)
        top1 = items[0]
        tags = top1.get("reason_tags", [])
        assert "imminent" in tags, tags

    def test_28_resolve_returns_italian_solution(self):
        r = requests.get(f"{API}/decisions/top?limit=1", headers=_hdr(TestRegression.demo_token))
        did = r.json()["items"][0]["id"]
        r2 = requests.post(f"{API}/decisions/{did}/resolve", headers=_hdr(TestRegression.demo_token))
        assert r2.status_code == 200, r2.text
        sol = r2.json().get("solution", "")
        assert isinstance(sol, str) and len(sol) > 20

    def test_29_complete_and_dismiss(self):
        # Use fresh user A – has decisions from seed
        r = requests.get(f"{API}/decisions/top?limit=3", headers=_hdr(STATE["token_a"]))
        items = r.json()["items"]
        assert len(items) >= 2
        did1 = items[0]["id"]
        did2 = items[1]["id"]
        r1 = requests.post(f"{API}/decisions/{did1}/complete", headers=_hdr(STATE["token_a"]))
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/decisions/{did2}/dismiss", headers=_hdr(STATE["token_a"]))
        assert r2.status_code == 200

    def test_30_legacy_priorities_and_tasks(self):
        r = requests.get(f"{API}/priorities", headers=_hdr(TestRegression.demo_token))
        assert r.status_code == 200
        items = r.json()["items"]
        assert 1 <= len(items) <= 3
        # legacy task-shape must have `kind` and `context` keys
        assert "kind" in items[0] and "context" in items[0]

        r2 = requests.get(f"{API}/tasks", headers=_hdr(TestRegression.demo_token))
        assert r2.status_code == 200

    def test_31_memory_add_and_ask(self):
        r = requests.post(f"{API}/memory", headers=_hdr(STATE["token_a"]),
                          json={"content": "Il mio codice fiscale finisce con 7X", "tags": ["docs"]})
        assert r.status_code == 200
        r2 = requests.post(f"{API}/memory/ask", headers=_hdr(STATE["token_a"]),
                           json={"question": "Con cosa finisce il mio codice fiscale?"})
        assert r2.status_code == 200
        assert "answer" in r2.json()

    def test_32_auth_error_cases(self):
        r = requests.post(f"{API}/auth/register", json={"email": USER_A_EMAIL, "password": PASSWORD})
        assert r.status_code == 409
        r2 = requests.post(f"{API}/auth/login", json={"email": USER_A_EMAIL, "password": "wrong"})
        assert r2.status_code == 401
        r3 = requests.get(f"{API}/auth/me")
        assert r3.status_code == 401
