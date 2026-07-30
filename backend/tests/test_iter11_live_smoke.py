"""
Iter11 live smoke — hits the preview URL and validates spec §3, §5, §6, §7.
Deterministic, no LLM.
"""
import os
import re
import time
import uuid
import requests
import pytest

BASE_URL = "https://ora-decision-engine.preview.emergentagent.com"
DEMO_EMAIL = "demo@ora.app"
DEMO_PASSWORD = "Demo!2026"

ALLOWED_SOURCES = {"Google Calendar", "Life Graph", "Knowledge Layer",
                   "Daily Intelligence", "Manual Input"}
LEAK_TOKENS = ["ExplanationService", "AppliedRule", "Traceback",
               "/app/backend", "openai", "gpt-", "LlmChat",
               "emergentintegrations"]


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password},
                      timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    return body.get("token") or body.get("access_token")


def _headers(token):
    return {"Authorization": f"Bearer {token}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def demo_token():
    return _login(DEMO_EMAIL, DEMO_PASSWORD)


@pytest.fixture(scope="module")
def demo_decision_id(demo_token):
    """Pick a decision from /api/priorities that is NOT in a terminal state."""
    r = requests.get(f"{BASE_URL}/api/priorities", headers=_headers(demo_token), timeout=20)
    assert r.status_code == 200, r.text
    items = r.json().get("items") or r.json().get("priorities") or r.json()
    assert isinstance(items, list) and len(items) > 0
    # try to find a non-terminal one; fallback to first
    for it in items:
        st = (it.get("action_state") or {}).get("status")
        if st not in ("completed", "dismissed"):
            return it["id"]
    return items[0]["id"]


class TestLiveExplanation:
    def test_a_get_explanation_envelope(self, demo_token, demo_decision_id):
        r = requests.get(f"{BASE_URL}/api/decisions/{demo_decision_id}/explanation",
                         headers=_headers(demo_token), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ["decision_id", "priority_score", "confidence",
                  "estimated_duration_minutes", "estimated_impact",
                  "estimated_postpone_risk", "generated_at", "human_summary",
                  "reasoning_steps", "data_sources", "applied_rules",
                  "context_used", "version"]:
            assert k in body, f"missing key: {k}"
        assert body["version"] == "explainability/v1.0"
        assert body["decision_id"] == demo_decision_id

    def test_b_data_sources_whitelist_only(self, demo_token, demo_decision_id):
        r = requests.get(f"{BASE_URL}/api/decisions/{demo_decision_id}/explanation",
                         headers=_headers(demo_token), timeout=20)
        assert r.status_code == 200
        for ds in r.json()["data_sources"]:
            assert ds["source"] in ALLOWED_SOURCES, f"illegal source: {ds['source']}"

    def test_c_no_leaks_in_body(self, demo_token, demo_decision_id):
        r = requests.get(f"{BASE_URL}/api/decisions/{demo_decision_id}/explanation",
                         headers=_headers(demo_token), timeout=20)
        raw = r.text
        for tok in LEAK_TOKENS:
            assert tok not in raw, f"leak token in body: {tok}"

    def test_d_human_summary_no_class_names(self, demo_token, demo_decision_id):
        r = requests.get(f"{BASE_URL}/api/decisions/{demo_decision_id}/explanation",
                         headers=_headers(demo_token), timeout=20)
        summary = r.json()["human_summary"]
        assert not re.search(r"[A-Z][a-z]+[A-Z]", summary), \
            f"class-like name in summary: {summary!r}"

    def test_e_new_manual_decision_includes_manual_input(self, demo_token):
        payload = {
            "title": f"TEST_iter11_manual_{uuid.uuid4().hex[:6]}",
            "description": "manual seed for iter11 live smoke",
            "category": "personal",
            "estimated_duration_minutes": 30,
        }
        r = requests.post(f"{BASE_URL}/api/decisions",
                          headers=_headers(demo_token),
                          json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        dec = r.json()
        dec_id = dec.get("id") or dec.get("decision_id")
        assert dec_id

        r2 = requests.get(f"{BASE_URL}/api/decisions/{dec_id}/explanation",
                          headers=_headers(demo_token), timeout=20)
        assert r2.status_code == 200, r2.text
        sources = [ds["source"] for ds in r2.json()["data_sources"]]
        assert "Manual Input" in sources, f"expected Manual Input in {sources}"


class TestLiveActionCenter:
    def test_a_start_partial_complete_history(self, demo_token):
        # create a fresh decision so we have a clean slate
        payload = {
            "title": f"TEST_iter11_flow_{uuid.uuid4().hex[:6]}",
            "description": "start->partial->complete flow",
            "category": "personal",
            "estimated_duration_minutes": 45,
        }
        r = requests.post(f"{BASE_URL}/api/decisions",
                          headers=_headers(demo_token),
                          json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        dec_id = r.json().get("id") or r.json().get("decision_id")

        r1 = requests.post(f"{BASE_URL}/api/decisions/{dec_id}/start",
                           headers=_headers(demo_token), json={}, timeout=20)
        assert r1.status_code == 200, r1.text

        r2 = requests.post(f"{BASE_URL}/api/decisions/{dec_id}/partial",
                           headers=_headers(demo_token),
                           json={"completion_percentage": 50, "remaining_minutes": 20},
                           timeout=20)
        assert r2.status_code == 200, r2.text

        r3 = requests.post(f"{BASE_URL}/api/decisions/{dec_id}/complete",
                           headers=_headers(demo_token),
                           json={"note": "done via live smoke"},
                           timeout=20)
        assert r3.status_code == 200, r3.text

        hist = requests.get(f"{BASE_URL}/api/decisions/{dec_id}/history",
                            headers=_headers(demo_token), timeout=20)
        assert hist.status_code == 200, hist.text
        rows = hist.json()
        if isinstance(rows, dict):
            rows = rows.get("items") or rows.get("history") or []
        assert len(rows) == 3, f"expected 3 rows, got {len(rows)}: {rows}"
        # extract action string per row (tolerant of key naming)
        def action_of(row):
            return (row.get("user_action") or row.get("action") or row.get("event")
                    or row.get("transition") or row.get("new_status"))
        actions = [action_of(r) for r in rows]
        assert all(row.get("immutable") is True for row in rows), \
            f"immutable not True on all rows: {rows}"
        # accept either sequential to_status semantics
        seq = " ".join(str(a) for a in actions).lower()
        for token in ["start", "partial", "complete"]:
            assert token in seq, f"missing {token} in ordered actions: {actions}"

    def test_b_complete_on_completed_is_409(self, demo_token):
        payload = {"title": f"TEST_iter11_dbl_complete_{uuid.uuid4().hex[:6]}",
                   "category": "personal", "estimated_duration_minutes": 15}
        r = requests.post(f"{BASE_URL}/api/decisions",
                          headers=_headers(demo_token), json=payload, timeout=20)
        dec_id = r.json().get("id") or r.json().get("decision_id")
        c1 = requests.post(f"{BASE_URL}/api/decisions/{dec_id}/complete",
                           headers=_headers(demo_token), json={}, timeout=20)
        assert c1.status_code == 200, c1.text
        c2 = requests.post(f"{BASE_URL}/api/decisions/{dec_id}/complete",
                           headers=_headers(demo_token), json={}, timeout=20)
        assert c2.status_code == 409, f"expected 409, got {c2.status_code}: {c2.text}"
        detail = c2.json().get("detail") or {}
        # detail may be dict or str depending on FastAPI serialization
        if isinstance(detail, dict):
            assert detail.get("error") == "invalid_transition", detail
        else:
            assert "invalid_transition" in str(detail).lower(), detail

    def test_c_postpone_missing_body_422(self, demo_token):
        payload = {"title": f"TEST_iter11_postpone_{uuid.uuid4().hex[:6]}",
                   "category": "personal", "estimated_duration_minutes": 20}
        r = requests.post(f"{BASE_URL}/api/decisions",
                          headers=_headers(demo_token), json=payload, timeout=20)
        dec_id = r.json().get("id") or r.json().get("decision_id")

        bad = requests.post(f"{BASE_URL}/api/decisions/{dec_id}/postpone",
                            headers=_headers(demo_token), json={}, timeout=20)
        assert bad.status_code == 422, f"expected 422 missing until_datetime, got {bad.status_code}: {bad.text}"

        from datetime import datetime, timedelta, timezone
        future_iso = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        ok = requests.post(f"{BASE_URL}/api/decisions/{dec_id}/postpone",
                           headers=_headers(demo_token),
                           json={"until_datetime": future_iso, "reason": "smoke"},
                           timeout=20)
        assert ok.status_code == 200, ok.text
        body = ok.json()
        # verify status is postponed and until echoed
        raw = str(body)
        assert "postponed" in raw.lower()
        # look inside possible nested action_state
        found_until = False
        def _find(obj):
            nonlocal found_until
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if "postpone" in k.lower() and v:
                        found_until = True
                    _find(v)
            elif isinstance(obj, list):
                for x in obj:
                    _find(x)
        _find(body)
        assert found_until, f"postponed_until not echoed in body: {body}"

    def test_d_blocked_missing_reason_422(self, demo_token):
        payload = {"title": f"TEST_iter11_blocked_{uuid.uuid4().hex[:6]}",
                   "category": "personal", "estimated_duration_minutes": 20}
        r = requests.post(f"{BASE_URL}/api/decisions",
                          headers=_headers(demo_token), json=payload, timeout=20)
        dec_id = r.json().get("id") or r.json().get("decision_id")

        bad = requests.post(f"{BASE_URL}/api/decisions/{dec_id}/blocked",
                            headers=_headers(demo_token), json={}, timeout=20)
        assert bad.status_code == 422, f"expected 422 missing reason, got {bad.status_code}: {bad.text}"

        ok = requests.post(f"{BASE_URL}/api/decisions/{dec_id}/blocked",
                           headers=_headers(demo_token),
                           json={"reason": "external dependency"},
                           timeout=20)
        assert ok.status_code == 200, ok.text
        # blocked_reason set
        raw = str(ok.json())
        assert "external dependency" in raw, f"blocked_reason not echoed: {raw}"

    def test_e_dismiss_backward_compat(self, demo_token):
        # (i) empty body still works
        p1 = {"title": f"TEST_iter11_dismiss_empty_{uuid.uuid4().hex[:6]}",
              "category": "personal", "estimated_duration_minutes": 10}
        r1 = requests.post(f"{BASE_URL}/api/decisions",
                           headers=_headers(demo_token), json=p1, timeout=20)
        did1 = r1.json().get("id") or r1.json().get("decision_id")
        e1 = requests.post(f"{BASE_URL}/api/decisions/{did1}/dismiss",
                           headers=_headers(demo_token), json={}, timeout=20)
        assert e1.status_code == 200, e1.text

        # (ii) with reason
        p2 = {"title": f"TEST_iter11_dismiss_reason_{uuid.uuid4().hex[:6]}",
              "category": "personal", "estimated_duration_minutes": 10}
        r2 = requests.post(f"{BASE_URL}/api/decisions",
                           headers=_headers(demo_token), json=p2, timeout=20)
        did2 = r2.json().get("id") or r2.json().get("decision_id")
        e2 = requests.post(f"{BASE_URL}/api/decisions/{did2}/dismiss",
                           headers=_headers(demo_token),
                           json={"reason": "no longer relevant"}, timeout=20)
        assert e2.status_code == 200, e2.text


class TestLiveIsolation:
    def test_cross_user_returns_404(self, demo_token, demo_decision_id):
        # create ephemeral second user
        uniq = uuid.uuid4().hex[:8]
        email = f"iter11_live_{uniq}@ora.app"
        password = "Iter11!2026"
        reg = requests.post(f"{BASE_URL}/api/auth/register",
                            json={"email": email, "password": password,
                                  "name": f"iter11_{uniq}"},
                            timeout=20)
        assert reg.status_code in (200, 201), reg.text
        # login
        tok2 = _login(email, password)
        # try to access user A's explanation
        r_expl = requests.get(f"{BASE_URL}/api/decisions/{demo_decision_id}/explanation",
                              headers=_headers(tok2), timeout=20)
        assert r_expl.status_code == 404, \
            f"cross-user explanation should be 404, got {r_expl.status_code}"
        r_hist = requests.get(f"{BASE_URL}/api/decisions/{demo_decision_id}/history",
                              headers=_headers(tok2), timeout=20)
        assert r_hist.status_code == 404, \
            f"cross-user history should be 404, got {r_hist.status_code}"


class TestLiveInvariants:
    def test_top_endpoint_still_works(self, demo_token):
        r = requests.get(f"{BASE_URL}/api/decisions/top?limit=3",
                         headers=_headers(demo_token), timeout=20)
        assert r.status_code == 200, r.text
        assert "items" in r.json(), r.json()

    def test_no_notification_events_in_audit(self, demo_token):
        # try common audit paths — tolerate 404 if endpoint is admin-only
        for path in ["/api/permission-audit", "/api/permissions/audit",
                     "/api/audit/permissions"]:
            r = requests.get(f"{BASE_URL}{path}",
                             headers=_headers(demo_token), timeout=20)
            if r.status_code == 200:
                events = r.json()
                if isinstance(events, dict):
                    events = events.get("items") or events.get("events") or []
                for ev in events:
                    et = ev.get("event_type", "") if isinstance(ev, dict) else ""
                    assert not et.startswith("notification."), \
                        f"forbidden notification.* audit event: {et}"
                return
        pytest.skip("no accessible permission_audit endpoint from demo user")
