"""Iteration 10 — Daily Intelligence Layer tests.

Two-layer strategy:
  1. Pure `analyzer` unit tests: feed hand-crafted event lists, assert
     signals/warnings/opportunities/scores are deterministic.
  2. API integration tests via TestClient: seed events into life_nodes
     (type=event) and hit /api/daily/*.

Everything is deterministic. No LLM. No side effects.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

os.environ["CALENDAR_PROVIDER_MODE"] = "fake"

sys.path.insert(0, "/app/backend")

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from daily_intelligence.analyzer import analyze_day  # noqa: E402
from daily_intelligence.types import DAILY_SUMMARY_VERSION  # noqa: E402

TS = int(time.time())


def _dt(hour: int, minute: int = 0, day_offset: int = 0) -> datetime:
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(days=day_offset, hours=hour, minutes=minute)


def _iso(d: datetime) -> str:
    return d.isoformat().replace("+00:00", "Z")


def _event(id_: str, title: str, start_h: int, end_h: int, *, all_day: bool = False, status: str = "confirmed"):
    return {
        "id": id_, "title": title,
        "starts_at": _dt(start_h), "ends_at": _dt(end_h),
        "all_day": all_day, "status": status, "source": "calendar_google",
    }


@pytest.fixture(scope="module")
def client(shared_client):
    return shared_client


@pytest.fixture(scope="module")
def user_a(client):
    r = client.post("/api/auth/register", json={
        "email": f"iter10_a_{TS}@ora.app", "password": "Passw0rd!", "name": "Iter10 A",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    return {"token": body["token"], "user_id": body["user"]["user_id"]}


def h(user):
    return {"Authorization": f"Bearer {user['token']}"}


# ============================================================
# 1) Pure analyzer unit tests — no I/O
# ============================================================
class TestA_AnalyzerPure:
    def test_a1_empty_day(self):
        d = analyze_day(target_date=date.today(), events=[])
        assert d.total_events == 0
        assert d.busy_minutes == 0
        assert "empty_day" in d.signals
        assert d.confidence in ("low", "medium")
        assert d.energy_estimation["level"] in ("high", "medium", "low")
        assert d.score >= 80  # empty ≠ bad
        assert d.version == DAILY_SUMMARY_VERSION

    def test_a2_full_day_stressful(self):
        # 5 back-to-back meetings (7h total) + 3h travel
        evs = [
            _event("e1", "Standup", 8, 10),
            _event("e2", "Meeting Design", 10, 11),
            _event("e3", "1:1 con Marco", 11, 12),
            _event("e4", "Sprint review", 13, 15),
            _event("e5", "Sync marketing", 15, 16),
            _event("e6", "Volo Roma-Parigi", 16, 19),
        ]
        d = analyze_day(target_date=date.today(), events=evs, calendar_sync_hint=True)
        assert d.total_events == 6
        assert "many_meetings" in d.signals
        assert "many_travel_hours" in d.signals
        assert "many_work_hours" in d.signals
        assert "stressful_day" in d.signals or "very_busy_day" in d.warnings
        assert d.energy_estimation["level"] in ("low", "medium")
        assert d.score < 60
        assert d.confidence == "high"

    def test_a3_many_meetings_only(self):
        evs = [
            _event("m1", "Meeting A", 9, 9, ),
            _event("m1", "Meeting A", 9, 10),
            _event("m2", "Meeting B", 10, 11),
            _event("m3", "Meeting C", 11, 12),
            _event("m4", "Meeting D", 13, 14),
        ]
        # dedupe accidental duplicate above; keep unique ids
        evs = [
            _event("m1", "Meeting A", 9, 10),
            _event("m2", "Meeting B", 10, 11),
            _event("m3", "Meeting C", 11, 12),
            _event("m4", "Meeting D", 13, 14),
        ]
        d = analyze_day(target_date=date.today(), events=evs)
        assert "many_meetings" in d.signals

    def test_a4_travel_day(self):
        evs = [
            _event("t1", "Volo Roma-Parigi", 8, 11),
            _event("t2", "Trasferimento hotel", 12, 13),
        ]
        d = analyze_day(target_date=date.today(), events=evs)
        assert "many_travel_hours" in d.signals

    def test_a5_weekend_flag(self):
        # find next saturday
        today = date.today()
        offset = (5 - today.weekday()) % 7
        sat = today + timedelta(days=offset if offset > 0 else 7)
        d = analyze_day(target_date=sat, events=[])
        assert d.is_weekend is True
        assert "weekend" in d.signals

    def test_a6_holiday_flag(self):
        # 15 August of some year (Ferragosto)
        d = analyze_day(target_date=date(date.today().year, 8, 15), events=[])
        assert d.is_holiday is True
        assert "holiday" in d.signals

    def test_a7_vacation_day_all_day(self):
        evs = [{
            "id": "v1", "title": "Ferie", "starts_at": _dt(0), "ends_at": _dt(0) + timedelta(days=1),
            "all_day": True, "status": "confirmed",
        }]
        d = analyze_day(target_date=date.today(), events=evs)
        assert d.is_vacation_day is True
        assert "vacation" in d.signals

    def test_a8_overlapping_events_merged_in_busy(self):
        evs = [
            _event("o1", "Meeting", 9, 11),
            _event("o2", "Chiamata", 10, 12),   # overlaps first
        ]
        d = analyze_day(target_date=date.today(), events=evs)
        # busy_minutes should be 3h (merged), NOT 4h (sum)
        assert d.busy_minutes == 180
        # exactly one merged busy slot for that window
        overlapping_slots = [
            s for s in d.busy_slots
            if s["start"].startswith(_iso(_dt(9))[:13])
        ]
        assert len(overlapping_slots) == 1

    def test_a9_free_slots_span_the_gaps(self):
        evs = [
            _event("g1", "Meeting", 10, 11),
            _event("g2", "Meeting", 14, 15),
        ]
        d = analyze_day(target_date=date.today(), events=evs)
        # Free slots must include the 11:00-14:00 gap
        gaps = [s for s in d.free_slots if s["duration_min"] >= 60]
        assert gaps, "expected at least one free slot >= 60 min"
        assert d.free_minutes >= 60

    def test_a10_back_to_back_marathon(self):
        evs = [
            _event("b1", "Meeting", 9, 10),
            _event("b2", "Meeting", 10, 11),
            _event("b3", "Meeting", 11, 12),
            _event("b4", "Meeting", 12, 13),
        ]
        d = analyze_day(target_date=date.today(), events=evs)
        assert d.consecutive_events >= 3
        assert "back_to_back_marathon" in d.warnings
        assert "stressful_day" in d.signals

    def test_a11_free_morning_opportunity(self):
        # No events before 14:00
        evs = [
            _event("x1", "Meeting", 14, 15),
            _event("x2", "Meeting", 16, 17),
        ]
        d = analyze_day(target_date=date.today(), events=evs)
        assert "free_morning" in d.opportunities

    def test_a12_confidence_high_with_many_events(self):
        evs = [
            _event(f"e{i}", "Meeting", 9 + i, 9 + i + 1) for i in range(5)
        ]
        d = analyze_day(target_date=date.today(), events=evs)
        assert d.confidence == "high"

    def test_a13_cancelled_events_ignored(self):
        evs = [
            _event("c1", "Meeting cancellato", 9, 10, status="cancelled"),
            _event("c2", "Meeting reale", 11, 12),
        ]
        d = analyze_day(target_date=date.today(), events=evs)
        assert d.total_events == 1
        assert d.busy_minutes == 60

    def test_a14_energy_estimation_shape(self):
        d = analyze_day(target_date=date.today(), events=[])
        assert set(d.energy_estimation.keys()) == {"level", "score", "reasons"}

    def test_a15_output_shape_stable(self):
        d = analyze_day(target_date=date.today(), events=[])
        payload = d.to_dict()
        required = {
            "date", "timezone", "generated_at", "score", "confidence",
            "total_events", "all_day_events", "is_weekend", "is_holiday",
            "is_vacation_day", "busy_minutes", "free_minutes",
            "consecutive_events", "total_break_minutes", "first_event_at",
            "last_event_at", "by_category", "busy_slots", "free_slots",
            "signals", "warnings", "opportunities", "energy_estimation",
            "version", "source_counts",
        }
        assert required.issubset(set(payload.keys()))


# ============================================================
# 2) API integration tests
# ============================================================
def _seed_event_node(client, user, *, title: str, start_h: int, end_h: int, day_offset: int = 0, all_day: bool = False):
    """Create a life graph `event` node so DailySummaryService picks it up."""
    attrs = {
        "starts_at": _dt(start_h, day_offset=day_offset).isoformat(),
        "ends_at": _dt(end_h, day_offset=day_offset).isoformat(),
        "all_day": all_day,
        "connector_id": "calendar_google",
    }
    r = client.post("/api/life-graph/nodes", headers=h(user), json={
        "type": "event", "label": title, "attributes": attrs,
    })
    assert r.status_code == 200, r.text
    return r.json()


class TestB_APIEndpoints:
    def test_b1_today_default_empty(self, client, user_a):
        r = client.get("/api/daily/today", headers=h(user_a))
        assert r.status_code == 200
        body = r.json()
        assert body["total_events"] == 0
        assert body["version"] == DAILY_SUMMARY_VERSION
        assert set(body["signals"]).intersection({"empty_day", "light_day", "relaxed_day", "weekend", "holiday"})

    def test_b2_today_with_events(self, client, user_a):
        # Seed events for today (unique per-user so no cross-contamination)
        _seed_event_node(client, user_a, title="Standup mattutino", start_h=9, end_h=10)
        _seed_event_node(client, user_a, title="Meeting design", start_h=10, end_h=11)
        _seed_event_node(client, user_a, title="Sprint review", start_h=14, end_h=15)
        r = client.get("/api/daily/today", headers=h(user_a))
        body = r.json()
        assert body["total_events"] >= 3
        assert body["busy_minutes"] >= 180
        assert body["by_category"].get("meeting", 0) >= 60

    def test_b3_tomorrow(self, client, user_a):
        _seed_event_node(client, user_a, title="Riunione domani", start_h=10, end_h=11, day_offset=1)
        r = client.get("/api/daily/tomorrow", headers=h(user_a))
        body = r.json()
        assert body["total_events"] >= 1
        # date is exactly today+1
        expected = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        assert body["date"] == expected

    def test_b4_refresh_returns_both_days(self, client, user_a):
        r = client.post("/api/daily/refresh", headers=h(user_a))
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"today", "tomorrow"}
        assert body["today"]["date"] != body["tomorrow"]["date"]

    def test_b5_specific_date(self, client, user_a):
        # Weekend + 15-Aug case
        r = client.get("/api/daily/date/2027-08-15", headers=h(user_a))
        assert r.status_code == 200
        body = r.json()
        assert body["is_holiday"] is True
        assert "holiday" in body["signals"]

    def test_b6_bad_date_400(self, client, user_a):
        r = client.get("/api/daily/date/nonsense", headers=h(user_a))
        assert r.status_code == 400

    def test_b7_auth_required(self, client):
        r = client.get("/api/daily/today")
        assert r.status_code == 401

    def test_b8_cross_user_isolation(self, client, user_a):
        r = client.post("/api/auth/register", json={
            "email": f"iter10_b_{TS}@ora.app", "password": "Passw0rd!", "name": "B",
        })
        token_b = r.json()["token"]
        # user B sees no events
        r2 = client.get("/api/daily/today", headers={"Authorization": f"Bearer {token_b}"})
        assert r2.status_code == 200
        assert r2.json()["total_events"] == 0


# ============================================================
# 3) Context Assembler flag
# ============================================================
class TestC_ContextAssemblerFlag:
    def _assemble(self, client, user, decision_id):
        r = client.post(f"/api/context/decisions/{decision_id}/assemble", headers=h(user))
        assert r.status_code == 200
        return r.json()

    def test_c1_flag_off_hash_stable_and_no_signals(self, client, user_a, monkeypatch):
        monkeypatch.setenv("DAILY_SUMMARY_ENABLED", "false")
        r = client.post("/api/decisions", headers=h(user_a), json={"title": "C1", "category": "generic"})
        did = r.json()["id"]
        snap1 = self._assemble(client, user_a, did)
        snap2 = self._assemble(client, user_a, did)
        assert snap1["context_hash"] == snap2["context_hash"]
        # provider registered but produces no signals
        assert "daily_summary" in snap1["provenance"]["providers_run"]
        daily_signals = [s for s in snap1["signals"] if s.get("source_module") == "daily_summary"]
        assert daily_signals == []

    def test_c2_flag_on_emits_daily_signal(self, client, user_a, monkeypatch):
        monkeypatch.setenv("DAILY_SUMMARY_ENABLED", "true")
        r = client.post("/api/decisions", headers=h(user_a), json={"title": "C2", "category": "generic"})
        did = r.json()["id"]
        snap = self._assemble(client, user_a, did)
        daily_signals = [s for s in snap["signals"] if s.get("source_module") == "daily_summary"]
        assert daily_signals, "expected at least one daily_summary signal when flag ON"
        # `daily_summary` payload must NOT include titles of events
        assert not any("title" in (s.get("value") or {}) for s in daily_signals if s["key"] == "daily_summary")
        monkeypatch.setenv("DAILY_SUMMARY_ENABLED", "false")


# ============================================================
# 4) Regression / do-not-fire rules
# ============================================================
class TestD_NoDecisionCreation:
    def test_d1_daily_never_creates_decisions(self, client, user_a):
        # baseline count
        r0 = client.get("/api/decisions", headers=h(user_a))
        n0 = len(r0.json()["items"])
        # hit all daily endpoints multiple times
        for _ in range(3):
            client.get("/api/daily/today", headers=h(user_a))
            client.get("/api/daily/tomorrow", headers=h(user_a))
            client.post("/api/daily/refresh", headers=h(user_a))
        r1 = client.get("/api/decisions", headers=h(user_a))
        n1 = len(r1.json()["items"])
        assert n0 == n1

    def test_d2_no_notifications_side_effect(self, client, user_a):
        # There is no notifications collection in this iteration.
        # Assert audit doesn't contain daily-related emission events.
        r = client.get("/api/permissions/audit?limit=500", headers=h(user_a))
        assert r.status_code == 200
        for ev in r.json()["items"]:
            assert not str(ev.get("event_type", "")).startswith("notification.")
