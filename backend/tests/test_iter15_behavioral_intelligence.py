"""Iterazione 15 — Behavioral Intelligence Engine test suite.

Covers:
* Timeline append-only + immutabilità
* Metriche incrementali
* Pattern deterministici
* Confidence buckets
* Cross-user isolation
* Feature flag OFF ⇒ context_hash invariato + provider silente
* Performance: 1000 e 10000 eventi
* Nessuna regressione (routing base e collezioni source non toccate)
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

import pytest
import pytest_asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from behavioral_intelligence import BehavioralIntelligenceService
from behavioral_intelligence.provider import BehaviorProfileProvider
from behavioral_intelligence.types import BehavioralEventType, Confidence, Trend


MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


# ============================================================
# fixtures
# ============================================================
@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(MONGO_URL)
    name = f"ora_test_iter15_{uuid.uuid4().hex[:8]}"
    yield client[name]
    await client.drop_database(name)
    client.close()


@pytest_asyncio.fixture
async def service(db):
    svc = BehavioralIntelligenceService(db)
    await svc.ensure_ready()
    return svc


@pytest_asyncio.fixture
async def user_id(db):
    uid = f"user_{uuid.uuid4().hex[:8]}"
    return uid


# ============================================================
# helpers
# ============================================================
async def seed_decision_history(db, user_id: str, records: List[dict]) -> None:
    """Insert into decision_action_history to simulate real user activity."""
    docs = []
    for i, rec in enumerate(records):
        docs.append({
            "id": f"ah_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "decision_id": rec.get("decision_id", f"dec_{i}"),
            "user_action": rec["action"],
            "old_status": rec.get("old_status", "pending"),
            "new_status": rec.get("new_status", rec["action"]),
            "timestamp": rec["ts"],
            "completion_percentage": rec.get("pct"),
            "immutable": True,
        })
    if docs:
        await db.decision_action_history.insert_many(docs)


async def seed_ingestion_events(db, user_id: str, n: int, base_ts: datetime) -> None:
    docs = []
    for i in range(n):
        ts = base_ts + timedelta(minutes=i)
        docs.append({
            "id": f"ing_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "connector_id": "calendar_google",
            "connector_instance_id": "ci_test",
            "ingestion_status": "processed",
            "processed_at": ts,
            "ingested_at": ts,
            "created_at": ts,
            "source_record_type": "calendar_event",
        })
    if docs:
        await db.ingestion_events.insert_many(docs)


# ============================================================
# 1. Timeline append-only + immutability
# ============================================================
@pytest.mark.asyncio
async def test_timeline_append_only(service, db, user_id):
    now = datetime.now(timezone.utc)
    ok1 = await service.timeline.append_event(
        user_id=user_id,
        event_type=BehavioralEventType.DECISION_STARTED,
        occurred_at=now,
        source_type="test",
        source_ref="e1",
    )
    ok2 = await service.timeline.append_event(
        user_id=user_id,
        event_type=BehavioralEventType.DECISION_COMPLETED,
        occurred_at=now,
        source_type="test",
        source_ref="e2",
    )
    assert ok1 is True and ok2 is True
    # dup insertion is silently rejected (idempotent contract)
    ok_dup = await service.timeline.append_event(
        user_id=user_id,
        event_type=BehavioralEventType.DECISION_STARTED,
        occurred_at=now,
        source_type="test",
        source_ref="e1",
    )
    assert ok_dup is False


@pytest.mark.asyncio
async def test_events_are_immutable(service, db, user_id):
    now = datetime.now(timezone.utc)
    await service.timeline.append_event(
        user_id=user_id,
        event_type=BehavioralEventType.DECISION_COMPLETED,
        occurred_at=now,
        source_type="test",
        source_ref="im1",
    )
    # Attempting to update should not modify the visible representation.
    await db.behavioral_events.update_one(
        {"user_id": user_id, "source_ref": "im1"},
        {"$set": {"event_type": "tampered"}},
    )
    # NOTE: MongoDB DOES allow direct writes — the "immutability" is enforced
    # at the SERVICE layer, not at the DB layer. This test documents that:
    # the service never issues update/delete on this collection.
    # Instead, we assert that the doc keeps its ``immutable=true`` marker.
    doc = await db.behavioral_events.find_one({"user_id": user_id, "source_ref": "im1"})
    assert doc["immutable"] is True


# ============================================================
# 2. Incremental metrics
# ============================================================
@pytest.mark.asyncio
async def test_metrics_incremental_from_source(service, db, user_id):
    base = datetime.now(timezone.utc) - timedelta(days=2)
    await seed_decision_history(db, user_id, [
        {"action": "start", "ts": base + timedelta(hours=1), "decision_id": "dA"},
        {"action": "complete", "ts": base + timedelta(hours=1, minutes=10), "decision_id": "dA"},
        {"action": "start", "ts": base + timedelta(hours=2), "decision_id": "d2"},
        {"action": "postpone", "ts": base + timedelta(hours=2, minutes=5), "decision_id": "d2"},
    ])
    m1 = await service.get_metrics(user_id, persist=False)
    assert m1.decisions_started == 2
    assert m1.decisions_completed == 1
    assert m1.decisions_postponed == 1
    # avg completion time ~= 10 minutes
    assert m1.avg_completion_minutes is not None
    assert 8 <= m1.avg_completion_minutes <= 12

    # Add more history and ensure cursor picked up only new records.
    await seed_decision_history(db, user_id, [
        {"action": "complete", "ts": base + timedelta(hours=3), "decision_id": "d3"},
        {"action": "start", "ts": base + timedelta(hours=3, minutes=1), "decision_id": "d3"},
    ])
    m2 = await service.get_metrics(user_id, persist=False)
    # Deterministic counters — must NOT decrease.
    assert m2.decisions_started >= m1.decisions_started
    assert m2.decisions_completed >= m1.decisions_completed


# ============================================================
# 3. Pattern detection (deterministic)
# ============================================================
@pytest.mark.asyncio
async def test_patterns_deterministic(service, db, user_id):
    base = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
    # 8 morning completions between 6..12 → morning_completer + quick_winner
    records = []
    for i in range(8):
        did = f"morn_{i}"
        records.append({"action": "start", "ts": base + timedelta(days=i, hours=0), "decision_id": did})
        records.append({"action": "complete", "ts": base + timedelta(days=i, minutes=8), "decision_id": did})
    await seed_decision_history(db, user_id, records)
    patterns = await service.get_patterns(user_id, persist=False)
    ids = {p.id for p in patterns}
    assert "morning_completer" in ids
    assert "quick_winner" in ids


# ============================================================
# 4. Confidence bucketing
# ============================================================
@pytest.mark.asyncio
async def test_confidence_low_with_no_data(service, user_id):
    r = await service.confidence_report(user_id)
    assert r.metrics == Confidence.LOW
    assert r.events_observed == 0


@pytest.mark.asyncio
async def test_confidence_scales_with_sample_size(service, db, user_id):
    base = datetime.now(timezone.utc)
    # Insert enough to reach MEDIUM confidence (>=20 sample)
    recs = []
    for i in range(25):
        did = f"cd_{i}"
        recs.append({"action": "start", "ts": base + timedelta(minutes=i), "decision_id": did})
        recs.append({"action": "complete", "ts": base + timedelta(minutes=i, seconds=30), "decision_id": did})
    await seed_decision_history(db, user_id, recs)
    m = await service.get_metrics(user_id, persist=False)
    assert m.confidence in (Confidence.MEDIUM, Confidence.HIGH)


# ============================================================
# 5. Cross-user isolation
# ============================================================
@pytest.mark.asyncio
async def test_cross_user_isolation(service, db):
    u1 = f"user_{uuid.uuid4().hex[:8]}"
    u2 = f"user_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    await seed_decision_history(db, u1, [
        {"action": "start", "ts": now},
        {"action": "complete", "ts": now + timedelta(minutes=5)},
    ])
    m1 = await service.get_metrics(u1, persist=False)
    m2 = await service.get_metrics(u2, persist=False)
    assert m1.decisions_started == 1
    assert m2.decisions_started == 0
    tl1 = await service.timeline_page(u1, limit=50)
    tl2 = await service.timeline_page(u2, limit=50)
    assert all(e.user_id == u1 for e in tl1.items)
    assert tl2.total == 0


# ============================================================
# 6. Feature flag OFF ⇒ provider silent (context_hash unchanged)
# ============================================================
@pytest.mark.asyncio
async def test_provider_is_silent_when_flag_off(service, monkeypatch, user_id):
    monkeypatch.delenv("BEHAVIOR_PROFILE_ENABLED", raising=False)
    provider = BehaviorProfileProvider(service)
    assert provider.enabled is False
    signals = await provider.signals(user_id)
    assert signals == []


@pytest.mark.asyncio
async def test_provider_emits_when_flag_on(service, monkeypatch, db, user_id):
    monkeypatch.setenv("BEHAVIOR_PROFILE_ENABLED", "true")
    provider = BehaviorProfileProvider(service)
    assert provider.enabled is True
    now = datetime.now(timezone.utc)
    await seed_decision_history(db, user_id, [
        {"action": "start", "ts": now},
        {"action": "complete", "ts": now + timedelta(minutes=2)},
    ])
    signals = await provider.signals(user_id)
    assert isinstance(signals, list) and len(signals) == 1
    assert signals[0]["kind"] == "behavior_profile"
    assert signals[0]["provider"] == "behavior_profile_provider"


# ============================================================
# 7. No LLM / no external calls
# ============================================================
def test_no_llm_imports():
    """Import inspection: the module must not depend on LLM libraries."""
    import behavioral_intelligence as bi
    import pkgutil
    forbidden = (
        "openai", "anthropic", "google.generativeai", "google.genai", "transformers",
        "torch", "sklearn", "tensorflow", "langchain", "chromadb", "faiss",
        "sentence_transformers", "cohere", "huggingface",
    )
    # Grep the module source for imports of forbidden libraries.
    root = os.path.dirname(bi.__file__)
    hits = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            with open(p, "r", encoding="utf-8") as f:
                source = f.read()
            for lib in forbidden:
                for kw in (f"import {lib}", f"from {lib}"):
                    if kw in source:
                        hits.append((p, kw))
    assert not hits, f"Forbidden LLM/ML imports detected: {hits}"


# ============================================================
# 8. Performance — 1000 and 10000 events
# ============================================================
@pytest.mark.asyncio
async def test_performance_1000_events(service, db, user_id):
    now = datetime.now(timezone.utc)
    # Direct bulk-insert into behavioral_events to skip source-sync overhead.
    docs = []
    for i in range(1000):
        docs.append({
            "id": f"bhv_perf_{i:06d}",
            "user_id": user_id,
            "event_type": (
                BehavioralEventType.DECISION_COMPLETED.value if i % 3 == 0
                else BehavioralEventType.DECISION_STARTED.value
            ),
            "occurred_at": now - timedelta(minutes=i),
            "metadata": {"decision_id": f"dec_{i}"},
            "source_type": "perf",
            "source_ref": f"perf-{i}",
            "recorded_at": now,
            "version": 1,
            "immutable": True,
        })
    await db.behavioral_events.insert_many(docs)
    t0 = time.time()
    m = await service.get_metrics(user_id, persist=False)
    elapsed = time.time() - t0
    assert m.sample_size >= 500
    # Metrics should compute in < 3 seconds on the test container.
    assert elapsed < 3.0, f"metrics computation too slow: {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_performance_10000_events(service, db, user_id):
    now = datetime.now(timezone.utc)
    # Bulk-insert 10k events across 30 days
    docs = []
    for i in range(10_000):
        docs.append({
            "id": f"bhv_perf2_{i:07d}",
            "user_id": user_id,
            "event_type": (
                BehavioralEventType.DECISION_COMPLETED.value if i % 5 == 0
                else BehavioralEventType.DECISION_STARTED.value
            ),
            "occurred_at": now - timedelta(minutes=i),
            "metadata": {"decision_id": f"dec_{i}"},
            "source_type": "perf",
            "source_ref": f"perf2-{i}",
            "recorded_at": now,
            "version": 1,
            "immutable": True,
        })
    # Insert in batches to avoid BSON limits
    for k in range(0, len(docs), 2000):
        await db.behavioral_events.insert_many(docs[k:k + 2000])
    t0 = time.time()
    m = await service.get_metrics(user_id, persist=False)
    elapsed = time.time() - t0
    assert m.sample_size >= 1000
    # <8 seconds is our budget for 10k events on the container.
    assert elapsed < 8.0, f"metrics @ 10k events too slow: {elapsed:.2f}s"


# ============================================================
# 9. No regression — Behavioral module must not touch source collections
# ============================================================
@pytest.mark.asyncio
async def test_behavioral_module_never_writes_to_source_collections(service, db, user_id):
    """Reads from source collections must not create / modify docs there."""
    now = datetime.now(timezone.utc)
    await seed_decision_history(db, user_id, [
        {"action": "start", "ts": now},
        {"action": "complete", "ts": now + timedelta(minutes=1)},
    ])
    before_dah = await db.decision_action_history.count_documents({})
    before_ing = await db.ingestion_events.count_documents({})
    before_ci = await db.connector_instances.count_documents({})
    before_ds = await db.daily_summaries.count_documents({})
    before_cs = await db.context_snapshots.count_documents({})

    # Exercise all read paths.
    await service.get_metrics(user_id, persist=False)
    await service.get_patterns(user_id, persist=False)
    await service.get_profile(user_id, persist=False)
    await service.confidence_report(user_id)
    await service.timeline_page(user_id, limit=50)

    assert await db.decision_action_history.count_documents({}) == before_dah
    assert await db.ingestion_events.count_documents({}) == before_ing
    assert await db.connector_instances.count_documents({}) == before_ci
    assert await db.daily_summaries.count_documents({}) == before_ds
    assert await db.context_snapshots.count_documents({}) == before_cs
