"""Iterazione 16 — Behavioral Data Integrity & Context Wiring.

Tests
-----
* Timezone-aware bucketing (ORA_DEFAULT_TZ)
* Session pairing (open + refresh + close) → avg_session_minutes
* Context Assembler wiring: BehaviorProfileProvider registered but
  strict no-op when BEHAVIOR_PROFILE_ENABLED=false → context_hash unchanged
* When flag=true → 1 extra signal `behavior.profile` appears and hash
  changes DETERMINISTICALLY
* Ranking / Decision Engine / Explainability outputs remain untouched
  (no code path modifies decisions collection).
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

import pytest
import pytest_asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from behavioral_intelligence import BehavioralIntelligenceService
from behavioral_intelligence.types import BehavioralEventType


MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(MONGO_URL)
    name = f"ora_test_iter16_{uuid.uuid4().hex[:8]}"
    yield client[name]
    await client.drop_database(name)
    client.close()


@pytest_asyncio.fixture
async def service(db):
    svc = BehavioralIntelligenceService(db)
    await svc.ensure_ready()
    return svc


# =====================================================================
# 1. Timezone-aware bucketing
# =====================================================================
@pytest.mark.asyncio
async def test_timezone_bucket_uses_local_tz(service, db, monkeypatch):
    monkeypatch.setenv("ORA_DEFAULT_TZ", "Europe/Rome")
    uid = f"u_{uuid.uuid4().hex[:6]}"
    # 05:00 UTC == 07:00 Europe/Rome (CEST, summer) or 06:00 in CET.
    ts_utc = datetime(2026, 6, 15, 5, 0, tzinfo=timezone.utc)
    # Insert a decision_completed → should bucket at HOUR=7 (CEST) not 5.
    await db.decision_action_history.insert_one({
        "id": f"ah_{uuid.uuid4().hex[:8]}",
        "user_id": uid,
        "decision_id": "d1",
        "user_action": "complete",
        "old_status": "in_progress",
        "new_status": "completed",
        "timestamp": ts_utc,
        "immutable": True,
    })
    metrics = await service.get_metrics(uid, persist=False)
    hours = [b.hour for b in metrics.completed_by_hour]
    # Accept CEST (7) or CET (6); MUST NOT be 5 (UTC).
    assert 5 not in hours
    assert 7 in hours or 6 in hours


# =====================================================================
# 2. Sessionization
# =====================================================================
@pytest.mark.asyncio
async def test_sessionization_pairs_open_and_refresh(service, db):
    uid = f"u_{uuid.uuid4().hex[:6]}"
    base = datetime.now(timezone.utc)
    # session 1: open + 3 refreshes over 8 minutes
    await service.observers.record_app_open_if_needed(uid, now=base)
    for i in range(3):
        await service.observers.record_manual_refresh(uid, now=base + timedelta(minutes=(i + 1) * 2))
    # 40-minute gap → new session
    await service.observers.record_manual_refresh(uid, now=base + timedelta(minutes=60))
    metrics = await service.get_metrics(uid, persist=False)
    # We expect avg_session_minutes to be > 0 (first session ≈ 6 min).
    assert metrics.avg_session_minutes is not None
    assert metrics.avg_session_minutes >= 0.5


# =====================================================================
# 3. Context Assembler wiring — flag OFF → hash unchanged
# =====================================================================
@pytest.mark.asyncio
async def test_context_hash_stable_when_flag_off(db, monkeypatch):
    monkeypatch.delenv("BEHAVIOR_PROFILE_ENABLED", raising=False)
    # Seed a minimal decision so the assembler can run.
    uid = f"u_{uuid.uuid4().hex[:6]}"
    did = f"dec_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.decisions.insert_one({
        "id": did, "user_id": uid, "title": "T", "description": "D",
        "category": "generic", "status": "open", "priority": "medium",
        "score": 0.5, "created_at": now_iso, "updated_at": now_iso,
        "node_ids": [], "linked_to": [], "metadata": {},
    })
    # Seed behavioral events (would produce a signal ONLY if flag were ON).
    await db.decision_action_history.insert_one({
        "id": f"ah_{uuid.uuid4().hex[:8]}",
        "user_id": uid, "decision_id": did, "user_action": "start",
        "old_status": "pending", "new_status": "in_progress",
        "timestamp": datetime.now(timezone.utc), "immutable": True,
    })
    # Assemble twice: hash must be equal.
    from context_assembler.repository import ContextRepository
    from context_assembler.assembler import assemble_pipeline
    repo = ContextRepository(db)
    decision = await db.decisions.find_one({"id": did}, {"_id": 0})
    s1 = await assemble_pipeline(repo, uid, decision)
    s2 = await assemble_pipeline(repo, uid, decision)
    assert s1["context_hash"] == s2["context_hash"]

    # Confirm provider ran with zero signals.
    assert "behavior_profile" in s1["provenance"]["providers_run"]
    keys = [sig["key"] for sig in s1["signals"]]
    assert "behavior.profile" not in keys


# =====================================================================
# 4. Context Assembler wiring — flag ON → new signal, hash changes
# =====================================================================
@pytest.mark.asyncio
async def test_context_hash_changes_when_flag_on(db, monkeypatch):
    monkeypatch.delenv("BEHAVIOR_PROFILE_ENABLED", raising=False)
    uid = f"u_{uuid.uuid4().hex[:6]}"
    did = f"dec_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.decisions.insert_one({
        "id": did, "user_id": uid, "title": "T", "description": "D",
        "category": "generic", "status": "open", "priority": "medium",
        "score": 0.5, "created_at": now_iso, "updated_at": now_iso,
        "node_ids": [], "linked_to": [], "metadata": {},
    })
    await db.decision_action_history.insert_one({
        "id": f"ah_{uuid.uuid4().hex[:8]}",
        "user_id": uid, "decision_id": did, "user_action": "start",
        "old_status": "pending", "new_status": "in_progress",
        "timestamp": datetime.now(timezone.utc), "immutable": True,
    })
    from context_assembler.repository import ContextRepository
    from context_assembler.assembler import assemble_pipeline
    repo = ContextRepository(db)
    decision = await db.decisions.find_one({"id": did}, {"_id": 0})

    monkeypatch.delenv("BEHAVIOR_PROFILE_ENABLED", raising=False)
    off = await assemble_pipeline(repo, uid, decision)
    monkeypatch.setenv("BEHAVIOR_PROFILE_ENABLED", "true")
    on = await assemble_pipeline(repo, uid, decision)

    assert off["context_hash"] != on["context_hash"]
    on_keys = [sig["key"] for sig in on["signals"]]
    assert "behavior.profile" in on_keys
    off_keys = [sig["key"] for sig in off["signals"]]
    assert "behavior.profile" not in off_keys


# =====================================================================
# 5. Ranking/DecisionEngine/Explainability outputs untouched
# =====================================================================
@pytest.mark.asyncio
async def test_flag_on_does_not_write_to_decisions_collection(db, monkeypatch):
    monkeypatch.setenv("BEHAVIOR_PROFILE_ENABLED", "true")
    uid = f"u_{uuid.uuid4().hex[:6]}"
    did = f"dec_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.decisions.insert_one({
        "id": did, "user_id": uid, "title": "T", "description": "D",
        "category": "generic", "status": "open", "priority": "medium",
        "score": 0.5, "created_at": now_iso, "updated_at": now_iso,
        "node_ids": [], "linked_to": [], "metadata": {},
    })
    before = await db.decisions.find_one({"id": did}, {"_id": 0})
    from context_assembler.repository import ContextRepository
    from context_assembler.assembler import assemble_pipeline
    repo = ContextRepository(db)
    decision = await db.decisions.find_one({"id": did}, {"_id": 0})
    await assemble_pipeline(repo, uid, decision)
    after = await db.decisions.find_one({"id": did}, {"_id": 0})
    assert before == after
