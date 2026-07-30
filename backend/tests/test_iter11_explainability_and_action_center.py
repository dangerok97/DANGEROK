"""Iteration 11 — Explainability + Action Center tests."""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
os.environ.setdefault("EXPLAINABILITY_ENABLED", "true")
os.environ.setdefault("ACTION_CENTER_ENABLED", "true")

sys.path.insert(0, "/app/backend")

from explainability.rules import evaluate_rules  # noqa: E402
from explainability.text import (  # noqa: E402
    classify_confidence,
    classify_impact,
    classify_postpone_risk,
    compose_human_summary,
    compose_reasoning_steps,
)
from explainability.types import DECISION_EXPLANATION_VERSION  # noqa: E402
from action_center import (  # noqa: E402
    ALLOWED_TRANSITIONS,
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_DISMISSED,
    STATUS_IN_PROGRESS,
    STATUS_PARTIALLY_COMPLETED,
    STATUS_PENDING,
    STATUS_POSTPONED,
    can_transition,
)

TS = int(time.time())


@pytest.fixture(scope="module")
def client(shared_client):
    return shared_client


@pytest.fixture(scope="module")
def user_a(client):
    r = client.post("/api/auth/register", json={
        "email": f"iter11_a_{TS}@ora.app", "password": "Passw0rd!", "name": "Iter11 A",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    return {"token": body["token"], "user_id": body["user"]["user_id"]}


def h(user):
    return {"Authorization": f"Bearer {user['token']}"}


def _iso_in(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _create_decision(client, user, **fields):
    payload = {"title": "T", "category": "generic"}
    payload.update(fields)
    r = client.post("/api/decisions", headers=h(user), json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# =====================================================================
# A) Pure rules — deterministic
# =====================================================================
class TestA_Rules:
    def test_a1_imminent_event_fires(self):
        d = {"starts_at": _iso_in(3), "urgency": 5}
        rules = evaluate_rules(decision=d)
        assert any(r.id == "imminent_event" for r in rules)

    def test_a2_deadline_soon(self):
        d = {"deadline": _iso_in(24), "urgency": 5}
        rules = evaluate_rules(decision=d)
        assert any(r.id == "deadline_soon" for r in rules)

    def test_a3_quick_win(self):
        rules = evaluate_rules(decision={"time_required_min": 10})
        assert any(r.id == "quick_win" for r in rules)

    def test_a4_travel_dependency_by_category(self):
        rules = evaluate_rules(decision={"category": "travel"})
        assert any(r.id == "travel_dependency" for r in rules)

    def test_a5_travel_dependency_by_linked_node(self):
        rules = evaluate_rules(
            decision={"category": "generic"},
            linked_nodes=[{"type": "event", "label": "Volo Roma-Parigi"}],
        )
        assert any(r.id == "travel_dependency" for r in rules)

    def test_a6_busy_day_from_daily(self):
        daily = {"warnings": ["very_busy_day"], "signals": []}
        rules = evaluate_rules(decision={}, daily=daily)
        assert any(r.id == "busy_day" for r in rules)

    def test_a7_available_time_slot(self):
        daily = {"free_minutes": 180, "signals": [], "warnings": []}
        rules = evaluate_rules(decision={"time_required_min": 15}, daily=daily)
        assert any(r.id == "available_time_slot" for r in rules)

    def test_a8_available_slot_requires_enough_time(self):
        daily = {"free_minutes": 10, "signals": [], "warnings": []}
        rules = evaluate_rules(decision={"time_required_min": 60}, daily=daily)
        assert not any(r.id == "available_time_slot" for r in rules)

    def test_a9_postpone_risk_high_combined(self):
        d = {"starts_at": _iso_in(6), "urgency": 8}
        rules = evaluate_rules(decision=d)
        assert any(r.id == "postpone_risk_high" for r in rules)

    def test_a10_deterministic(self):
        d = {"starts_at": _iso_in(3), "time_required_min": 10, "urgency": 7}
        r1 = evaluate_rules(decision=d)
        r2 = evaluate_rules(decision=d)
        assert [x.id for x in r1] == [x.id for x in r2]


# =====================================================================
# B) Text composition — deterministic
# =====================================================================
class TestB_TextComposition:
    def test_b1_summary_default_when_no_rules(self):
        s = compose_human_summary([])
        assert "consigliata" in s.lower()

    def test_b2_summary_imminent_plus_slot(self):
        rules = evaluate_rules(
            decision={"starts_at": _iso_in(2), "time_required_min": 15},
            daily={"free_minutes": 240, "signals": [], "warnings": []},
        )
        s = compose_human_summary(rules)
        assert "imminente" in s.lower() and "finestra libera" in s.lower()

    def test_b3_no_python_class_names_in_summary(self):
        rules = evaluate_rules(decision={"starts_at": _iso_in(2), "urgency": 9})
        s = compose_human_summary(rules)
        # No CamelCase class names, no double underscore markers
        assert not re.search(r"[A-Z][a-z]+[A-Z]", s)
        assert "__" not in s
        assert "class " not in s.lower()
        assert "python" not in s.lower()

    def test_b4_reasoning_steps_ordered(self):
        rules = evaluate_rules(decision={"starts_at": _iso_in(2), "urgency": 9, "time_required_min": 10})
        steps = compose_reasoning_steps(rules)
        # Each step must be a human string
        for s in steps:
            assert isinstance(s, str) and len(s) > 3

    def test_b5_impact_classifier(self):
        assert classify_impact({"importance": 9, "personal_impact": 8, "economic_impact": 6}) == "high"
        assert classify_impact({"importance": 5, "personal_impact": 5, "economic_impact": 4}) == "medium"
        assert classify_impact({"importance": 1, "personal_impact": 1, "economic_impact": 1}) == "low"

    def test_b6_postpone_risk_classifier(self):
        assert classify_postpone_risk({"urgency": 7}, {"postpone_risk_high"}) == "high"
        assert classify_postpone_risk({"urgency": 7}, {"imminent_event"}) == "medium"
        assert classify_postpone_risk({"urgency": 3}, set()) == "low"

    def test_b7_confidence_classifier(self):
        assert classify_confidence(has_snapshot=True, has_daily=True, rules_count=3) == "high"
        assert classify_confidence(has_snapshot=False, has_daily=True, rules_count=1) == "medium"
        assert classify_confidence(has_snapshot=False, has_daily=False, rules_count=0) == "low"


# =====================================================================
# C) Explanation API
# =====================================================================
class TestC_ExplanationAPI:
    def test_c1_explanation_for_existing_decision(self, client, user_a):
        d = _create_decision(client, user_a,
                             title="Prepara presentazione", starts_at=_iso_in(2),
                             urgency=8, importance=8, time_required_min=10)
        r = client.get(f"/api/decisions/{d['id']}/explanation", headers=h(user_a))
        assert r.status_code == 200
        body = r.json()
        assert body["decision_id"] == d["id"]
        assert body["version"] == DECISION_EXPLANATION_VERSION
        assert body["confidence"] in ("high", "medium", "low")
        assert body["estimated_impact"] in ("high", "medium", "low")
        assert body["estimated_postpone_risk"] in ("high", "medium", "low")
        assert body["human_summary"]
        assert isinstance(body["reasoning_steps"], list)
        assert isinstance(body["applied_rules"], list)
        assert isinstance(body["data_sources"], list)
        # Manual Input must appear for user-created decisions
        assert any(s["source"] == "Manual Input" for s in body["data_sources"])

    def test_c2_explanation_missing_decision_404(self, client, user_a):
        r = client.get("/api/decisions/dec_does_not_exist/explanation", headers=h(user_a))
        assert r.status_code == 404

    def test_c3_explanation_no_leaks(self, client, user_a):
        d = _create_decision(client, user_a, title="Test leak", urgency=9)
        r = client.get(f"/api/decisions/{d['id']}/explanation", headers=h(user_a))
        body_text = r.text
        for banned in ["ExplanationService", "AppliedRule", "traceback", "Traceback",
                       "/app/backend", "openai", "gpt-", "LlmChat"]:
            assert banned not in body_text
        # Data sources only from the safe whitelist
        safe = {"Google Calendar", "Life Graph", "Knowledge Layer", "Daily Intelligence", "Manual Input"}
        for s in r.json()["data_sources"]:
            assert s["source"] in safe

    def test_c4_flag_off_returns_404(self, client, user_a, monkeypatch):
        d = _create_decision(client, user_a, title="Flag off", urgency=5)
        monkeypatch.setenv("EXPLAINABILITY_ENABLED", "false")
        r = client.get(f"/api/decisions/{d['id']}/explanation", headers=h(user_a))
        assert r.status_code == 404
        monkeypatch.setenv("EXPLAINABILITY_ENABLED", "true")

    def test_c5_data_sources_include_life_graph_when_linked(self, client, user_a):
        # Seed a life node then create a decision linked to it
        node = client.post("/api/life-graph/nodes", headers=h(user_a), json={
            "type": "event", "label": "Volo Roma-Milano",
            "attributes": {"starts_at": _iso_in(20), "connector_id": "calendar_google"},
        }).json()
        d = _create_decision(client, user_a, title="Fai check-in", node_ids=[node["id"]])
        body = client.get(f"/api/decisions/{d['id']}/explanation", headers=h(user_a)).json()
        assert any(s["source"] == "Life Graph" for s in body["data_sources"])

    def test_c6_cross_user_isolation(self, client, user_a):
        d = _create_decision(client, user_a, title="Private")
        # different user
        r_reg = client.post("/api/auth/register", json={
            "email": f"iter11_x_{TS}@ora.app", "password": "Passw0rd!", "name": "X",
        }).json()
        r = client.get(f"/api/decisions/{d['id']}/explanation",
                       headers={"Authorization": f"Bearer {r_reg['token']}"})
        assert r.status_code == 404


# =====================================================================
# D) Action Center transitions
# =====================================================================
class TestD_StateMachine:
    def test_d1_allowed_matrix_shape(self):
        # every declared status has a mapping (possibly empty for terminals)
        for s in [STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_PARTIALLY_COMPLETED,
                  STATUS_COMPLETED, STATUS_POSTPONED, STATUS_DISMISSED, STATUS_BLOCKED]:
            assert s in ALLOWED_TRANSITIONS
        assert can_transition(STATUS_PENDING, STATUS_IN_PROGRESS)
        assert not can_transition(STATUS_COMPLETED, STATUS_IN_PROGRESS)
        assert not can_transition(STATUS_DISMISSED, STATUS_IN_PROGRESS)

    def test_d2_start_from_pending(self, client, user_a):
        d = _create_decision(client, user_a, title="Start")
        r = client.post(f"/api/decisions/{d['id']}/start", headers=h(user_a))
        assert r.status_code == 200
        assert r.json()["decision"]["action_state"]["status"] == STATUS_IN_PROGRESS

    def test_d3_partial_with_percentage(self, client, user_a):
        d = _create_decision(client, user_a, title="Partial")
        client.post(f"/api/decisions/{d['id']}/start", headers=h(user_a))
        r = client.post(f"/api/decisions/{d['id']}/partial", headers=h(user_a),
                        json={"completion_percentage": 60, "remaining_minutes": 5, "optional_note": "quasi finito"})
        assert r.status_code == 200
        st = r.json()["decision"]["action_state"]
        assert st["status"] == STATUS_PARTIALLY_COMPLETED
        assert st["completion_percentage"] == 60
        assert st["remaining_minutes"] == 5

    def test_d4_complete_terminal(self, client, user_a):
        d = _create_decision(client, user_a, title="Complete")
        client.post(f"/api/decisions/{d['id']}/complete", headers=h(user_a), json={})
        # Second complete → 409
        r2 = client.post(f"/api/decisions/{d['id']}/complete", headers=h(user_a), json={})
        assert r2.status_code == 409
        assert r2.json()["detail"]["error"] == "invalid_transition"

    def test_d5_postpone_with_until(self, client, user_a):
        d = _create_decision(client, user_a, title="Postpone")
        until = _iso_in(24)
        r = client.post(f"/api/decisions/{d['id']}/postpone", headers=h(user_a),
                        json={"until_datetime": until, "reason": "meeting collision"})
        assert r.status_code == 200
        assert r.json()["decision"]["action_state"]["status"] == STATUS_POSTPONED
        assert r.json()["decision"]["action_state"]["postponed_until"] == until

    def test_d6_block_with_reason(self, client, user_a):
        d = _create_decision(client, user_a, title="Block")
        r = client.post(f"/api/decisions/{d['id']}/blocked", headers=h(user_a),
                        json={"reason": "waiting on Marco"})
        assert r.status_code == 200
        assert r.json()["decision"]["action_state"]["status"] == STATUS_BLOCKED
        assert r.json()["decision"]["action_state"]["blocked_reason"] == "waiting on Marco"

    def test_d7_dismiss_with_reason(self, client, user_a):
        d = _create_decision(client, user_a, title="Dismiss")
        r = client.post(f"/api/decisions/{d['id']}/dismiss", headers=h(user_a),
                        json={"reason": "no longer relevant"})
        assert r.status_code == 200
        assert r.json()["decision"]["action_state"]["status"] == STATUS_DISMISSED

    def test_d8_dismissed_is_terminal(self, client, user_a):
        d = _create_decision(client, user_a, title="Terminal dismiss")
        client.post(f"/api/decisions/{d['id']}/dismiss", headers=h(user_a), json={})
        r = client.post(f"/api/decisions/{d['id']}/start", headers=h(user_a))
        assert r.status_code == 409

    def test_d9_postpone_then_resume(self, client, user_a):
        d = _create_decision(client, user_a, title="Resume")
        client.post(f"/api/decisions/{d['id']}/postpone", headers=h(user_a),
                    json={"until_datetime": _iso_in(2), "reason": "later"})
        r = client.post(f"/api/decisions/{d['id']}/start", headers=h(user_a))
        assert r.status_code == 200
        assert r.json()["decision"]["action_state"]["status"] == STATUS_IN_PROGRESS

    def test_d10_flag_off_disables_new_endpoints(self, client, user_a, monkeypatch):
        d = _create_decision(client, user_a, title="Flag off action")
        monkeypatch.setenv("ACTION_CENTER_ENABLED", "false")
        r = client.post(f"/api/decisions/{d['id']}/start", headers=h(user_a))
        assert r.status_code == 404
        # But existing /dismiss and /complete still work in legacy mode.
        r2 = client.post(f"/api/decisions/{d['id']}/dismiss", headers=h(user_a))
        assert r2.status_code == 200
        monkeypatch.setenv("ACTION_CENTER_ENABLED", "true")


# =====================================================================
# E) History append-only
# =====================================================================
class TestE_History:
    def test_e1_history_records_each_transition(self, client, user_a):
        d = _create_decision(client, user_a, title="History flow")
        client.post(f"/api/decisions/{d['id']}/start", headers=h(user_a))
        client.post(f"/api/decisions/{d['id']}/partial", headers=h(user_a),
                    json={"completion_percentage": 30})
        client.post(f"/api/decisions/{d['id']}/complete", headers=h(user_a), json={})
        r = client.get(f"/api/decisions/{d['id']}/history", headers=h(user_a))
        items = r.json()["items"]
        actions = [i["user_action"] for i in items]
        assert actions == ["start", "partial", "complete"]
        for i in items:
            assert i["immutable"] is True
            assert "timestamp" in i
            assert "old_status" in i and "new_status" in i

    def test_e2_history_isolated_per_user(self, client, user_a):
        d = _create_decision(client, user_a, title="Isolation")
        client.post(f"/api/decisions/{d['id']}/start", headers=h(user_a))
        r2 = client.post("/api/auth/register", json={
            "email": f"iter11_y_{TS}@ora.app", "password": "Passw0rd!", "name": "Y",
        }).json()
        h_other = {"Authorization": f"Bearer {r2['token']}"}
        r = client.get(f"/api/decisions/{d['id']}/history", headers=h_other)
        assert r.status_code == 404


# =====================================================================
# F) Regression / do-not-fire
# =====================================================================
class TestF_NoRegression:
    def test_f1_no_llm_in_module(self):
        # grep the new modules for LLM references
        for path in ("/app/backend/explainability", "/app/backend/action_center"):
            for root, _, files in os.walk(path):
                for fn in files:
                    if not fn.endswith(".py"):
                        continue
                    with open(os.path.join(root, fn)) as f:
                        content = f.read()
                    for banned in ("openai", "emergentintegrations", "LlmChat", "gpt-"):
                        assert banned not in content, f"{banned} found in {fn}"

    def test_f2_action_center_never_creates_new_decisions(self, client, user_a):
        n0 = len(client.get("/api/decisions", headers=h(user_a)).json()["items"])
        d = _create_decision(client, user_a, title="Do not multiply")
        for _ in range(3):
            client.post(f"/api/decisions/{d['id']}/start", headers=h(user_a))
            client.post(f"/api/decisions/{d['id']}/partial", headers=h(user_a),
                        json={"completion_percentage": 50})
            client.post(f"/api/decisions/{d['id']}/postpone", headers=h(user_a),
                        json={"until_datetime": _iso_in(2)})
        n1 = len(client.get("/api/decisions", headers=h(user_a)).json()["items"])
        assert n1 == n0 + 1  # only the one we created

    def test_f3_top_ranking_endpoint_untouched(self, client, user_a):
        # The /top endpoint returns items — we don't assert score order (that's
        # governed by the untouched decision_engine), but that it still returns.
        r = client.get("/api/decisions/top?limit=3", headers=h(user_a))
        assert r.status_code == 200
        assert "items" in r.json()

    def test_f4_context_latest_still_uniform(self, client, user_a):
        d = _create_decision(client, user_a, title="Latest envelope")
        client.post(f"/api/context/decisions/{d['id']}/assemble", headers=h(user_a))
        r = client.get(f"/api/context/decisions/{d['id']}/latest", headers=h(user_a))
        body = r.json()
        assert set(body.keys()) == {"snapshot", "status", "generated_at", "assembler_version"}
