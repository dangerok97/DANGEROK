"""Iteration 4 — Knowledge Layer + regression tests for ORA backend."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', 'https://ora-decision-engine.preview.emergentagent.com').rstrip('/')

TS = int(time.time())
USER_A = {"email": f"knowledge_a_{TS}@ora.app", "password": "Demo!2026", "name": "KA"}
USER_B = {"email": f"knowledge_b_{TS}@ora.app", "password": "Demo!2026", "name": "KB"}


@pytest.fixture(scope="module")
def state():
    return {}


@pytest.fixture(scope="module")
def sess():
    return requests.Session()


# ---- A. Schemas (public) ----
class TestSchemas:
    def test_01_list_schemas(self, sess):
        r = sess.get(f"{BASE_URL}/api/knowledge/schemas")
        assert r.status_code == 200
        data = r.json()
        assert "schemas" in data and "types" in data
        expected = sorted(["car", "contract", "document", "event", "finance", "generic",
                           "goal", "health", "home", "job", "person", "pet", "purchase",
                           "subscription", "trip", "university"])
        assert data["types"] == expected

    def test_02_schema_field_shape(self, sess):
        r = sess.get(f"{BASE_URL}/api/knowledge/schemas").json()
        home = r["schemas"]["home"]
        home_type = next(p for p in home if p["key"] == "home_type")
        assert "casa_principale" in home_type["options"]
        car = r["schemas"]["car"]
        assert any(p["key"] == "plate" for p in car)
        person = r["schemas"]["person"]
        bday = next(p for p in person if p["key"] == "birthday")
        assert bday["type"] == "date"

    def test_03_schema_by_type(self, sess):
        r = sess.get(f"{BASE_URL}/api/knowledge/schemas/home")
        assert r.status_code == 200
        d = r.json()
        assert d["node_type"] == "home"
        assert isinstance(d["schema"], list) and len(d["schema"]) == 12

    def test_04_schema_fallback(self, sess):
        r = sess.get(f"{BASE_URL}/api/knowledge/schemas/nonexistent")
        assert r.status_code == 200
        assert r.json()["schema"] == sess.get(f"{BASE_URL}/api/knowledge/schemas/generic").json()["schema"]


# ---- Auth + seed helper ----
def _register(sess, u):
    r = sess.post(f"{BASE_URL}/api/auth/register", json=u)
    assert r.status_code == 200, r.text
    return r.json()["token"]


class TestAuthAndSeed:
    def test_05_register_user_a_and_seed(self, sess, state):
        state["token_a"] = _register(sess, USER_A)
        h = {"Authorization": f"Bearer {state['token_a']}"}
        r = sess.post(f"{BASE_URL}/api/life-graph/seed", headers=h)
        assert r.status_code == 200
        r2 = sess.get(f"{BASE_URL}/api/life-graph/nodes", headers=h)
        assert r2.status_code == 200
        nodes = r2.json()["items"]
        state["nodes_a"] = nodes
        home = next((n for n in nodes if n["type"] == "home"), None)
        car = next((n for n in nodes if n["type"] == "car"), None)
        assert home and car
        state["home_id"] = home["id"]
        state["car_id"] = car["id"]

    def test_06_register_user_b(self, sess, state):
        state["token_b"] = _register(sess, USER_B)

    def test_07_auth_required(self, sess, state):
        for method, url in [
            ("get", f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}"),
            ("put", f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}"),
            ("patch", f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}"),
            ("delete", f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}"),
            ("get", f"{BASE_URL}/api/knowledge"),
        ]:
            r = sess.request(method, url, json={"properties": {}})
            assert r.status_code == 401, f"{method} {url} -> {r.status_code}"

    def test_08_cross_user_404(self, sess, state):
        hb = {"Authorization": f"Bearer {state['token_b']}"}
        r = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}", headers=hb)
        assert r.status_code == 404
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}",
                       json={"properties": {"x": 1}}, headers=hb)
        assert r.status_code == 404
        r = sess.put(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}",
                     json={"properties": {"x": 1}}, headers=hb)
        assert r.status_code == 404
        r = sess.delete(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}", headers=hb)
        assert r.status_code == 404


# ---- C. Read/write flow ----
class TestReadWrite:
    def _h(self, state):
        return {"Authorization": f"Bearer {state['token_a']}"}

    def test_09_get_empty(self, sess, state):
        r = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}", headers=self._h(state))
        assert r.status_code == 200
        d = r.json()
        assert d["properties"] == {}
        assert d["node_type"] == "home"
        assert len(d["schema"]) == 12
        assert d["id"] is None and d["created_at"] is None and d["updated_at"] is None

    def test_10_patch_creates(self, sess, state):
        payload = {"properties": {
            "home_type": "casa_principale",
            "address": "Via Roma 12",
            "residents": ["Marco", "Anna"],
            "purchase_date": "2020-06-15",
        }}
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}",
                       json=payload, headers=self._h(state))
        assert r.status_code == 200
        d = r.json()
        for k in ("home_type", "address", "residents", "purchase_date"):
            assert k in d["properties"]
        assert d["properties"]["residents"] == ["Marco", "Anna"]
        events = [h["event"] for h in d["history"]]
        assert "created" in events

    def test_11_patch_merges(self, sess, state):
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}",
                       json={"properties": {"owner": "Marco"}}, headers=self._h(state))
        d = r.json()
        for k in ("home_type", "address", "residents", "purchase_date", "owner"):
            assert k in d["properties"], f"missing {k}"
        events = [h["event"] for h in d["history"]]
        assert events.count("created") == 1
        assert "merged" in events

    def test_12_patch_null_deletes(self, sess, state):
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}",
                       json={"properties": {"address": None}}, headers=self._h(state))
        d = r.json()
        assert "address" not in d["properties"]
        assert "owner" in d["properties"]

    def test_13_put_replaces(self, sess, state):
        r = sess.put(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}",
                     json={"properties": {"home_type": "seconda_casa"}}, headers=self._h(state))
        d = r.json()
        assert list(d["properties"].keys()) == ["home_type"]
        assert d["properties"]["home_type"] == "seconda_casa"
        events = [h["event"] for h in d["history"]]
        assert "replaced" in events


# ---- D. Extensibility & coercion ----
class TestCoercion:
    def _h(self, state):
        return {"Authorization": f"Bearer {state['token_a']}"}

    def test_14_car_coercion_and_extras(self, sess, state):
        payload = {"properties": {
            "brand": "Fiat", "model": "500", "plate": "AB123CD",
            "mileage_km": "48500",
            "weird_key": {"foo": "bar"},
            "another_extra": 123,
        }}
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                       json=payload, headers=self._h(state))
        assert r.status_code == 200
        d = r.json()
        assert d["properties"]["mileage_km"] == 48500
        assert isinstance(d["properties"]["mileage_km"], int)
        extra = d["properties"].get("_extra", {})
        assert "weird_key" in extra and "another_extra" in extra

    def test_15_extra_null_removes(self, sess, state):
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                       json={"properties": {"_extra": {"weird_key": None}}},
                       headers=self._h(state))
        d = r.json()
        extra = d["properties"].get("_extra", {})
        assert "weird_key" not in extra
        assert "another_extra" in extra

    def test_16_string_list_autowrap(self, sess, state):
        # First re-seed home properties to include residents baseline (put replaced earlier)
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}",
                       json={"properties": {"residents": "Solo"}},
                       headers=self._h(state))
        d = r.json()
        assert d["properties"]["residents"] == ["Solo"]


# ---- E. Single-property endpoints ----
class TestSingleProperty:
    def _h(self, state):
        return {"Authorization": f"Bearer {state['token_a']}"}

    def test_17_put_property(self, sess, state):
        r = sess.put(
            f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}/properties/road_tax",
            json={"value": {"amount": 220, "paid": False}}, headers=self._h(state),
        )
        assert r.status_code == 200
        d = r.json()
        assert d["properties"]["road_tax"] == {"amount": 220, "paid": False}
        r2 = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}", headers=self._h(state))
        assert r2.json()["properties"]["road_tax"]["amount"] == 220

    def test_18_delete_property(self, sess, state):
        r = sess.delete(
            f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}/properties/mileage_km",
            headers=self._h(state),
        )
        d = r.json()
        assert "mileage_km" not in d["properties"]
        assert "brand" in d["properties"]

    def test_19_clear(self, sess, state):
        r = sess.delete(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}", headers=self._h(state))
        d = r.json()
        assert d["properties"] == {}
        events = [h["event"] for h in d["history"]]
        assert "cleared" in events


# ---- F. Bulk ----
class TestBulk:
    def test_20_list_all(self, sess, state):
        h = {"Authorization": f"Bearer {state['token_a']}"}
        r = sess.get(f"{BASE_URL}/api/knowledge", headers=h)
        assert r.status_code == 200
        items = r.json()["items"]
        node_ids = {it["node_id"] for it in items}
        assert state["home_id"] in node_ids and state["car_id"] in node_ids
        # updated_at desc
        uas = [it.get("updated_at") for it in items if it.get("updated_at")]
        assert uas == sorted(uas, reverse=True)


# ---- G. Regression ----
class TestRegression:
    def _h(self, state):
        return {"Authorization": f"Bearer {state['token_a']}"}

    def test_21_life_graph_unchanged(self, sess, state):
        r = sess.get(f"{BASE_URL}/api/life-graph/nodes", headers=self._h(state))
        nodes = r.json()["items"]
        assert len(nodes) == 8
        # Verify no 'knowledge' field leaked onto node docs
        for n in nodes:
            assert "knowledge" not in n

    def test_22_node_graph(self, sess, state):
        r = sess.get(
            f"{BASE_URL}/api/life-graph/nodes/{state['home_id']}/graph?depth=2",
            headers=self._h(state))
        assert r.status_code == 200
        d = r.json()
        assert "nodes" in d and "edges" in d and "decisions" in d

    def test_23_decisions_top_imminent(self, sess, state):
        r = sess.get(f"{BASE_URL}/api/decisions/top?limit=3", headers=self._h(state))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 3
        scores = [i["score"] for i in items]
        assert scores == sorted(scores, reverse=True)
        assert "imminent" in (items[0].get("reason_tags") or [])

    def test_24_resolve_italian(self, sess, state):
        top = sess.get(f"{BASE_URL}/api/decisions/top?limit=1", headers=self._h(state)).json()["items"]
        did = top[0]["id"]
        r = sess.post(f"{BASE_URL}/api/decisions/{did}/resolve", headers=self._h(state), timeout=45)
        assert r.status_code == 200, r.text
        sol = r.json()["solution"]
        assert isinstance(sol, str) and len(sol) > 20

    def test_25_priorities_legacy(self, sess, state):
        r = sess.get(f"{BASE_URL}/api/priorities", headers=self._h(state))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 3
        for it in items:
            assert "reason" in it

    def test_26_memory_ask(self, sess, state):
        r = sess.post(f"{BASE_URL}/api/memory/ask",
                      json={"question": "cosa devo fare?"},
                      headers=self._h(state), timeout=45)
        assert r.status_code == 200, r.text
        assert "answer" in r.json()

    def test_27_auth_errors(self, sess):
        r = sess.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401
        r2 = sess.post(f"{BASE_URL}/api/auth/login",
                       json={"email": "demo@ora.app", "password": "wrong"})
        assert r2.status_code == 401
