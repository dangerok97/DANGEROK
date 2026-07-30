"""Iteration 5 — Knowledge Layer hardening tests.

Covers: property envelope + provenance + sensitivity + optimistic concurrency +
rich audit + soft delete/restore + security normalization + single-property atomic
API + cross-user isolation + no-premature-interpretation + demo drift fix +
iteration 1-4 regression.
"""
import os
import time
import json
import pytest
import requests

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', 'https://ora-decision-engine.preview.emergentagent.com').rstrip('/')

TS = int(time.time())
USER_A = {"email": f"iter5_a_{TS}@ora.app", "password": "Demo!2026", "name": "IA"}
USER_B = {"email": f"iter5_b_{TS}@ora.app", "password": "Demo!2026", "name": "IB"}


@pytest.fixture(scope="module")
def state():
    return {}


@pytest.fixture(scope="module")
def sess():
    return requests.Session()


def _register(sess, u):
    r = sess.post(f"{BASE_URL}/api/auth/register", json=u)
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ============================================================
# SETUP: register 2 users + seed Life Graph for user A
# ============================================================
class TestSetup:
    def test_00_register_seed(self, sess, state):
        state["token_a"] = _register(sess, USER_A)
        state["token_b"] = _register(sess, USER_B)
        state["ha"] = {"Authorization": f"Bearer {state['token_a']}"}
        state["hb"] = {"Authorization": f"Bearer {state['token_b']}"}
        # Seed graph for A
        r = sess.post(f"{BASE_URL}/api/life-graph/seed", headers=state["ha"])
        assert r.status_code == 200
        nodes = sess.get(f"{BASE_URL}/api/life-graph/nodes", headers=state["ha"]).json()["items"]
        state["car_id"] = next(n["id"] for n in nodes if n["type"] == "car")
        state["home_id"] = next(n["id"] for n in nodes if n["type"] == "home")
        # Try to get a health node; if missing, create one
        health = next((n for n in nodes if n["type"] == "health"), None)
        if not health:
            r = sess.post(f"{BASE_URL}/api/life-graph/nodes", headers=state["ha"],
                          json={"type": "health", "label": "Health"})
            state["health_id"] = r.json()["id"]
        else:
            state["health_id"] = health["id"]


# ============================================================
# A. Envelope wrapping (bare-value input)
# ============================================================
class TestA_Envelope:
    def test_01_bare_values_wrap(self, sess, state):
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                       json={"properties": {"brand": "Fiat", "plate": "AB123CD", "mileage_km": "48500"}},
                       headers=state["ha"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["version"] == 1, f"version {d.get('version')}"
        p = d["properties"]

        assert p["brand"]["value"] == "Fiat"
        assert p["brand"]["value_type"] == "string"
        assert p["brand"]["sensitivity"] == "public"
        assert p["plate"]["sensitivity"] == "sensitive"
        # mileage coerced to int
        assert p["mileage_km"]["value"] == 48500
        assert isinstance(p["mileage_km"]["value"], int)
        assert p["mileage_km"]["unit"] == "km"
        assert p["mileage_km"]["value_type"] == "number"

        for k in ("brand", "plate", "mileage_km"):
            prov = p[k]["provenance"]
            assert prov["source_type"] == "user_input"
            assert prov["verified_by_user"] is True
            assert prov["confidence"] == 1.0

        assert d.get("updated_at") is not None
        state["v_after_a"] = d["version"]


# ============================================================
# A2. Coercion (boolean strings, string_list wrap)
# ============================================================
class TestA2_Coercion:
    def test_01b_boolean_coercion(self, sess, state):
        # Create a subscription node
        r = sess.post(f"{BASE_URL}/api/life-graph/nodes", headers=state["ha"],
                      json={"type": "subscription", "label": "Netflix"})
        assert r.status_code == 200, r.text
        sub_id = r.json()["id"]
        state["sub_id"] = sub_id
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{sub_id}",
                       json={"properties": {"auto_renew": "true"}},
                       headers=state["ha"])
        assert r.status_code == 200, r.text
        ar = r.json()["properties"]["auto_renew"]
        assert ar["value_type"] == "boolean"
        assert ar["value"] is True, f"expected True, got {ar['value']!r}"

    def test_01c_string_list_wrap(self, sess, state):
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}",
                       json={"properties": {"residents": "Marco"}},
                       headers=state["ha"])
        assert r.status_code == 200, r.text
        res = r.json()["properties"]["residents"]
        assert res["value_type"] == "string_list"
        assert res["value"] == ["Marco"], f"expected ['Marco'], got {res['value']!r}"


# ============================================================
# B. Rich envelope input (AI extraction)
# ============================================================
class TestB_RichEnvelope:
    def test_02_ai_extraction_envelope(self, sess, state):
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                       json={
                           "source_type": "ai_extraction",
                           "actor_type": "ai",
                           "properties": {
                               "road_tax": {
                                   "value": 220,
                                   "unit": "EUR",
                                   "provenance": {
                                       "source_type": "ai_extraction",
                                       "confidence": 0.42,
                                       "verified_by_user": False,
                                       "source_id": "doc_xyz",
                                   }
                               }
                           }
                       }, headers=state["ha"])
        assert r.status_code == 200, r.text
        rt = r.json()["properties"]["road_tax"]
        assert rt["provenance"]["confidence"] == 0.42
        assert rt["provenance"]["verified_by_user"] is False
        assert rt["provenance"]["source_id"] == "doc_xyz"
        assert rt["unit"] == "EUR"

    def test_03_confidence_clamping(self, sess, state):
        # confidence > 1 -> 1
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                       json={"properties": {"model": {"value": "500", "provenance": {"source_type": "ai_extraction", "confidence": 5}}}},
                       headers=state["ha"])
        assert r.status_code == 200
        assert r.json()["properties"]["model"]["provenance"]["confidence"] == 1.0
        # confidence < 0 -> 0
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                       json={"properties": {"model": {"value": "500", "provenance": {"source_type": "ai_extraction", "confidence": -0.3}}}},
                       headers=state["ha"])
        assert r.json()["properties"]["model"]["provenance"]["confidence"] == 0.0

    def test_04_invalid_source_type_falls_back(self, sess, state):
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                       json={"properties": {"owner": {"value": "Marco", "provenance": {"source_type": "banana"}}}},
                       headers=state["ha"])
        assert r.status_code == 200
        assert r.json()["properties"]["owner"]["provenance"]["source_type"] == "user_input"


# ============================================================
# C. Same-value re-declaration
# ============================================================
class TestC_Reconfirm:
    def test_05_reconfirm_preserves_extracted_at(self, sess, state):
        # Get current brand envelope
        r = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}", headers=state["ha"])
        before = r.json()["properties"]["brand"]["provenance"]
        time.sleep(1.1)
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                       json={"properties": {"brand": "Fiat"}}, headers=state["ha"])
        after = r.json()["properties"]["brand"]["provenance"]
        assert after["extracted_at"] == before["extracted_at"], (before, after)
        # last_confirmed_at should be >= before's
        assert (after.get("last_confirmed_at") or "") >= (before.get("last_confirmed_at") or "")


# ============================================================
# D. History / audit
# ============================================================
class TestD_History:
    def test_06_history_entries_shape(self, sess, state):
        r = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}/history?limit=100", headers=state["ha"])
        assert r.status_code == 200
        events = r.json()["items"]
        assert len(events) > 0
        required = {"at", "event", "property", "previous", "next", "actor_type", "actor_id", "source_type"}
        for e in events:
            missing = required - set(e.keys())
            assert not missing, f"missing {missing} in {e}"

    def test_07_history_ai_actor(self, sess, state):
        events = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}/history?limit=200",
                          headers=state["ha"]).json()["items"]
        ai_events = [e for e in events if e.get("source_type") == "ai_extraction"]
        assert ai_events, "no ai_extraction events"
        assert any(e.get("actor_type") == "ai" for e in ai_events)

    def test_08_sensitive_redacted_in_history(self, sess, state):
        events = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}/history?limit=200",
                          headers=state["ha"]).json()["items"]
        plate_events = [e for e in events if e.get("property") == "plate"]
        assert plate_events, "no plate events"
        for e in plate_events:
            for k in ("previous", "next"):
                v = e.get(k)
                if v is None:
                    continue
                # Must NOT contain raw plate string
                assert "AB123CD" not in json.dumps(v), f"raw plate leaked: {e}"
                # Should be shape {redacted: true, value_type: ...}
                if isinstance(v, dict):
                    assert v.get("redacted") is True

    def test_09_highly_sensitive_health(self, sess, state):
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['health_id']}",
                       json={"properties": {"medications": ["aspirin", "vitaminD"]}},
                       headers=state["ha"])
        assert r.status_code == 200, r.text
        events = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['health_id']}/history?limit=50",
                          headers=state["ha"]).json()["items"]
        med_events = [e for e in events if e.get("property") == "medications"]
        assert med_events
        for e in med_events:
            body = json.dumps(e)
            assert "aspirin" not in body and "vitaminD" not in body


# ============================================================
# E. Optimistic concurrency
# ============================================================
class TestE_Concurrency:
    def test_10_expected_version_conflict(self, sess, state):
        cur = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}", headers=state["ha"]).json()
        v = cur["version"]
        r1 = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                        json={"expected_version": v, "properties": {"purchase_date": "2020-05-01"}},
                        headers=state["ha"])
        assert r1.status_code == 200, r1.text
        # Second one w/ same expected → conflict
        r2 = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                        json={"expected_version": v, "properties": {"purchase_date": "2021-06-01"}},
                        headers=state["ha"])
        assert r2.status_code == 409, r2.text
        detail = r2.json().get("detail")
        assert isinstance(detail, dict)
        assert detail.get("error") == "version_conflict"
        assert detail.get("expected") == v
        assert detail.get("current") == v + 1

    def test_11_unconditional_write_ok(self, sess, state):
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                       json={"properties": {"purchase_date": "2022-01-01"}}, headers=state["ha"])
        assert r.status_code == 200

    def test_12_put_property_honors_version(self, sess, state):
        cur = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}", headers=state["ha"]).json()
        v = cur["version"]
        r = sess.put(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}/properties/brand",
                     json={"value": "Fiat", "expected_version": v + 999},
                     headers=state["ha"])
        assert r.status_code == 409, r.text


# ============================================================
# F. Security & normalization (all should return 400)
# ============================================================
class TestF_Security:
    @pytest.mark.parametrize("props", [
        {"$where": "x"},
        {"foo.bar": "x"},
        {"__proto__": "x"},
        {"constructor": "x"},
        {"prototype": "x"},
        {"k" * 65: "x"},              # too long
        {"good": "y" * 10_001},       # value too long
        {"road_tax": {"$ne": 1}},     # nested $
        {"road_tax": {"foo.bar": 1}}, # nested with .
    ])
    def test_13_reject_bad_keys(self, sess, state, props):
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                       json={"properties": props}, headers=state["ha"])
        assert r.status_code == 400, f"expected 400 for {list(props.keys())}, got {r.status_code}: {r.text[:200]}"

    def test_14_nan_inf(self, sess, state):
        # JSON spec disallows NaN, but python `requests` with allow_nan=True (default)
        # will send it. Server must reject without 500.
        try:
            body = json.dumps({"properties": {"gpa": float("nan")}}, allow_nan=True)
        except Exception:
            pytest.skip("cannot serialize NaN")
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                       data=body,
                       headers={**state["ha"], "Content-Type": "application/json"})
        assert r.status_code in (400, 422), f"NaN got {r.status_code}: {r.text[:200]}"

    def test_15_key_normalization(self, sess, state):
        # "Mileage KM" -> either 400 or normalized to mileage_km
        r = sess.patch(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}",
                       json={"properties": {"Mileage KM": 12345}}, headers=state["ha"])
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            got = r.json()["properties"]
            assert "mileage_km" in got, f"expected normalized 'mileage_km', got keys: {list(got.keys())}"


# ============================================================
# G. Soft delete + restore
# ============================================================
class TestG_SoftDelete:
    def test_16_delete_soft(self, sess, state):
        r = sess.delete(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}?reason=cleanup",
                        headers=state["ha"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("status") == "archived"
        assert d.get("archived_at") is not None
        assert d.get("archive_reason") == "cleanup"

    def test_17_default_get_hides(self, sess, state):
        r = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}", headers=state["ha"])
        assert r.status_code == 200
        d = r.json()
        assert d["properties"] == {}
        assert d["version"] == 0

    def test_18_include_archived_shows(self, sess, state):
        r = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}?include_archived=true",
                     headers=state["ha"])
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") == "archived"
        assert "brand" in d["properties"]

    def test_19_restore(self, sess, state):
        r = sess.post(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}/restore",
                      json={"reason": "oops"}, headers=state["ha"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("status") == "active"
        assert d.get("archived_at") in (None, "")
        assert "brand" in d["properties"]
        events = [e["event"] for e in sess.get(
            f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}/history?limit=200",
            headers=state["ha"]).json()["items"]]
        assert "restored" in events

    def test_20_list_hides_archived(self, sess, state):
        # Archive again to test list filtering
        sess.delete(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}?reason=temp", headers=state["ha"])
        r = sess.get(f"{BASE_URL}/api/knowledge", headers=state["ha"])
        items = r.json()["items"]
        ids = {i["node_id"] for i in items}
        assert state["car_id"] not in ids
        # With include_archived=true
        r = sess.get(f"{BASE_URL}/api/knowledge?include_archived=true", headers=state["ha"])
        ids = {i["node_id"] for i in r.json()["items"]}
        assert state["car_id"] in ids
        # Restore for later tests
        sess.post(f"{BASE_URL}/api/knowledge/nodes/{state['car_id']}/restore", headers=state["ha"])


# ============================================================
# H. Single-property atomic API
# ============================================================
class TestH_SingleProperty:
    def test_21_put_property(self, sess, state):
        r = sess.put(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}/properties/address",
                     json={"value": "Via Milano 1", "source_type": "user_input"},
                     headers=state["ha"])
        assert r.status_code == 200, r.text
        d = r.json()
        addr = d["properties"]["address"]
        assert addr["value"] == "Via Milano 1"
        assert addr["sensitivity"] == "sensitive"

    def test_22_get_property(self, sess, state):
        r = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}/properties/address",
                     headers=state["ha"])
        assert r.status_code == 200
        d = r.json()
        assert d["key"] == "address"
        assert d["value"] == "Via Milano 1"
        assert d["envelope"] is not None
        assert d["envelope"]["sensitivity"] == "sensitive"

    def test_23_get_nonexistent_key(self, sess, state):
        r = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}/properties/nonexistent_key",
                     headers=state["ha"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["envelope"] is None
        assert d["value"] is None

    def test_24_delete_property_then_get(self, sess, state):
        pre = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}", headers=state["ha"]).json()
        v_pre = pre["version"]
        r = sess.delete(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}/properties/address",
                        headers=state["ha"])
        assert r.status_code == 200
        d = r.json()
        assert d["version"] > v_pre
        r2 = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}/properties/address",
                      headers=state["ha"])
        assert r2.json()["envelope"] is None

    def test_25_bad_key_400(self, sess, state):
        for k in ["$foo", "a.b", "__proto__"]:
            r = sess.get(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}/properties/{k}",
                         headers=state["ha"])
            assert r.status_code == 400, f"GET {k}: {r.status_code}"
            r = sess.put(f"{BASE_URL}/api/knowledge/nodes/{state['home_id']}/properties/{k}",
                         json={"value": "x"}, headers=state["ha"])
            assert r.status_code == 400, f"PUT {k}: {r.status_code}"


# ============================================================
# I. Isolation & auth
# ============================================================
class TestI_Isolation:
    def test_26_cross_user_404(self, sess, state):
        h = state["hb"]
        cid = state["car_id"]
        for method, url, body in [
            ("get", f"{BASE_URL}/api/knowledge/nodes/{cid}", None),
            ("patch", f"{BASE_URL}/api/knowledge/nodes/{cid}", {"properties": {"x": 1}}),
            ("put", f"{BASE_URL}/api/knowledge/nodes/{cid}", {"properties": {"x": 1}}),
            ("delete", f"{BASE_URL}/api/knowledge/nodes/{cid}", None),
            ("post", f"{BASE_URL}/api/knowledge/nodes/{cid}/restore", {}),
            ("get", f"{BASE_URL}/api/knowledge/nodes/{cid}/history", None),
            ("get", f"{BASE_URL}/api/knowledge/nodes/{cid}/properties/brand", None),
            ("put", f"{BASE_URL}/api/knowledge/nodes/{cid}/properties/brand", {"value": "Foo"}),
            ("delete", f"{BASE_URL}/api/knowledge/nodes/{cid}/properties/brand", None),
        ]:
            r = sess.request(method, url, headers=h, json=body)
            assert r.status_code == 404, f"{method} {url} -> {r.status_code}"

    def test_27_no_bearer_401(self, sess, state):
        cid = state["car_id"]
        for method, url in [
            ("get", f"{BASE_URL}/api/knowledge/nodes/{cid}"),
            ("patch", f"{BASE_URL}/api/knowledge/nodes/{cid}"),
            ("put", f"{BASE_URL}/api/knowledge/nodes/{cid}"),
            ("delete", f"{BASE_URL}/api/knowledge/nodes/{cid}"),
            ("get", f"{BASE_URL}/api/knowledge/nodes/{cid}/history"),
            ("get", f"{BASE_URL}/api/knowledge/nodes/{cid}/properties/brand"),
            ("get", f"{BASE_URL}/api/knowledge"),
        ]:
            r = sess.request(method, url, json={"properties": {}})
            assert r.status_code == 401, f"{method} {url} -> {r.status_code}"


# ============================================================
# J. No premature interpretation
# ============================================================
class TestJ_NoInterpretation:
    def test_28_no_side_effects(self, sess, state):
        # Snapshot before
        decs_before = sess.get(f"{BASE_URL}/api/decisions", headers=state["ha"]).json()["items"]
        edges_before = sess.get(f"{BASE_URL}/api/life-graph/edges", headers=state["ha"]).json()["items"]
        # Knowledge session: several writes on car
        cid = state["car_id"]
        sess.patch(f"{BASE_URL}/api/knowledge/nodes/{cid}",
                   json={"properties": {"model": "500L"}}, headers=state["ha"])
        sess.put(f"{BASE_URL}/api/knowledge/nodes/{cid}/properties/mot",
                 json={"value": {"expires_at": "2027-01-01"}}, headers=state["ha"])
        sess.patch(f"{BASE_URL}/api/knowledge/nodes/{cid}",
                   json={"properties": {"tires": {"size": "205/55R16"}}}, headers=state["ha"])
        sess.delete(f"{BASE_URL}/api/knowledge/nodes/{cid}/properties/model", headers=state["ha"])
        # Snapshot after
        decs_after = sess.get(f"{BASE_URL}/api/decisions", headers=state["ha"]).json()["items"]
        edges_after = sess.get(f"{BASE_URL}/api/life-graph/edges", headers=state["ha"]).json()["items"]
        assert len(decs_before) == len(decs_after), f"decisions changed: {len(decs_before)}->{len(decs_after)}"
        assert len(edges_before) == len(edges_after), f"edges changed: {len(edges_before)}->{len(edges_after)}"


# ============================================================
# K. Regression (iterations 1-4)
# ============================================================
class TestK_Regression:
    def test_29_top_decisions(self, sess, state):
        r = sess.get(f"{BASE_URL}/api/decisions/top?limit=3", headers=state["ha"])
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 3
        for it in items:
            assert it.get("reason_tags") is not None

    def test_30_resolve_italian(self, sess, state):
        top = sess.get(f"{BASE_URL}/api/decisions/top?limit=1", headers=state["ha"]).json()["items"]
        r = sess.post(f"{BASE_URL}/api/decisions/{top[0]['id']}/resolve",
                      headers=state["ha"], timeout=60)
        assert r.status_code == 200, r.text
        assert len(r.json()["solution"]) > 20

    def test_31_node_graph(self, sess, state):
        r = sess.get(f"{BASE_URL}/api/life-graph/nodes/{state['home_id']}/graph?depth=2",
                     headers=state["ha"])
        assert r.status_code == 200
        d = r.json()
        for k in ("nodes", "edges", "decisions"):
            assert k in d

    def test_32_priorities_legacy(self, sess, state):
        r = sess.get(f"{BASE_URL}/api/priorities", headers=state["ha"])
        assert r.status_code == 200
        assert len(r.json()["items"]) == 3

    def test_33_memory_ask(self, sess, state):
        r = sess.post(f"{BASE_URL}/api/memory/ask",
                      json={"question": "cosa devo fare?"},
                      headers=state["ha"], timeout=60)
        assert r.status_code == 200
        assert "answer" in r.json()

    def test_34_me_no_token(self, sess):
        r = sess.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401


# ============================================================
# L. Demo user drift fix
# ============================================================
class TestL_DemoDrift:
    def test_35_demo_login_imminent_top1(self, sess, state):
        r = sess.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "demo@ora.app", "password": "Demo!2026"})
        assert r.status_code == 200, r.text
        state["token_demo"] = r.json()["token"]
        hd = {"Authorization": f"Bearer {state['token_demo']}"}
        top = sess.get(f"{BASE_URL}/api/decisions/top?limit=3", headers=hd).json()["items"]
        assert len(top) == 3
        first = top[0]
        assert "imminent" in (first.get("reason_tags") or []), \
            f"top1 reason_tags={first.get('reason_tags')}, title={first.get('title')}"
        assert "Esci tra 25 minuti" in (first.get("title") or "")

    def test_36_repeated_login_stable(self, sess, state):
        # login twice more, ensure decision count doesn't grow
        hd = {"Authorization": f"Bearer {state['token_demo']}"}
        count_before = len(sess.get(f"{BASE_URL}/api/decisions", headers=hd).json()["items"])
        for _ in range(2):
            r = sess.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "demo@ora.app", "password": "Demo!2026"})
            assert r.status_code == 200
        count_after = len(sess.get(f"{BASE_URL}/api/decisions", headers=hd).json()["items"])
        assert count_before == count_after, f"decisions grew: {count_before}->{count_after}"
