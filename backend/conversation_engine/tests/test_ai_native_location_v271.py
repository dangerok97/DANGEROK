"""V2.7.1 — Foreground location + PresenceContext (slice 1)."""
from __future__ import annotations

import inspect
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

import pytest

os.environ["AI_CORE_TRACE"] = "1"

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.ai_core.trace import add_step, public_trace
from location.models import (
    CURRENT_MAX_AGE_SEC,
    RECENT_MAX_AGE_SEC,
    SIGNAL_TTL_SECONDS,
    LocationSignal,
    PresenceContext,
)
from location.place_label import ResolvedPlace
from location.service import LocationService, classify_freshness, runtime_location_capabilities


class _MemCol:
    def __init__(self):
        self.docs: List[dict] = []
        self.indexes: List[Any] = []

    async def create_index(self, *args, **kwargs):
        self.indexes.append((args, kwargs))

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def find_one(self, q, proj=None, sort=None):
        matches = [d for d in self.docs if all(d.get(k) == v for k, v in q.items())]
        if sort:
            field, direction = sort[0]
            matches.sort(key=lambda d: d.get(field) or "", reverse=direction < 0)
        return dict(matches[0]) if matches else None

    async def update_one(self, q, update, upsert=False):
        def _apply_set(doc: dict, sets: dict) -> dict:
            out = dict(doc)
            for k, v in sets.items():
                if "." in k:
                    parts = k.split(".")
                    cur = out
                    for p in parts[:-1]:
                        nxt = cur.get(p)
                        if not isinstance(nxt, dict):
                            nxt = {}
                            cur[p] = nxt
                        cur = nxt
                    cur[parts[-1]] = v
                else:
                    out[k] = v
            return out

        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in q.items()):
                if "$set" in update:
                    self.docs[i] = _apply_set(d, update["$set"])
                return
        if upsert:
            base = dict(q)
            if "$set" in update:
                base = _apply_set(base, update["$set"])
            self.docs.append(base)


class FakeLocDB:
    def __init__(self):
        self._cols: Dict[str, _MemCol] = {}
        self.users = _MemCol()

    def __getitem__(self, name: str) -> _MemCol:
        if name not in self._cols:
            self._cols[name] = _MemCol()
        return self._cols[name]


@pytest.fixture
def db():
    return FakeLocDB()


@pytest.mark.asyncio
async def test_a_create_signal_user_scoped(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    with patch.object(svc, "_reverse_place", AsyncMock(return_value=ResolvedPlace(display_label="Testville", municipality="Testville", precision="municipality"))):
        r = await svc.ingest_foreground_signal(
            "u1", latitude=42.1, longitude=12.2, accuracy_meters=25
        )
    assert r["ok"] is True
    assert r["memory_written"] is False
    sigs = db["location_signals"].docs
    assert len(sigs) == 1
    assert sigs[0]["user_id"] == "u1"
    assert "expires_at" in sigs[0]


@pytest.mark.asyncio
async def test_b_ttl_index_configured(db):
    svc = LocationService(db)
    await svc.ensure_indexes()
    idx = db["location_signals"].indexes
    names = [kw.get("name") for _, kw in idx]
    assert "ttl_expires_at" in names
    assert SIGNAL_TTL_SECONDS == 2 * 60 * 60


def test_c_freshness_current():
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(seconds=60)).isoformat()
    assert classify_freshness(ts, now=now) == "CURRENT"


def test_d_freshness_stale():
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(seconds=RECENT_MAX_AGE_SEC + 10)).isoformat()
    assert classify_freshness(ts, now=now) == "STALE"


def test_e_freshness_unknown():
    assert classify_freshness(None) == "UNKNOWN"
    assert classify_freshness("") == "UNKNOWN"


@pytest.mark.asyncio
async def test_c2_signal_to_presence_current(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    with patch.object(svc, "_reverse_place", AsyncMock(return_value=None)):
        await svc.ingest_foreground_signal("u1", latitude=41.0, longitude=12.0)
    p = await svc.build_presence("u1")
    assert p.freshness == "CURRENT"
    assert p.latitude is not None


@pytest.mark.asyncio
async def test_d2_old_signal_stale(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    sig = LocationSignal(
        user_id="u1",
        latitude=41.0,
        longitude=12.0,
        timestamp=old.isoformat(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await svc.repo.insert_signal(sig)
    p = await svc.build_presence("u1")
    assert p.freshness == "STALE"


@pytest.mark.asyncio
async def test_e2_no_signal_unknown(db):
    svc = LocationService(db)
    p = await svc.build_presence("u_none")
    assert p.freshness == "UNKNOWN"


@pytest.mark.asyncio
async def test_f_permission_denied(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    await svc.record_permission_outcome("u1", state="denied")
    r = await svc.capability_get_current_location("u1")
    assert r["status"] == "denied"
    assert r["needs_client"] is False


@pytest.mark.asyncio
async def test_g_capability_unavailable_native(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    r = await svc.capability_get_current_location("u1", platform="ios")
    assert r["status"] == "unavailable"
    assert r["error"] == "native_unsupported"


@pytest.mark.asyncio
async def test_h_i_residence_separate_device_no_overwrite(db):
    """Device signal must not write residence / Memory."""
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    with patch.object(svc, "_reverse_place", AsyncMock(return_value=ResolvedPlace(display_label="Coastal Locality", municipality="Coastal Locality", precision="municipality"))):
        r = await svc.ingest_foreground_signal("u1", latitude=38.7, longitude=16.1)
    assert r["memory_written"] is False
    # No users.settings residence mutation beyond location_mode
    user_docs = db.users.docs
    for d in user_docs:
        assert "residence" not in str(d.get("settings") or {})


@pytest.mark.asyncio
async def test_j_temporary_context_not_overwritten_by_device():
    """current_facts.location remains conversational — service never touches it."""
    src = inspect.getsource(LocationService.ingest_foreground_signal)
    assert "current_facts" not in src
    assert "residence" not in src.lower() or "overwrite" not in src.lower()


def test_k_goal_override_semantics_in_prompt():
    from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT

    assert "Goal-specific origin" in COGNITIVE_SYSTEM_PROMPT
    assert "device is elsewhere" in COGNITIVE_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_l_context_broker_minimized(db):
    from conversation_engine.ai_core.context_broker import ContextBroker

    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    with patch.object(svc, "_reverse_place", AsyncMock(return_value=ResolvedPlace(display_label="Somewhere", municipality="Somewhere", precision="municipality"))):
        await svc.ingest_foreground_signal("u1", latitude=41.9, longitude=12.5)
    broker = ContextBroker(db)
    facts = await broker._presence_facts("u1")
    assert len(facts) == 1
    blob = facts[0].statement
    assert "NOT durable residence" in blob or "presence" in blob.lower()
    # No GPS trail dump
    assert "history" not in blob.lower()


@pytest.mark.asyncio
async def test_m_raw_gps_not_in_memory_path(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    with patch.object(svc, "_reverse_place", AsyncMock(return_value=None)):
        r = await svc.ingest_foreground_signal("u1", latitude=41.0, longitude=12.0)
    assert r.get("memory_written") is False
    assert "life_memory" not in db._cols


def test_n_no_raw_presence_in_life_map():
    from location import service as loc_mod

    src = inspect.getsource(loc_mod)
    assert "life_map" not in src
    assert "LifeMap" not in src


@pytest.mark.asyncio
async def test_o_x_ownership_cross_user(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    with patch.object(svc, "_reverse_place", AsyncMock(return_value=None)):
        await svc.ingest_foreground_signal("u1", latitude=41.0, longitude=12.0)
    p2 = await svc.build_presence("u2")
    assert p2.freshness == "UNKNOWN"
    assert p2.latitude is None


def test_p_no_coordinates_in_urls():
    from location.router import router

    for route in router.routes:
        path = getattr(route, "path", "") or ""
        assert "{lat" not in path
        assert "{lon" not in path
        assert "latitude" not in path


def test_q_no_exact_coords_in_traces():
    tr = {"steps": []}
    add_step(tr, event="X", latitude=41.9028, longitude=12.4964, coordinates={"latitude": 1})
    step = tr["steps"][0]
    assert "latitude" not in step
    assert step.get("coordinates") == "[redacted]" or "coordinates" not in step
    pub = public_trace(
        {"steps": [{"latitude": 41.9028, "event": "TOOL"}], "ai_calls": 1}
    )
    steps = pub.get("steps") or []
    blob = str(steps)
    assert "41.9028" not in blob
    if steps and isinstance(steps[0], dict):
        assert steps[0].get("latitude") in (None, "[redacted]")


def test_r_ai_capability_availability():
    reg = ToolRegistry(db=None)
    names = {t["capability"] for t in reg.list_public()}
    assert "get_current_location" in names
    assert "get_current_presence" in names
    assert "get_recent_presence_context" in names
    assert "get_home_location" not in names
    assert "get_work_location" not in names


@pytest.mark.asyncio
async def test_s_reverse_geocode_failure_honesty(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    with patch.object(svc, "_reverse_place", AsyncMock(return_value=None)):
        r = await svc.ingest_foreground_signal("u1", latitude=41.0, longitude=12.0)
    assert r["ok"]
    p = await svc.build_presence("u1")
    assert p.place_label is None
    assert p.latitude is not None


def test_t_no_home_work_hardcoding():
    from location import service as loc_mod
    from location import caps as loc_caps

    blob = inspect.getsource(loc_mod) + inspect.getsource(loc_caps)
    for bad in ("get_home_location", "get_work_location", "is_at_home", "is_at_work"):
        assert bad not in blob


def test_u_no_event_action_rules():
    from location import service as loc_mod

    src = inspect.getsource(loc_mod)
    assert "geofence" not in src.lower()
    assert "on_enter" not in src.lower()
    assert "trigger_action" not in src.lower()


def test_v_one_ora_production_route():
    from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

    src = inspect.getsource(AICoreOrchestrator._public)
    assert "/ora/" in src
    assert "ora-location" not in src


@pytest.mark.asyncio
async def test_w_permission_preference_enforced(db):
    svc = LocationService(db)
    # default off
    r = await svc.ingest_foreground_signal("u1", latitude=41.0, longitude=12.0)
    assert r["ok"] is False
    assert r["error"] == "location_disabled"


def test_y_web_foreground_bridge_fields():
    caps = runtime_location_capabilities(preference="while_using", platform="web")
    assert caps["foreground_location"] == "available"
    assert caps["background_location"] == "unavailable"
    assert caps["native_location"] == "unsupported"
    caps_off = runtime_location_capabilities(preference="off", platform="web")
    assert caps_off["current_location"] == "requires_consent"
    assert caps_off["ora_location_consent"] == "not_requested"
    assert "disabled_by_user" not in caps_off.values()


@pytest.mark.asyncio
async def test_needs_client_when_no_signal(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    r = await svc.capability_get_current_location("u1")
    assert r["status"] == "needs_client"
    assert r["client_action"]["type"] == "request_foreground_location"


@pytest.mark.asyncio
async def test_permission_required_when_off(db):
    svc = LocationService(db)
    r = await svc.capability_get_current_location("u1")
    assert r["status"] == "consent_required"
    assert r["error"] == "ora_consent_required"
    assert r["needs_client"] is True
    assert r["client_action"]["type"] == "request_location_permission"
    assert "disabilitati" not in (r.get("user_facing_hint") or "").lower()


@pytest.mark.asyncio
async def test_client_actions_pause_loop(db):
    from conversation_engine.ai_core.loop import run_cognitive_loop
    from conversation_engine.models import ConversationSession

    await LocationService(db).set_preference("u1", "while_using")

    async def decision_fn(system: str, user: str):
        return {
            "response_mode": "tool",
            "user_intent_summary": "where am i",
            "reasoning_status": "needs_tool",
            "tool_call": {
                "capability": "get_current_location",
                "operation": "run",
                "arguments": {},
                "reason": "need presence",
            },
        }

    sess = ConversationSession(user_id="u1", meta={"ui_mode": "ai_core", "ai_core": {}})
    result = await run_cognitive_loop(
        sess=sess,
        user_message="Dove sono adesso?",
        db=db,
        decision_fn=decision_fn,
    )
    assert result.client_actions
    assert result.client_actions[0]["type"] == "request_foreground_location"


def test_freshness_thresholds_documented():
    assert CURRENT_MAX_AGE_SEC == 5 * 60
    assert RECENT_MAX_AGE_SEC == 30 * 60
    assert SIGNAL_TTL_SECONDS == 7200


@pytest.mark.asyncio
async def test_presence_for_ai_hides_stale_coords(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    sig = LocationSignal(
        user_id="u1",
        latitude=41.90281337,
        longitude=12.49641234,
        timestamp=old.isoformat(),
        place_label="Roma",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await svc.repo.insert_signal(sig)
    p = await svc.build_presence("u1")
    ai = p.for_ai()
    assert ai["freshness"] == "STALE"
    assert "coordinates" not in ai
    assert "Sei a" not in str(ai)


@pytest.mark.asyncio
async def test_browser_denied_distinct_from_device_disabled(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    await svc.record_permission_outcome("u1", state="denied")
    r = await svc.capability_get_current_location("u1")
    assert r["status"] == "denied"
    assert r["error"] == "permission_denied"
    assert r["needs_client"] is False


@pytest.mark.asyncio
async def test_position_unavailable_distinct(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    await svc.record_permission_outcome("u1", state="position_unavailable")
    r = await svc.capability_get_current_location("u1")
    assert r["status"] == "unavailable"
    assert r["error"] == "position_unavailable"


@pytest.mark.asyncio
async def test_timeout_distinct(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    await svc.record_permission_outcome("u1", state="timeout")
    r = await svc.capability_get_current_location("u1")
    assert r["status"] == "timeout"
    assert r["error"] == "geolocation_timeout"


@pytest.mark.asyncio
async def test_location_nudge_forces_capability(db):
    """Invented device-disabled answer without tool → nudge → tool → client_action."""
    from conversation_engine.ai_core.loop import run_cognitive_loop
    from conversation_engine.models import ConversationSession

    calls = {"n": 0}

    async def decision_fn(system: str, user: str):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "response_mode": "answer",
                "user_intent_summary": "where am i",
                "reasoning_status": "enough_information",
                "message_to_user": (
                    "Al momento non posso rilevare la tua posizione perché i servizi di "
                    "localizzazione del dispositivo sono disabilitati."
                ),
            }
        return {
            "response_mode": "tool",
            "user_intent_summary": "where am i",
            "reasoning_status": "needs_tool",
            "tool_call": {
                "capability": "get_current_location",
                "operation": "run",
                "arguments": {},
                "reason": "need presence",
            },
        }

    sess = ConversationSession(user_id="u1", meta={"ui_mode": "ai_core", "ai_core": {}})
    result = await run_cognitive_loop(
        sess=sess,
        user_message="Dove sono adesso?",
        db=db,
        decision_fn=decision_fn,
    )
    assert result.client_actions
    assert result.client_actions[0]["type"] == "request_location_permission"
    assert "disabilitati" not in (result.ora_text or "").lower()


@pytest.mark.asyncio
async def test_outdated_resolver_version_reresolves_without_new_gps(db):
    """Root-cause regression: CURRENT signal keeps coords; place semantics upgrade."""
    from location.place_label import PLACE_RESOLVER_VERSION, ResolvedPlace

    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    # Simulate pre-v2 signal: municipality-only label, no resolver version
    old = LocationSignal(
        user_id="u1",
        latitude=38.71,
        longitude=16.12,
        accuracy_meters=25,
        place_label="Admin Town",
        place_municipality="Admin Town",
        place_label_precision="municipality",
        place_resolver_version=None,
    )
    await svc.repo.insert_signal(old)

    upgraded = ResolvedPlace(
        display_label="Coastal Locality",
        locality="Coastal Locality",
        municipality="Admin Town",
        region="Sample Region",
        country="Italia",
        precision="locality",
    )
    with patch.object(svc, "_reverse_place", AsyncMock(return_value=upgraded)):
        p = await svc.build_presence("u1")
        cap = await svc.capability_get_current_location("u1")

    assert p.place_label == "Coastal Locality"
    assert p.place_locality == "Coastal Locality"
    assert p.place_municipality == "Admin Town"
    assert p.place_resolver_version == PLACE_RESOLVER_VERSION
    assert cap["status"] == "ok"
    assert cap["place_label"] == "Coastal Locality"
    assert (cap.get("place") or {}).get("locality") == "Coastal Locality"
    # No client_action — GPS still CURRENT; only semantics refreshed
    assert not cap.get("needs_client")


@pytest.mark.asyncio
async def test_current_resolver_version_skips_reresolve(db):
    from location.place_label import PLACE_RESOLVER_VERSION, ResolvedPlace

    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    sig = LocationSignal(
        user_id="u1",
        latitude=38.71,
        longitude=16.12,
        accuracy_meters=25,
        place_label="Coastal Locality",
        place_locality="Coastal Locality",
        place_municipality="Admin Town",
        place_label_precision="locality",
        place_resolver_version=PLACE_RESOLVER_VERSION,
    )
    await svc.repo.insert_signal(sig)
    mock = AsyncMock(
        return_value=ResolvedPlace(display_label="SHOULD_NOT_CALL", precision="locality")
    )
    with patch.object(svc, "_reverse_place", mock):
        p = await svc.build_presence("u1")
    assert p.place_label == "Coastal Locality"
    mock.assert_not_called()


@pytest.mark.asyncio
async def test_resume_does_not_duplicate_recent_user_turn(db):
    from conversation_engine.ai_core import state as state_mod
    from conversation_engine.ai_core.loop import run_cognitive_loop
    from conversation_engine.models import ConversationSession

    await LocationService(db).set_preference("u1", "while_using")
    svc = LocationService(db)
    with patch.object(svc, "_reverse_place", AsyncMock(return_value=ResolvedPlace(display_label="Somewhere", municipality="Somewhere", precision="municipality"))):
        await svc.ingest_foreground_signal("u1", latitude=41.0, longitude=12.0)

    step = {"n": 0}

    async def decision_fn2(system: str, user: str):
        step["n"] += 1
        if step["n"] % 2 == 1:
            return {
                "response_mode": "tool",
                "user_intent_summary": "where",
                "reasoning_status": "needs_tool",
                "tool_call": {
                    "capability": "get_current_location",
                    "operation": "run",
                    "arguments": {},
                    "reason": "need",
                },
            }
        return {
            "response_mode": "answer",
            "user_intent_summary": "where",
            "reasoning_status": "enough_information",
            "message_to_user": "Sei vicino a Somewhere.",
        }

    sess = ConversationSession(user_id="u1", meta={"ui_mode": "ai_core", "ai_core": {}})
    await run_cognitive_loop(
        sess=sess,
        user_message="Dove sono adesso?",
        db=db,
        decision_fn=decision_fn2,
    )
    st = state_mod.get_ai_state(sess)
    n_before = len(
        [t for t in (st.get("recent_turns") or []) if t.get("role") == "user"]
    )
    step["n"] = 0
    await run_cognitive_loop(
        sess=sess,
        user_message="Dove sono adesso?",
        db=db,
        decision_fn=decision_fn2,
        resume_client=True,
    )
    st2 = state_mod.get_ai_state(sess)
    n_after = len(
        [t for t in (st2.get("recent_turns") or []) if t.get("role") == "user"]
    )
    assert n_after == n_before


@pytest.mark.asyncio
async def test_stale_emits_needs_client_and_foreground_action(db):
    """STALE + while_using → needs_client + request_foreground_location (refresh)."""
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    await svc.repo.insert_signal(
        LocationSignal(
            user_id="u1",
            latitude=38.71,
            longitude=16.12,
            timestamp=old.isoformat(),
            place_label="Vibo Marina",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    r = await svc.capability_get_current_location("u1")
    assert r["status"] == "stale"
    assert r["freshness"] == "STALE"
    assert r["needs_client"] is True
    assert r["client_action"]["type"] == "request_foreground_location"
    assert r["client_action"].get("refresh") is True
    assert r["place_label"] == "Vibo Marina"
    hint = (r.get("user_facing_hint") or "").lower()
    assert "permission" in hint or "denied" in hint
    assert "disabled" in hint  # instructs model NOT to claim disabled without denied


@pytest.mark.asyncio
async def test_stale_with_ora_off_requests_consent(db):
    svc = LocationService(db)
    # Preference off but Chrome may still be granted — ORA must ask product consent
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    await svc.repo.insert_signal(
        LocationSignal(
            user_id="u1",
            latitude=38.71,
            longitude=16.12,
            timestamp=old.isoformat(),
            place_label="Vibo Marina",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    # pref defaults to off
    r = await svc.capability_get_current_location("u1")
    assert r["status"] == "consent_required"
    assert r["client_action"]["type"] == "request_location_permission"


@pytest.mark.asyncio
async def test_stale_pauses_loop_with_client_action(db):
    from conversation_engine.ai_core.loop import run_cognitive_loop
    from conversation_engine.models import ConversationSession

    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    await svc.repo.insert_signal(
        LocationSignal(
            user_id="u1",
            latitude=38.71,
            longitude=16.12,
            timestamp=old.isoformat(),
            place_label="Vibo Marina",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )

    async def decision_fn(system: str, user: str):
        return {
            "response_mode": "tool",
            "user_intent_summary": "where am i",
            "reasoning_status": "needs_tool",
            "tool_call": {
                "capability": "get_current_location",
                "operation": "run",
                "arguments": {},
                "reason": "need presence",
            },
        }

    sess = ConversationSession(user_id="u1", meta={"ui_mode": "ai_core", "ai_core": {}})
    result = await run_cognitive_loop(
        sess=sess,
        user_message="Dove sono adesso?",
        db=db,
        decision_fn=decision_fn,
    )
    assert result.client_actions
    assert result.client_actions[0]["type"] == "request_foreground_location"
    assert result.client_actions[0].get("refresh") is True
    assert (result.ora_text or "") == ""


@pytest.mark.asyncio
async def test_fresh_signal_after_stale_is_current(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    await svc.repo.insert_signal(
        LocationSignal(
            user_id="u1",
            latitude=38.71,
            longitude=16.12,
            timestamp=old.isoformat(),
            place_label="Vibo Marina",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    assert (await svc.capability_get_current_location("u1"))["status"] == "stale"
    with patch.object(
        svc,
        "_reverse_place",
        AsyncMock(
            return_value=ResolvedPlace(
                display_label="Vibo Marina",
                locality="Vibo Marina",
                municipality="Vibo Valentia",
                precision="locality",
            )
        ),
    ):
        await svc.ingest_foreground_signal("u1", latitude=38.715, longitude=16.125)
    r = await svc.capability_get_current_location("u1")
    assert r["status"] == "ok"
    assert r["freshness"] == "CURRENT"
    assert r["needs_client"] is False
    assert r["place_label"] == "Vibo Marina"


@pytest.mark.asyncio
async def test_timeout_after_stale_is_terminal_then_retryable(db):
    """After FE timeout on STALE refresh: terminal timeout; next turn clears and retries."""
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    await svc.repo.insert_signal(
        LocationSignal(
            user_id="u1",
            latitude=38.71,
            longitude=16.12,
            timestamp=old.isoformat(),
            place_label="Vibo Marina",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    await svc.record_permission_outcome("u1", state="timeout")
    mid = await svc.capability_get_current_location("u1")
    assert mid["status"] == "timeout"
    assert mid["needs_client"] is False
    assert mid.get("place_label") == "Vibo Marina"
    assert "permission" not in (mid.get("error") or "")
    await svc.clear_transient_acquisition_error("u1")
    retry = await svc.capability_get_current_location("u1")
    assert retry["status"] == "stale"
    assert retry["needs_client"] is True
    assert retry["client_action"]["type"] == "request_foreground_location"


@pytest.mark.asyncio
async def test_denied_not_confused_with_timeout(db):
    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    await svc.record_permission_outcome("u1", state="denied")
    r = await svc.capability_get_current_location("u1")
    assert r["status"] == "denied"
    assert r["error"] == "permission_denied"
    # Denied is sticky — clear_transient must not reopen
    await svc.clear_transient_acquisition_error("u1")
    r2 = await svc.capability_get_current_location("u1")
    assert r2["status"] == "denied"


@pytest.mark.asyncio
async def test_pending_capability_retry_nudge_without_location_phrase(db):
    """Follow-up like a short retry retries pending location via pending_client_capability."""
    from conversation_engine.ai_core import state as state_mod
    from conversation_engine.ai_core.loop import run_cognitive_loop
    from conversation_engine.models import ConversationSession

    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    await svc.repo.insert_signal(
        LocationSignal(
            user_id="u1",
            latitude=38.71,
            longitude=16.12,
            timestamp=old.isoformat(),
            place_label="Vibo Marina",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )

    calls = {"n": 0}

    async def decision_fn(system: str, user: str):
        calls["n"] += 1
        if calls["n"] == 1:
            # Answer without tool — pending capability must force location nudge
            return {
                "response_mode": "answer",
                "user_intent_summary": "retry",
                "reasoning_status": "enough_information",
                "message_to_user": "Riprovo senza tool.",
            }
        return {
            "response_mode": "tool",
            "user_intent_summary": "retry location",
            "reasoning_status": "needs_tool",
            "tool_call": {
                "capability": "get_current_location",
                "operation": "run",
                "arguments": {},
                "reason": "retry",
            },
        }

    sess = ConversationSession(user_id="u1", meta={"ui_mode": "ai_core", "ai_core": {}})
    st = state_mod.get_ai_state(sess)
    st["pending_client_capability"] = {
        "capability": "get_current_location",
        "action": "request_foreground_location",
        "refresh": True,
    }
    state_mod.save_ai_state(sess, st)

    result = await run_cognitive_loop(
        sess=sess,
        user_message="ok riprova",  # generic retry — not a hardcoded location phrase
        db=db,
        decision_fn=decision_fn,
    )
    assert calls["n"] >= 2
    assert result.client_actions
    assert result.client_actions[0]["type"] == "request_foreground_location"


@pytest.mark.asyncio
async def test_success_resume_uses_fresh_observation(db):
    from conversation_engine.ai_core import state as state_mod
    from conversation_engine.ai_core.loop import run_cognitive_loop
    from conversation_engine.models import ConversationSession

    svc = LocationService(db)
    await svc.set_preference("u1", "while_using")
    with patch.object(
        svc,
        "_reverse_place",
        AsyncMock(
            return_value=ResolvedPlace(
                display_label="Vibo Marina",
                locality="Vibo Marina",
                municipality="Vibo Valentia",
                precision="locality",
            )
        ),
    ):
        await svc.ingest_foreground_signal("u1", latitude=38.71, longitude=16.12)

    calls = {"n": 0}

    async def decision_fn(system: str, user: str):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "response_mode": "tool",
                "user_intent_summary": "where",
                "reasoning_status": "needs_tool",
                "tool_call": {
                    "capability": "get_current_location",
                    "operation": "run",
                    "arguments": {},
                    "reason": "need",
                },
            }
        return {
            "response_mode": "answer",
            "user_intent_summary": "where",
            "reasoning_status": "enough_information",
            "message_to_user": "Adesso sei a Vibo Marina.",
        }

    sess = ConversationSession(user_id="u1", meta={"ui_mode": "ai_core", "ai_core": {}})
    st = state_mod.get_ai_state(sess)
    st["pending_client_capability"] = {
        "capability": "get_current_location",
        "action": "request_foreground_location",
    }
    st["pending_client_resume_message"] = "Dove sono adesso?"
    state_mod.save_ai_state(sess, st)

    result = await run_cognitive_loop(
        sess=sess,
        user_message="Dove sono adesso?",
        db=db,
        decision_fn=decision_fn,
        resume_client=True,
    )
    assert "Vibo Marina" in (result.ora_text or "")
    st2 = state_mod.get_ai_state(sess)
    assert not st2.get("pending_client_capability")
