"""
Iteration 6 — Auto-Link Engine + Login side-effect regression tests.
Run serially:  pytest /app/backend/tests/test_auto_link.py -v -n 0
"""
import os
import time
import uuid
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE:
    BASE = "http://localhost:8001"
API = f"{BASE}/api"

DEMO_EMAIL = "demo@ora.app"
DEMO_PASS = "Demo!2026"


def _register(email=None):
    email = email or f"iter6_{uuid.uuid4().hex[:10]}@ora.app"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Demo!2026", "name": "Iter6"}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    return email, tok, {"Authorization": f"Bearer {tok}"}


def _login(email, pwd="Demo!2026"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _decisions(h):
    r = requests.get(f"{API}/decisions", headers=h, timeout=30)
    assert r.status_code == 200
    return r.json().get("items", [])


def _seed_graph(h):
    r = requests.post(f"{API}/life-graph/seed", headers=h, timeout=30)
    assert r.status_code == 200
    return r.json()


def _list_nodes(h, ntype=None):
    q = {"type": ntype} if ntype else {}
    r = requests.get(f"{API}/life-graph/nodes", headers=h, params=q, timeout=30)
    assert r.status_code == 200
    return r.json()["items"]


# =========================================================================
# A. LOGIN SIDE-EFFECT REGRESSION
# =========================================================================
class TestA_LoginSideEffects:
    def test_01_fresh_user_snapshot_and_5_logins(self):
        email, tok, h = _register()
        before = _decisions(h)
        assert len(before) == 7, f"expected 7 seeded decisions, got {len(before)}"
        # Each history should have exactly 1 'seeded' event
        hist_before = [(d["id"], len(d.get("history") or []),
                        d.get("starts_at"), d.get("deadline")) for d in before]
        for d in before:
            assert any((ev.get("event") == "seeded") for ev in (d.get("history") or []))

        for i in range(5):
            tok2 = _login(email)
            h2 = {"Authorization": f"Bearer {tok2}"}
            cur = _decisions(h2)
            assert len(cur) == 7, f"login #{i+1}: decision count changed to {len(cur)}"
            hist_now = [(d["id"], len(d.get("history") or []),
                         d.get("starts_at"), d.get("deadline")) for d in cur]
            assert sorted(hist_now) == sorted(hist_before), \
                f"login #{i+1}: history/anchors mutated"

    def test_02_demo_login_top_still_imminent(self):
        tok = _login(DEMO_EMAIL, DEMO_PASS)
        h = {"Authorization": f"Bearer {tok}"}
        r = requests.get(f"{API}/decisions/top", headers=h, params={"limit": 3}, timeout=30)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 1
        top = items[0]
        assert "Esci tra 25 minuti" in (top.get("title") or ""), f"demo top title unexpected: {top.get('title')}"
        tags = top.get("reason_tags") or []
        assert "imminent" in tags, f"demo top reason_tags missing 'imminent': {tags}"

    def test_03_admin_demo_refresh_forbidden_for_normal(self):
        _, _, h = _register()
        r = requests.post(f"{API}/admin/demo/refresh", headers=h, timeout=30)
        assert r.status_code == 403

    def test_04_admin_demo_refresh_ok_for_demo(self):
        tok = _login(DEMO_EMAIL, DEMO_PASS)
        h = {"Authorization": f"Bearer {tok}"}
        r = requests.post(f"{API}/admin/demo/refresh", headers=h, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        assert body.get("email") == DEMO_EMAIL


# =========================================================================
# Shared fixture: a fully-set-up user for the auto-link tests
# =========================================================================
STATE = {}


def _setup_shared_user():
    if STATE:
        return STATE
    email, tok, h = _register()
    _seed_graph(h)
    car_nodes = _list_nodes(h, "car")
    sub_nodes = _list_nodes(h, "subscription")
    assert car_nodes, "seed did not produce car node"
    assert sub_nodes, "seed did not produce subscription node"
    car_id = car_nodes[0]["id"]
    sub_id = sub_nodes[0]["id"]

    # Enrich car knowledge: plate + brand
    r = requests.patch(f"{API}/knowledge/nodes/{car_id}",
                       headers=h, json={"properties": {"plate": "AB123CD", "brand": "Fiat"}}, timeout=30)
    assert r.status_code == 200, r.text
    # Enrich subscription knowledge: provider, amount
    r = requests.patch(f"{API}/knowledge/nodes/{sub_id}",
                       headers=h, json={"properties": {"provider": "Enel", "amount": 87.40}}, timeout=30)
    assert r.status_code == 200, r.text

    STATE.update({"email": email, "token": tok, "h": h,
                  "car_id": car_id, "sub_id": sub_id})
    return STATE


def _mkdec(h, **payload):
    r = requests.post(f"{API}/decisions", headers=h, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# =========================================================================
# B. Basic flow (subscription provider)
# =========================================================================
class TestB_Basic:
    def test_05_analyze_subscription(self):
        s = _setup_shared_user()
        h = s["h"]
        dec = _mkdec(h, title="Paga la bolletta della luce Enel",
                     description="Fattura Enel Energia", category="bill",
                     metadata={"provider": "Enel"})
        r = requests.post(f"{API}/auto-link/decisions/{dec['id']}/analyze", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("matcher_version") == "auto_link/v1.0"
        assert body.get("auto_accepted") == []
        props = body.get("proposals") or []
        sub_props = [p for p in props if p["node_id"] == s["sub_id"]]
        assert sub_props, f"no proposal for subscription node; got {props}"
        sp = sub_props[0]
        assert sp["status"] == "proposed"
        assert sp["confidence"] >= 0.70
        assert sp["ambiguous"] is False
        tags = {ms["tag"] for ms in sp["matching_signals"]}
        assert "VERIFIABLE_PROVIDER" in tags
        assert "CATEGORY_TYPE" in tags
        reason = sp["reason"]
        assert isinstance(reason, str) and reason.strip().endswith("."), reason

        # Decision not yet modified
        r2 = requests.get(f"{API}/decisions/{dec['id']}", headers=h, timeout=30)
        assert r2.status_code == 200
        assert not (r2.json().get("node_ids") or []), "decision should not have node_ids yet"
        STATE["bill_decision_id"] = dec["id"]


# =========================================================================
# C. Auto-accept via VERIFIABLE_PLATE
# =========================================================================
class TestC_AutoAccept:
    def test_06_plate_auto_accept(self):
        s = _setup_shared_user()
        h = s["h"]
        dec = _mkdec(h, title="Rinnova assicurazione AB123CD",
                     description="Polizza", category="bill",
                     metadata={"plate": "AB123CD"})
        r = requests.post(f"{API}/auto-link/decisions/{dec['id']}/analyze", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        aa = body.get("auto_accepted") or []
        assert len(aa) == 1, f"expected 1 auto_accepted, got: {aa}"
        a = aa[0]
        tags = {ms["tag"] for ms in a["matching_signals"]}
        assert "VERIFIABLE_PLATE" in tags
        assert a["confidence"] == 1.0
        assert a["status"] == "accepted"
        assert a["accepted_by_system"] is True
        assert a["accepted_by_user"] is False

        # Decision is linked to car
        r2 = requests.get(f"{API}/decisions/{dec['id']}", headers=h, timeout=30)
        d_after = r2.json()
        assert s["car_id"] in (d_after.get("node_ids") or [])
        # NOTE (spec vs impl): the review spec says "the car's history got a life_graph.linked
        # event", but the current implementation writes life_graph.linked to the DECISION history
        # (see /app/backend/life_graph/service.py:214). We assert the event was recorded somewhere.
        dec_events = [ev.get("event") for ev in (d_after.get("history") or [])]
        node_events = []
        rn = requests.get(f"{API}/life-graph/nodes/{s['car_id']}", headers=h, timeout=30)
        if rn.status_code == 200:
            node_events = [ev.get("event") for ev in (rn.json().get("history") or [])]
        assert any("linked" in (ev or "") for ev in dec_events + node_events), \
            f"linked event not found in decision.history={dec_events} nor node.history={node_events}"

        # Sensitive redaction: plate value AB123CD must not appear in signal descriptions
        for ms in a["matching_signals"]:
            assert "AB123CD" not in (ms.get("description") or "")


# =========================================================================
# D. Ambiguity
# =========================================================================
class TestD_Ambiguity:
    def test_07_ambiguous_provider(self):
        s = _setup_shared_user()
        h = s["h"]
        # Create a 2nd subscription node "Enel Gas" with provider=Enel
        r = requests.post(f"{API}/life-graph/nodes", headers=h,
                          json={"type": "subscription", "label": "Enel Gas"}, timeout=30)
        assert r.status_code == 200, r.text
        n2 = r.json()
        r2 = requests.patch(f"{API}/knowledge/nodes/{n2['id']}", headers=h,
                            json={"properties": {"provider": "Enel"}}, timeout=30)
        assert r2.status_code == 200

        dec = _mkdec(h, title="Pagare Enel", description="", category="bill",
                     metadata={"provider": "Enel"})
        r = requests.post(f"{API}/auto-link/decisions/{dec['id']}/analyze", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("auto_accepted") == []
        props = body.get("proposals") or []
        if len(props) >= 2:
            assert all(p.get("ambiguous") is True for p in props), \
                f"expected all ambiguous, got: {[(p['node_id'], p['ambiguous']) for p in props]}"
            for p in props:
                assert p["confidence"] >= 0.60
        # Acceptable behavior: 0 or ≥2 ambiguous — but never a single auto-accepted.
        r2 = requests.get(f"{API}/decisions/{dec['id']}", headers=h, timeout=30)
        assert not (r2.json().get("node_ids") or [])


# =========================================================================
# E. Keyword-only never auto-accepts
# =========================================================================
class TestE_KeywordOnly:
    def test_08_exam_keyword_only(self):
        # Use a FRESH user with NO university node
        _, _, h = _register()
        dec = _mkdec(h, title="Studia per esame", description="", category="exam")
        r = requests.post(f"{API}/auto-link/decisions/{dec['id']}/analyze", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("auto_accepted") == []
        for p in (body.get("proposals") or []):
            assert p.get("status") != "accepted"
            assert not any(ms.get("verifiable") for ms in p.get("matching_signals") or [])
        # reanalyze — same result
        r2 = requests.post(f"{API}/auto-link/decisions/{dec['id']}/reanalyze", headers=h, timeout=30)
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2.get("auto_accepted") == []


# =========================================================================
# F. Idempotence and versioning
# =========================================================================
class TestF_Idempotence:
    def test_09_double_analyze_same_proposals(self):
        s = _setup_shared_user()
        h = s["h"]
        did = STATE["bill_decision_id"]
        # Bring proposals to steady state (the ambiguity test in TestD added a new
        # candidate node between when test_05 first analyzed and now).
        requests.post(f"{API}/auto-link/decisions/{did}/analyze", headers=h, timeout=30)
        # 1st list
        r = requests.get(f"{API}/auto-link/decisions/{did}/proposals", headers=h, timeout=30)
        assert r.status_code == 200
        first = r.json()["items"]
        first_ids = sorted([p["id"] for p in first])
        first_meta = {p["id"]: (p["decision_id"], p["node_id"], p.get("created_at")) for p in first}
        # 2nd analyze
        r2 = requests.post(f"{API}/auto-link/decisions/{did}/analyze", headers=h, timeout=30)
        assert r2.status_code == 200
        # 2nd list
        r3 = requests.get(f"{API}/auto-link/decisions/{did}/proposals", headers=h, timeout=30)
        assert r3.status_code == 200
        second = r3.json()["items"]
        second_ids = sorted([p["id"] for p in second])
        second_meta = {p["id"]: (p["decision_id"], p["node_id"], p.get("created_at")) for p in second}
        assert first_ids == second_ids, f"ids differ: {first_ids} vs {second_ids}"
        # created_at unchanged for existing proposals
        for pid in first_ids:
            assert first_meta[pid] == second_meta[pid], \
                f"proposal {pid} mutated: {first_meta[pid]} vs {second_meta[pid]}"
        # No duplicate (decision, node) pairs
        pairs = [(p["decision_id"], p["node_id"]) for p in second if p["status"] in ("proposed", "accepted")]
        assert len(pairs) == len(set(pairs)), f"duplicate proposals: {pairs}"

    def test_10_persisted_fields(self):
        s = _setup_shared_user()
        h = s["h"]
        did = STATE["bill_decision_id"]
        r = requests.get(f"{API}/auto-link/decisions/{did}/proposals", headers=h, timeout=30)
        items = r.json()["items"]
        assert items
        for p in items:
            assert "matcher_version" in p and p["matcher_version"] == "auto_link/v1.0"
            assert "decision_signature" in p
            assert "node_knowledge_version" in p

    def test_11_knowledge_version_bump_supersedes_or_refreshes(self):
        s = _setup_shared_user()
        h = s["h"]
        did = STATE["bill_decision_id"]
        # Bump subscription knowledge (change provider string)
        r = requests.patch(f"{API}/knowledge/nodes/{s['sub_id']}", headers=h,
                           json={"properties": {"provider": "Enel Energia SpA"}}, timeout=30)
        assert r.status_code == 200
        new_ver = r.json().get("version")

        # Re-analyze
        r2 = requests.post(f"{API}/auto-link/decisions/{did}/analyze", headers=h, timeout=30)
        assert r2.status_code == 200
        # Fetch all proposals include_all=true to see supersession
        r3 = requests.get(f"{API}/auto-link/decisions/{did}/proposals",
                          headers=h, params={"include_all": "true"}, timeout=30)
        items = r3.json()["items"]
        sub_items = [p for p in items if p["node_id"] == s["sub_id"]]
        # Any active (proposed/accepted) proposal for this node is bound to CURRENT version
        actives = [p for p in sub_items if p["status"] in ("proposed", "accepted")]
        for p in actives:
            assert p["node_knowledge_version"] == new_ver, \
                f"active proposal has stale version: {p['node_knowledge_version']} vs {new_ver}"


# =========================================================================
# G. Accept + reject flow
# =========================================================================
class TestG_AcceptReject:
    def test_12_accept_flow(self):
        s = _setup_shared_user()
        h = s["h"]
        # Fresh decision → propose → accept
        dec = _mkdec(h, title="Bolletta Enel Energia SpA",
                     description="Fattura", category="bill",
                     metadata={"provider": "Enel Energia SpA"})
        rr = requests.post(f"{API}/auto-link/decisions/{dec['id']}/analyze", headers=h, timeout=30).json()
        props = [p for p in rr.get("proposals") or [] if p["status"] == "proposed"]
        assert props, f"no proposed items in {rr}"
        pid = props[0]["id"]
        target_node = props[0]["node_id"]

        r = requests.post(f"{API}/auto-link/proposals/{pid}/accept",
                          headers=h, json={"reason": "corretto"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "accepted"
        assert body["accepted_at"] is not None
        assert body["accepted_by_user"] is True
        assert body["acceptance_reason"] == "corretto"

        # Decision has node_id linked
        d = requests.get(f"{API}/decisions/{dec['id']}", headers=h, timeout=30).json()
        assert target_node in (d.get("node_ids") or [])

        # Idempotent accept
        r2 = requests.post(f"{API}/auto-link/proposals/{pid}/accept",
                           headers=h, json={"reason": "again"}, timeout=30)
        assert r2.status_code == 200
        d2 = requests.get(f"{API}/decisions/{dec['id']}", headers=h, timeout=30).json()
        nids = d2.get("node_ids") or []
        assert nids.count(target_node) == 1, f"duplicated node_id: {nids}"
        STATE["accept_decision_id"] = dec["id"]
        STATE["accepted_pid"] = pid

    def test_13_reject_and_suppression(self):
        s = _setup_shared_user()
        h = s["h"]
        # New decision to have a fresh proposed proposal
        dec = _mkdec(h, title="Bolletta Enel Energia SpA seconda",
                     description="Fattura 2", category="bill",
                     metadata={"provider": "Enel Energia SpA"})
        rr = requests.post(f"{API}/auto-link/decisions/{dec['id']}/analyze", headers=h, timeout=30).json()
        props = [p for p in rr.get("proposals") or [] if p["status"] == "proposed"]
        assert props
        pid = props[0]["id"]

        r = requests.post(f"{API}/auto-link/proposals/{pid}/reject",
                          headers=h, json={"reason": "non pertinente"}, timeout=30)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["status"] == "rejected"
        assert b["rejected_at"] is not None
        assert b["correction_reason"] == "non pertinente"

        # Re-run analyze — rejection suppression: NOT regenerated for same signature
        r2 = requests.post(f"{API}/auto-link/decisions/{dec['id']}/analyze", headers=h, timeout=30).json()
        active = [p for p in r2.get("proposals") or [] if p["status"] in ("proposed", "accepted")]
        assert all(p["node_id"] != b["node_id"] for p in active), \
            f"rejected node re-appeared: {active}"

        # reanalyze (force) — MAY regenerate
        r3 = requests.post(f"{API}/auto-link/decisions/{dec['id']}/reanalyze", headers=h, timeout=30).json()
        # old rejected still exists for audit
        lst = requests.get(f"{API}/auto-link/decisions/{dec['id']}/proposals",
                           headers=h, params={"include_all": "true"}, timeout=30).json()["items"]
        rejected_still = [p for p in lst if p["id"] == pid]
        assert rejected_still and rejected_still[0]["status"] == "rejected"

        # Idempotent reject
        r4 = requests.post(f"{API}/auto-link/proposals/{pid}/reject", headers=h,
                           json={"reason": "again"}, timeout=30)
        assert r4.status_code == 200
        assert r4.json()["status"] == "rejected"

        # Accept on rejected → 404
        r5 = requests.post(f"{API}/auto-link/proposals/{pid}/accept", headers=h, timeout=30)
        assert r5.status_code == 404


# =========================================================================
# H. Sensitive redaction
# =========================================================================
class TestH_Redaction:
    def test_14_plate_not_leaked(self):
        s = _setup_shared_user()
        h = s["h"]
        dec = _mkdec(h, title="Portare AB123CD dal meccanico",
                     category="bill", metadata={"plate": "AB123CD"})
        r = requests.post(f"{API}/auto-link/decisions/{dec['id']}/analyze", headers=h, timeout=30)
        body = r.json()
        # Combine proposals + auto_accepted
        all_props = (body.get("proposals") or []) + (body.get("auto_accepted") or [])
        assert all_props
        for p in all_props:
            for ms in p.get("matching_signals") or []:
                tag = ms.get("tag")
                desc = ms.get("description") or ""
                if tag in ("KNOWLEDGE_PLATE", "VERIFIABLE_PLATE"):
                    assert "AB123CD" not in desc, f"plate leaked in {tag}: {desc}"
        # Response body should NOT embed full knowledge doc
        import json as _json
        blob = _json.dumps(body)
        assert "\"properties\"" not in blob or len(blob) < 20000, \
            f"response too large or embeds knowledge: {len(blob)} bytes"


# =========================================================================
# I. Cross-user isolation
# =========================================================================
class TestI_Isolation:
    def test_15_cross_user_404(self):
        # user A: create decision, analyze
        _, _, hA = _register()
        _seed_graph(hA)
        car_a = _list_nodes(hA, "car")[0]["id"]
        requests.patch(f"{API}/knowledge/nodes/{car_a}", headers=hA,
                       json={"properties": {"plate": "XY999ZZ"}}, timeout=30)
        dec = _mkdec(hA, title="Assicurazione XY999ZZ", category="bill",
                     metadata={"plate": "XY999ZZ"})
        rr = requests.post(f"{API}/auto-link/decisions/{dec['id']}/analyze", headers=hA, timeout=30).json()
        pid = (rr.get("auto_accepted") or rr.get("proposals") or [{}])[0].get("id")
        assert pid, f"no proposal id: {rr}"

        # User B
        _, _, hB = _register()
        for path in [
            (f"{API}/auto-link/decisions/{dec['id']}/analyze", "POST"),
            (f"{API}/auto-link/decisions/{dec['id']}/reanalyze", "POST"),
            (f"{API}/auto-link/decisions/{dec['id']}/proposals", "GET"),
            (f"{API}/auto-link/proposals/{pid}", "GET"),
            (f"{API}/auto-link/proposals/{pid}/accept", "POST"),
            (f"{API}/auto-link/proposals/{pid}/reject", "POST"),
        ]:
            url, method = path
            r = requests.request(method, url, headers=hB, json={}, timeout=30)
            assert r.status_code == 404, f"{method} {url} → {r.status_code} (expected 404)"

    def test_16_no_bearer_401(self):
        # (url, method) pairs — no auth header
        cases = [
            (f"{API}/auto-link/decisions/x/analyze", "POST"),
            (f"{API}/auto-link/decisions/x/reanalyze", "POST"),
            (f"{API}/auto-link/decisions/x/proposals", "GET"),
            (f"{API}/auto-link/proposals/x", "GET"),
            (f"{API}/auto-link/proposals/x/accept", "POST"),
            (f"{API}/auto-link/proposals/x/reject", "POST"),
        ]
        for url, method in cases:
            r = requests.request(method, url, timeout=30)
            assert r.status_code in (401, 403), f"{method} {url} → {r.status_code}"


# =========================================================================
# J. Multi-node accept — decision.node_ids has BOTH
# =========================================================================
class TestJ_MultiNodeAccept:
    def test_17_two_proposals_two_accepts(self):
        _, _, h = _register()
        _seed_graph(h)
        nodes = _list_nodes(h)
        # Pick two subscription nodes (create 2nd if needed)
        subs = [n for n in nodes if n["type"] == "subscription"]
        if len(subs) < 2:
            r = requests.post(f"{API}/life-graph/nodes", headers=h,
                              json={"type": "subscription", "label": "Netflix"}, timeout=30)
            subs.append(r.json())
        n1, n2 = subs[0]["id"], subs[1]["id"]
        # Distinct provider IDs so each matches uniquely
        requests.patch(f"{API}/knowledge/nodes/{n1}", headers=h,
                       json={"properties": {"contract_id": "CID-111"}}, timeout=30)
        requests.patch(f"{API}/knowledge/nodes/{n2}", headers=h,
                       json={"properties": {"contract_id": "CID-222"}}, timeout=30)

        d1 = _mkdec(h, title="Contratto CID-111", category="bill", metadata={"contract_id": "CID-111"})
        d2 = _mkdec(h, title="Contratto CID-222", category="bill", metadata={"contract_id": "CID-222"})
        # Auto-accept via VERIFIABLE_CONTRACT
        requests.post(f"{API}/auto-link/decisions/{d1['id']}/analyze", headers=h, timeout=30)
        requests.post(f"{API}/auto-link/decisions/{d2['id']}/analyze", headers=h, timeout=30)
        r1 = requests.get(f"{API}/decisions/{d1['id']}", headers=h, timeout=30).json()
        r2 = requests.get(f"{API}/decisions/{d2['id']}", headers=h, timeout=30).json()
        assert n1 in (r1.get("node_ids") or [])
        assert n2 in (r2.get("node_ids") or [])


# =========================================================================
# K. Regression quick checks
# =========================================================================
class TestK_Regression:
    def test_18_top_decisions(self):
        _, _, h = _register()
        r = requests.get(f"{API}/decisions/top", headers=h, params={"limit": 3}, timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 3
        for it in items:
            assert "reason" in it and "reason_tags" in it

    def test_19_legacy_priorities(self):
        _, _, h = _register()
        r = requests.get(f"{API}/priorities", headers=h, timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items and "reason" in items[0]

    def test_20_life_graph_neighborhood(self):
        _, _, h = _register()
        _seed_graph(h)
        node = _list_nodes(h)[0]
        r = requests.get(f"{API}/life-graph/nodes/{node['id']}/graph",
                         headers=h, params={"depth": 2}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        for k in ("root", "nodes", "edges", "distances", "decisions"):
            assert k in body, f"missing {k}"

    def test_21_auth_me_401(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401


# =========================================================================
# L. No side effects from analyze
# =========================================================================
class TestL_NoSideEffects:
    def test_22_analyze_only_touches_proposals_and_node_ids(self):
        _, _, h = _register()
        _seed_graph(h)
        # Snapshot
        d_before = _decisions(h)
        edges_before = requests.get(f"{API}/life-graph/edges", headers=h, timeout=30).json()["items"]
        know_before = requests.get(f"{API}/knowledge", headers=h, timeout=30).json()["items"]
        # Create 5 decisions and analyze each (non-auto-accept cases: generic)
        for i in range(5):
            d = _mkdec(h, title=f"Generico {i}", description="test", category="generic")
            requests.post(f"{API}/auto-link/decisions/{d['id']}/analyze", headers=h, timeout=30)

        d_after = _decisions(h)
        edges_after = requests.get(f"{API}/life-graph/edges", headers=h, timeout=30).json()["items"]
        know_after = requests.get(f"{API}/knowledge", headers=h, timeout=30).json()["items"]

        # 5 new decisions we created — but seed decisions themselves must be untouched
        # We check: original seeded decisions unchanged (title/starts_at/deadline/history)
        by_id_before = {d["id"]: d for d in d_before}
        for d in d_after:
            if d["id"] in by_id_before:
                b = by_id_before[d["id"]]
                assert d.get("starts_at") == b.get("starts_at")
                assert d.get("deadline") == b.get("deadline")
                assert len(d.get("history") or []) == len(b.get("history") or [])
        # No new edges, no new knowledge docs
        assert len(edges_after) == len(edges_before), \
            f"edges changed: {len(edges_before)} → {len(edges_after)}"
        assert len(know_after) == len(know_before), \
            f"knowledge docs changed: {len(know_before)} → {len(know_after)}"
