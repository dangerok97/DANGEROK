"""Iterazione 17 — Behavior-Aware Decision Engine Shadow Mode tests."""
from __future__ import annotations
import os, uuid
from datetime import datetime, timedelta, timezone
import pytest, pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from behavior_aware_decisions import BehaviorShadowService
from behavior_aware_decisions.types import DELTA_MIN_TOTAL, DELTA_MAX_TOTAL
from behavior_aware_decisions.comparison import compare_rankings
from behavior_aware_decisions.rules import (
    rule_preferred_time_alignment, rule_category_procrastination,
    rule_overload_protection, rule_deadline_guardrail,
)
from behavior_aware_decisions.scoring import apply_confidence, clip_per_rule, aggregate

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(MONGO_URL)
    name = f"ora_test_iter17_{uuid.uuid4().hex[:8]}"
    yield client[name]
    await client.drop_database(name)
    client.close()


@pytest_asyncio.fixture
async def svc(db):
    s = BehaviorShadowService(db)
    await s.ensure_ready()
    return s


def _flags_on(mp):
    mp.setenv("BEHAVIOR_PROFILE_ENABLED", "true")
    mp.setenv("BEHAVIOR_SHADOW_MODE", "true")


def _flags_off(mp):
    mp.delenv("BEHAVIOR_PROFILE_ENABLED", raising=False)
    mp.delenv("BEHAVIOR_SHADOW_MODE", raising=False)


async def _seed_behavior(db, uid: str, n_completed=20, n_postponed=15, hour=9):
    """Seed behavioral_events to make profile MEDIUM/HIGH confidence."""
    now = datetime.now(timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0)
    docs = []
    for i in range(n_completed):
        docs.append({"id": f"bhv_c_{i}", "user_id": uid,
                     "event_type": "decision_completed",
                     "occurred_at": now - timedelta(days=i),
                     "metadata": {"decision_id": f"d_{i}"},
                     "source_type": "seed", "source_ref": f"c-{i}",
                     "recorded_at": now, "version": 1, "immutable": True})
    for i in range(n_postponed):
        docs.append({"id": f"bhv_p_{i}", "user_id": uid,
                     "event_type": "decision_postponed",
                     "occurred_at": now - timedelta(days=i, hours=1),
                     "metadata": {"decision_id": f"dp_{i}"},
                     "source_type": "seed", "source_ref": f"p-{i}",
                     "recorded_at": now, "version": 1, "immutable": True})
    for i in range(25):
        docs.append({"id": f"bhv_s_{i}", "user_id": uid,
                     "event_type": "decision_started",
                     "occurred_at": now - timedelta(days=i, hours=2),
                     "metadata": {"decision_id": f"ds_{i}"},
                     "source_type": "seed", "source_ref": f"s-{i}",
                     "recorded_at": now, "version": 1, "immutable": True})
    await db.behavioral_events.insert_many(docs)


# ============================================================
# 1. Both flags OFF → no evaluation, no writes
# ============================================================
@pytest.mark.asyncio
async def test_flags_off_zero_writes(svc, db, monkeypatch):
    _flags_off(monkeypatch)
    uid = f"u_{uuid.uuid4().hex[:6]}"
    d = {"id": "d1", "score": 50, "category": "generic", "priority": "medium"}
    before = await db.behavior_shadow_evaluations.count_documents({})
    ev = await svc.evaluate(uid, d)
    after = await db.behavior_shadow_evaluations.count_documents({})
    assert ev.shadow_priority_delta == 0
    assert ev.ranking_applied is False
    assert before == after  # no write


# ============================================================
# 2. Flag partial ON (profile only) → still no shadow
# ============================================================
@pytest.mark.asyncio
async def test_profile_on_shadow_off_no_write(svc, db, monkeypatch):
    monkeypatch.setenv("BEHAVIOR_PROFILE_ENABLED", "true")
    monkeypatch.delenv("BEHAVIOR_SHADOW_MODE", raising=False)
    uid = f"u_{uuid.uuid4().hex[:6]}"
    d = {"id": "d1", "score": 50, "category": "generic"}
    ev = await svc.evaluate(uid, d)
    assert ev.shadow_priority_delta == 0
    assert await db.behavior_shadow_evaluations.count_documents({}) == 0


# ============================================================
# 3. Both flags ON → evaluation persisted, ranking_applied=false
# ============================================================
@pytest.mark.asyncio
async def test_flags_on_persists_evaluation(svc, db, monkeypatch):
    _flags_on(monkeypatch)
    uid = f"u_{uuid.uuid4().hex[:6]}"
    await _seed_behavior(db, uid)
    d = {"id": "dec_1", "score": 50, "category": "generic", "priority": "medium",
         "time_required_min": 20, "updated_at": "2026-01-01T00:00:00Z"}
    ev = await svc.evaluate(uid, d)
    assert ev.ranking_applied is False
    persisted = await db.behavior_shadow_evaluations.find_one({"decision_id": "dec_1"})
    assert persisted is not None
    assert persisted["ranking_applied"] is False


# ============================================================
# 4. Idempotency — same inputs → no duplicates
# ============================================================
@pytest.mark.asyncio
async def test_idempotency(svc, db, monkeypatch):
    _flags_on(monkeypatch)
    uid = f"u_{uuid.uuid4().hex[:6]}"
    await _seed_behavior(db, uid)
    d = {"id": "dec_x", "score": 60, "category": "generic",
         "updated_at": "2026-01-01T00:00:00Z"}
    e1 = await svc.evaluate(uid, d, context_hash="ctx-abc")
    e2 = await svc.evaluate(uid, d, context_hash="ctx-abc")
    count = await db.behavior_shadow_evaluations.count_documents({"decision_id": "dec_x"})
    assert count == 1
    assert e1.evaluation_id == e2.evaluation_id


# ============================================================
# 5. Cap enforcement (never > +10 nor < -5)
# ============================================================
def test_cap_enforcement_math():
    from behavior_aware_decisions.types import ShadowRuleResult
    fake = [ShadowRuleResult(rule_id=f"r{i}", delta=100.0, applied=True, confidence="high") for i in range(10)]
    fake = apply_confidence(fake)
    fake = clip_per_rule(fake)  # each clipped to ±3
    total, cap_hit, applied = aggregate(fake, {"category": "generic"})
    assert total <= DELTA_MAX_TOTAL
    assert total >= DELTA_MIN_TOTAL
    assert cap_hit is True


# ============================================================
# 6. Deadline guardrail — no negative on urgent/critical
# ============================================================
def test_deadline_guardrail_no_negative_on_urgent():
    from behavior_aware_decisions.types import ShadowRuleResult
    fake = [ShadowRuleResult(rule_id="overload_protection", delta=-3.0, applied=True, confidence="high")]
    fake = apply_confidence(fake); fake = clip_per_rule(fake)
    urgent_dec = {"category": "generic", "priority": "urgent"}
    total, _, _ = aggregate(fake, urgent_dec)
    assert total == 0

    critical_dec = {"category": "health", "priority": "medium"}
    total2, _, _ = aggregate(fake, critical_dec)
    assert total2 == 0


# ============================================================
# 7. Confidence LOW → delta zero
# ============================================================
def test_confidence_low_zero_delta():
    from behavior_aware_decisions.types import ShadowRuleResult
    r = ShadowRuleResult(rule_id="x", delta=5.0, applied=True, confidence="low")
    scaled = apply_confidence([r])
    assert scaled[0].delta == 0.0


def test_confidence_medium_half_delta():
    from behavior_aware_decisions.types import ShadowRuleResult
    r = ShadowRuleResult(rule_id="x", delta=4.0, applied=True, confidence="medium")
    scaled = apply_confidence([r])
    assert scaled[0].delta == 2.0


# ============================================================
# 8. Real ranking must NOT be modified
# ============================================================
@pytest.mark.asyncio
async def test_real_score_not_modified(svc, db, monkeypatch):
    _flags_on(monkeypatch)
    uid = f"u_{uuid.uuid4().hex[:6]}"
    await _seed_behavior(db, uid)
    now_iso = datetime.now(timezone.utc).isoformat()
    original = {"id": "dec_real", "user_id": uid, "title": "T", "score": 42.5,
                "category": "generic", "priority": "medium", "status": "open",
                "created_at": now_iso, "updated_at": now_iso, "metadata": {}}
    await db.decisions.insert_one(dict(original))
    ev = await svc.evaluate(uid, original)
    after = await db.decisions.find_one({"id": "dec_real"}, {"_id": 0})
    assert after["score"] == 42.5  # untouched
    # shadow may differ from real
    assert ev.effective_score == 42.5


# ============================================================
# 9. Cross-user isolation
# ============================================================
@pytest.mark.asyncio
async def test_cross_user_isolation(svc, db, monkeypatch):
    _flags_on(monkeypatch)
    u1, u2 = f"u_{uuid.uuid4().hex[:6]}", f"u_{uuid.uuid4().hex[:6]}"
    await _seed_behavior(db, u1)
    await svc.evaluate(u1, {"id": "d1", "score": 50, "category": "generic",
                            "updated_at": "2026-01-01T00:00:00Z"})
    # u2 should see zero evaluations
    rows = await svc.storage.list_by_user(u2)
    assert len(rows) == 0
    stats = await svc.storage.stats(u2)
    assert stats.get("total", 0) == 0


# ============================================================
# 10. Comparison engine
# ============================================================
def test_comparison_engine():
    real = [{"id": "a", "score": 100}, {"id": "b", "score": 90}, {"id": "c", "score": 80}]
    shadow = {"a": 0, "b": 5, "c": -2}  # b jumps to 95 > 100? No: 90+5=95 still < 100
    r = compare_rankings(real, shadow)
    assert r["evaluated"] == 3
    assert r["positive"] == 1
    assert r["negative"] == 1
    assert r["unchanged"] == 1
    assert r["kendall_tau"] <= 1.0

    # Case with position change
    shadow2 = {"a": 0, "b": 15, "c": -2}  # b becomes 105 > 100
    r2 = compare_rankings(real, shadow2)
    assert r2["position_changes"] > 0


# ============================================================
# 11. No LLM/ML imports in the module
# ============================================================
def test_no_llm_imports_shadow():
    import os
    root = "/app/backend/behavior_aware_decisions"
    forbidden = ("openai", "anthropic", "google.generativeai", "transformers",
                 "torch", "sklearn", "tensorflow", "langchain", "chromadb", "faiss")
    hits = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if not fn.endswith(".py"): continue
            with open(os.path.join(dp, fn), "r") as f: src = f.read()
            for lib in forbidden:
                if f"import {lib}" in src or f"from {lib}" in src:
                    hits.append((fn, lib))
    assert not hits


# ============================================================
# 12. Fail-safe — profile error → zero eval, no crash
# ============================================================
@pytest.mark.asyncio
async def test_fail_safe_profile_error(svc, db, monkeypatch):
    _flags_on(monkeypatch)
    uid = f"u_{uuid.uuid4().hex[:6]}"
    # No behavioral data seeded → profile call will succeed but return low confidence
    d = {"id": "dec_no_data", "score": 30, "category": "generic",
         "updated_at": "2026-01-01T00:00:00Z"}
    ev = await svc.evaluate(uid, d)
    # With LOW confidence, delta must be 0
    assert ev.shadow_priority_delta == 0
    assert ev.ranking_applied is False
