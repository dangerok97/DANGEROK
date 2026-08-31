"""
V3.8 Sprint 3 — the safety net, and what happens after the lights come back on.

    ORA DOES NOT NEED THE USER TO WAKE IT UP.
    BUT ORA ALSO DOES NOT WAKE ITSELF WITHOUT A REASON.

Everything upstream is event-driven, and event-driven systems lose things.
This sprint adds the net that catches what they drop — and almost every test
here exists to stop that net from becoming the thing it was built to avoid.

The failure mode is specific and seductive: an hourly job that builds a
snapshot for everybody and asks a model what it thinks. It would work, it
would look diligent, and it would cost a fortune while quietly moving the
judgement out of the model and into a scheduler. So the checker counts and
never reasons, a life with nothing in it produces nothing at all, and what
eligibility produces is a wake — an alarm the ordinary pipeline handles, not
a conclusion.

The other half is the morning after four hours of downtime, where the wrong
answer is five notifications in one minute about things that were true last
night.
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in (
        "ambient_wakes", "ambient_locks", "ambient_fallback_state", "ambient_activity",
        "push_endpoints", "app_presence", "delivery_plans", "notification_preferences",
        "delivery_suppressions", "opportunities", "opportunity_decisions",
        "meaningful_changes", "opportunity_scan_state", "calendar_events",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


async def _release_lock(db):
    await db.ambient_locks.delete_many({"name": "ambient_sweep"})


class FakeModel:
    def __init__(self, answers):
        self.answers = list(answers)
        self.seen = []

    async def __call__(self, system, user):
        self.seen.append({"system": system, "user": user})
        return self.answers.pop(0) if self.answers else None


def _install(monkeypatch, model):
    import delivery.reasoning as delivery_reasoning
    import opportunities.reasoning as opportunity_reasoning

    monkeypatch.setattr(delivery_reasoning, "_ask_model", model)
    monkeypatch.setattr(opportunity_reasoning, "_ask_model", model)


class Provider:
    name = "test"

    def __init__(self):
        self.sent = []
        self.cancelled = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return {"ok": True, "provider": self.name}

    async def cancel(self, *, owner_id, plan_id):
        self.cancelled.append(plan_id)
        return {"ok": True, "retracted": False}


def _provider(monkeypatch) -> Provider:
    from delivery import provider as provider_module

    channel = Provider()
    monkeypatch.setattr(provider_module, "get_provider", lambda: channel)
    return channel


async def _allow_push(allowed=True):
    import delivery.context as context_module

    async def _permission(_db, _uid, _now):
        return {"push": allowed}

    context_module._permission = _permission  # noqa: SLF001


async def _an_opportunity(db, uid, **over):
    from opportunities.models import EvidenceRef, Opportunity
    from opportunities.repository import OpportunityRepository

    fields = {
        "owner_id": uid,
        "identity_key": f"cosa-{uuid.uuid4().hex[:6]}",
        "status": "active",
        "semantic_summary": "Manca il certificato per l'appuntamento.",
        "why_it_matters": "Senza, non si conclude.",
        "relevance": "high",
        "urgency": "soon",
        "confidence": "strong",
        "evidence": [EvidenceRef(kind="calendar_event", ref="evt_x")],
    }
    fields.update(over)
    opportunity = Opportunity(**fields)
    await OpportunityRepository(db).save(opportunity)
    return opportunity


async def _a_plan(db, uid, opportunity, **over):
    from delivery.models import DeliveryPlan, PushCopy
    from delivery.service import DeliveryService

    fields = {
        "owner_id": uid,
        "opportunity_id": opportunity.id,
        "mode": "push",
        "status": "pending",
        "words": PushCopy(title="t", body="b"),
        "deep_link": f"/ora?opportunityId={opportunity.id}&entry=notification",
    }
    fields.update(over)
    plan = DeliveryPlan(**fields)
    await DeliveryService(db).repo.save_plan(plan)
    return plan


# ---------------------------------------------------------------------------
# The small question
# ---------------------------------------------------------------------------

def test_a_life_with_nothing_in_it_costs_nothing(monkeypatch):
    """
    §5/§40: EMPTY USER = ZERO AI.

    The whole safety net is affordable only if this is true. Somebody with no
    concerns, no plans and nothing pending must produce no wake, no activity
    and no inference — and the checker must not even be tempted, because it
    has no way to reach a model at all.
    """
    async def body():
        client, db = await _db()
        uid = f"r38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.eligibility import EligibilityService

            model = FakeModel([{"mode": "push"}, {"worth_saying": True, "line": "x"}])
            _install(monkeypatch, model)
            await _release_lock(db)

            service = EligibilityService(db)
            assert await service.reasons_to_look_again(uid) == []
            assert await service.eligible(uid) is False

            await service.sweep()

            assert model.seen == [], "il fallback ha pensato a qualcuno che non aveva niente"
            assert await db.ambient_wakes.count_documents({"owner_id": uid}) == 0
            assert await db.ambient_activity.count_documents({"owner_id": uid}) == 0
            assert await db.delivery_plans.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            await _release_lock(db)
            client.close()

    _run(body())


def test_every_reason_to_look_again_is_a_fact_and_not_a_judgement(monkeypatch):
    """Each one is a count against an index; none of them means anything yet."""
    async def body():
        client, db = await _db()
        uid = f"r38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.eligibility import EligibilityService
            from opportunities.discovery import OpportunityDiscovery

            service = EligibilityService(db)
            assert await service.reasons_to_look_again(uid) == []

            # A concern with a clock on it.
            soon = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
            await _an_opportunity(db, uid, valid_until=soon)
            assert "temporal_window" in await service.reasons_to_look_again(uid)

            # Something still intending to arrive.
            opportunity = await _an_opportunity(db, uid)
            await _a_plan(db, uid, opportunity)
            assert "delivery_pending" in await service.reasons_to_look_again(uid)

            # Something moved and nobody read it.
            await OpportunityDiscovery(db).changes.record(
                uid, source="calendar", kind="event.updated", entity_ref="evt_z"
            )
            assert "changes_unprocessed" in await service.reasons_to_look_again(uid)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_wake_that_was_missed_is_a_reason_to_look(monkeypatch):
    """§7: the lost-wake case, which is what a safety net is for."""
    async def body():
        client, db = await _db()
        uid = f"r38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.eligibility import EligibilityService, OVERDUE_MINUTES
            from ambient.models import AmbientWake
            from ambient.repository import AmbientRepository

            await AmbientRepository(db).ensure_indexes()
            long_ago = (
                datetime.now(timezone.utc) - timedelta(minutes=OVERDUE_MINUTES + 30)
            ).isoformat()
            await AmbientRepository(db).schedule(AmbientWake(
                owner_id=uid, reason="delivery_recheck", scheduled_for=long_ago
            ))

            assert "wake_overdue" in await EligibilityService(db).reasons_to_look_again(uid)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_fallback_asks_for_a_review_and_never_performs_one(monkeypatch):
    """
    §6/§41: eligibility produces a wake, not a conclusion.

    The distinction is the whole architecture. A checker that reasoned would
    be a second, parallel brain running on a timer — with none of the
    coalescing, dedupe or cost guards the real pipeline has.
    """
    async def body():
        client, db = await _db()
        uid = f"r38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.eligibility import EligibilityService
            from ambient.repository import AmbientRepository

            await AmbientRepository(db).ensure_indexes()
            await _release_lock(db)
            model = FakeModel([{"mode": "push"}])
            _install(monkeypatch, model)

            soon = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
            await _an_opportunity(db, uid, valid_until=soon)

            result = await EligibilityService(db).sweep()
            assert result["ran"] is True
            assert result["eligible"] >= 1
            assert model.seen == [], "il checker ha chiamato il modello"

            wakes = await AmbientRepository(db).open_wakes(uid)
            assert len(wakes) == 1
            assert wakes[0].reason == "ambient_review"
            assert "temporal_window" in wakes[0].source_ref
        finally:
            await _clean(db, uid)
            await _release_lock(db)
            client.close()

    _run(body())


def test_two_instances_sweeping_together_do_the_work_once(monkeypatch):
    """§36/§42: one lease, in the database, like every other claim here."""
    async def body():
        client, db = await _db()
        uid = f"r38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.eligibility import EligibilityService
            from ambient.repository import AmbientRepository

            await AmbientRepository(db).ensure_indexes()
            await EligibilityService(db).ensure_indexes()
            await _release_lock(db)
            soon = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
            await _an_opportunity(db, uid, valid_until=soon)

            results = await asyncio.gather(*[
                EligibilityService(db).sweep() for _ in range(4)
            ])
            ran = [r for r in results if r.get("ran")]
            assert len(ran) == 1, f"{len(ran)} istanze hanno spazzato insieme"

            assert await db.ambient_wakes.count_documents(
                {"owner_id": uid, "status": "pending"}
            ) == 1
        finally:
            await _clean(db, uid)
            await _release_lock(db)
            client.close()

    _run(body())


def test_a_permanently_eligible_person_is_not_checked_every_few_minutes(monkeypatch):
    """
    §35: NO CRON EXPLOSION.

    Somebody with a long-lived concern is eligible all week. Without a
    per-person interval the sweep would arrange a review on every pass.
    """
    async def body():
        client, db = await _db()
        uid = f"r38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.eligibility import EligibilityService
            from ambient.repository import AmbientRepository

            await AmbientRepository(db).ensure_indexes()
            await EligibilityService(db).ensure_indexes()
            soon = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
            await _an_opportunity(db, uid, valid_until=soon)

            # The clock advances between sweeps, so the wake identity — which
            # is bucketed to the minute — would not dedupe them. What has to
            # stop the second, third and fourth is the per-person interval,
            # and nothing else.
            start = datetime.now(timezone.utc)
            for minutes in (0, 7, 21, 44):
                await _release_lock(db)
                await EligibilityService(db).sweep(now=start + timedelta(minutes=minutes))

            assert await db.ambient_wakes.count_documents({"owner_id": uid}) == 1, (
                "una revisione per ogni passata"
            )
        finally:
            await _clean(db, uid)
            await _release_lock(db)
            client.close()

    _run(body())


def test_the_sweep_never_walks_everybody(monkeypatch):
    """
    §38: the candidate set comes from state, not from the user table.

    A product with a hundred thousand people, three of whom have anything
    pending, must cost three.
    """
    from ambient import eligibility

    source = (HERE / "ambient" / "eligibility.py").read_text(encoding="utf-8")
    candidates = source.split("async def _candidates")[1].split("async def")[0]
    assert "users" not in candidates, "il fallback parte dalla tabella utenti"
    for collection in ("delivery_plans", "ambient_wakes", "meaningful_changes", "opportunities"):
        assert collection in candidates
    assert "distinct" in candidates


# ---------------------------------------------------------------------------
# The morning after
# ---------------------------------------------------------------------------

def test_leases_held_by_workers_that_no_longer_exist_are_released(monkeypatch):
    """§32/§34: a deterministic startup pass, with no model anywhere in it."""
    async def body():
        client, db = await _db()
        uid = f"r38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.eligibility import recover_after_downtime
            from ambient.models import AmbientWake
            from ambient.repository import AmbientRepository

            repo = AmbientRepository(db)
            await repo.ensure_indexes()
            long_ago = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
            wake = AmbientWake(
                owner_id=uid, reason="delivery_recheck", scheduled_for=long_ago,
                status="claimed", worker_id="ghost", lease_until=long_ago,
                claimed_at=long_ago,
            )
            await repo.schedule(wake)

            model = FakeModel([{"mode": "push"}])
            _install(monkeypatch, model)
            recovered = await recover_after_downtime(db)

            assert recovered["leases_released"] >= 1
            assert model.seen == [], "il recupero ha chiamato il modello"

            refreshed = await db.ambient_wakes.find_one({"id": wake.id}, {"_id": 0})
            assert refreshed["status"] == "pending"
            assert refreshed["worker_id"] == ""
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_plan_whose_moment_passed_during_downtime_is_expired_not_fired(monkeypatch):
    """A notification that arrives four hours late is worse than none."""
    async def body():
        client, db = await _db()
        uid = f"r38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.eligibility import recover_after_downtime

            channel = _provider(monkeypatch)
            opportunity = await _an_opportunity(db, uid)
            past = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
            plan = await _a_plan(
                db, uid, opportunity,
                not_before=(datetime.now(timezone.utc) - timedelta(hours=4)).isoformat(),
                not_after=past,
            )

            await recover_after_downtime(db)

            stored = await db.delivery_plans.find_one({"id": plan.id}, {"_id": 0})
            assert stored["status"] == "expired"
            assert stored["decision_provenance"] == "code_expiry"
            assert channel.sent == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_downtime_does_not_become_a_burst(monkeypatch):
    """
    §33/§44: NO CATCH-UP SPAM.

    Three plans came due while the process was away, each one correct at the
    time. The wrong answer is three notifications in one minute. The right one
    is that each is re-examined and the technical ceiling still applies —
    which is what stops a restart from being the worst moment of somebody's
    week.
    """
    async def body():
        client, db = await _db()
        uid = f"r38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.models import AmbientWake
            from ambient.repository import AmbientRepository
            from ambient.runtime import tick
            from delivery.service import MAX_PUSHES_PER_HOUR

            repo = AmbientRepository(db)
            await repo.ensure_indexes()
            channel = _provider(monkeypatch)
            await _allow_push(True)

            past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            for _ in range(3):
                opportunity = await _an_opportunity(db, uid)
                plan = await _a_plan(db, uid, opportunity, not_before=past)
                await repo.schedule(AmbientWake(
                    owner_id=uid, reason="delivery_recheck", scheduled_for=past,
                    opportunity_id=opportunity.id, delivery_plan_id=plan.id,
                ))

            _install(monkeypatch, FakeModel([
                {"mode": "push", "timing": "now", "reason_to_interrupt": "r",
                 "reason_to_open": "o", "copy": {"title": "t", "body": "b"}}
                for _ in range(6)
            ]))

            await tick(db, limit=10)

            assert len(channel.sent) <= MAX_PUSHES_PER_HOUR, (
                f"{len(channel.sent)} notifiche in una raffica dopo il riavvio"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_missed_wake_is_still_re_examined_before_anything_is_sent(monkeypatch):
    """§43: overdue is not permission. The recheck happens either way."""
    async def body():
        client, db = await _db()
        uid = f"r38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.models import AmbientWake
            from ambient.repository import AmbientRepository
            from ambient.runtime import tick
            from opportunities.repository import OpportunityRepository

            repo = AmbientRepository(db)
            await repo.ensure_indexes()
            channel = _provider(monkeypatch)
            await _allow_push(True)

            past = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
            opportunity = await _an_opportunity(db, uid)
            plan = await _a_plan(db, uid, opportunity, not_before=past)
            await repo.schedule(AmbientWake(
                owner_id=uid, reason="delivery_recheck", scheduled_for=past,
                opportunity_id=opportunity.id, delivery_plan_id=plan.id,
            ))

            # Dealt with while the lights were off.
            opportunity.status = "resolved"
            await OpportunityRepository(db).save(opportunity)

            model = FakeModel([{"mode": "push"}])
            _install(monkeypatch, model)
            await tick(db)

            assert channel.sent == [], "ha inviato al buio una cosa già risolta"
            assert model.seen == [], "ha speso una chiamata per una cosa chiusa"
            stored = await db.delivery_plans.find_one({"id": plan.id}, {"_id": 0})
            assert stored["status"] == "cancelled"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_fallback_that_found_nothing_leaves_no_trace(monkeypatch):
    """
    §30: NO BACKGROUND THEATRE.

    The net was cast and caught nothing. Saying "ho controllato tutto" would
    be a lie about work that did not happen — and the kind nobody files a bug
    about.
    """
    async def body():
        client, db = await _db()
        uid = f"r38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.eligibility import EligibilityService
            from delivery.service import DeliveryService

            await _release_lock(db)
            _install(monkeypatch, FakeModel([{"worth_saying": True, "line": "Ho controllato tutto."}]))

            before = await db.ambient_activity.count_documents({})
            await EligibilityService(db).sweep()
            after = await db.ambient_activity.count_documents({})

            assert after == before, "il fallback ha lasciato una traccia senza lavorare"
            assert await DeliveryService(db).ambient_line(uid) is None
        finally:
            await _clean(db, uid)
            await _release_lock(db)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def _source(*parts) -> str:
    return HERE.joinpath(*parts).read_text(encoding="utf-8")


def _code_only(text: str) -> str:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False):
                node.body = node.body[1:]
    stripped = ast.unparse(tree)
    return "\n".join(
        "" if line.strip().startswith("#") else line.split("#")[0]
        for line in stripped.splitlines()
    )


def test_the_checker_has_no_way_to_reach_a_model():
    """
    §2/§55: the guard that keeps the safety net from becoming a cron AI.

    Not "it does not call a model today" — it cannot. Nothing in the file
    imports reasoning, and the day somebody adds it, this fails.
    """
    code = _code_only(_source("ambient", "eligibility.py"))
    for forbidden in (
        "_ask_model", "decide_delivery", "reasoning", "decide_surfacing",
        "summarise_recent", "note_activity", "get_provider", "snapshot",
    ):
        assert forbidden not in code, f"il checker conosce {forbidden}"

    # And what it produces is an alarm, not an answer.
    assert "schedule(" in code
    assert "ambient_review" in code


def test_how_often_the_system_looks_and_how_often_a_person_is_looked_at_are_two_settings():
    """
    §8: two different things that used to be one, and should not have been.

    The sweep cadence bounds how long a lost event can go unnoticed — it is
    about the system noticing. The per-person interval bounds how often any
    one life is looked at again. Sharing a value meant turning one down
    silently changed the other, and neither name said which was which.
    """
    from ambient import eligibility

    assert eligibility.SWEEP_INTERVAL_HOURS >= 0.5, "lo sweep è diventato un polling"
    assert eligibility.PER_USER_INTERVAL_HOURS >= 1
    assert eligibility.SWEEP_INTERVAL_HOURS != eligibility.PER_USER_INTERVAL_HOURS, (
        "i due intervalli sono di nuovo lo stesso numero"
    )

    code = _source("ambient", "eligibility.py")
    assert "AMBIENT_FALLBACK_SWEEP_INTERVAL_HOURS" in code
    assert "AMBIENT_FALLBACK_USER_INTERVAL_HOURS" in code
    assert "AMBIENT_FALLBACK_INTERVAL_HOURS" not in code, "la vecchia config è rimasta"


def test_moving_one_interval_does_not_move_the_other(monkeypatch):
    """Independent by construction, not by convention."""
    import importlib

    from ambient import eligibility

    monkeypatch.setenv("AMBIENT_FALLBACK_SWEEP_INTERVAL_HOURS", "6")
    monkeypatch.setenv("AMBIENT_FALLBACK_USER_INTERVAL_HOURS", "12")
    reloaded = importlib.reload(eligibility)
    try:
        assert reloaded.SWEEP_INTERVAL_HOURS == 6
        assert reloaded.PER_USER_INTERVAL_HOURS == 12
        # The window a closing concern is judged against follows the per-person
        # interval, because the question is "will this still be open next time
        # we look at *them*" — not "next time we sweep".
        assert reloaded.horizon_hours() == 24

        monkeypatch.setenv("AMBIENT_FALLBACK_SWEEP_INTERVAL_HOURS", "1")
        again = importlib.reload(eligibility)
        assert again.SWEEP_INTERVAL_HOURS == 1
        assert again.PER_USER_INTERVAL_HOURS == 12, "cambiare lo sweep ha mosso l'altro"
        assert again.horizon_hours() == 24
    finally:
        monkeypatch.delenv("AMBIENT_FALLBACK_SWEEP_INTERVAL_HOURS", raising=False)
        monkeypatch.delenv("AMBIENT_FALLBACK_USER_INTERVAL_HOURS", raising=False)
        importlib.reload(eligibility)


def test_the_loop_derives_its_cadence_from_the_sweep_setting():
    """One place decides how often the system looks."""
    from ambient.runtime import _fallback_every_ticks

    assert _fallback_every_ticks() >= 1
    code = _code_only(_source("ambient", "runtime.py"))
    assert "SWEEP_INTERVAL_HOURS" in code
    assert "PER_USER_INTERVAL_HOURS" not in code, (
        "il loop legge l'intervallo che riguarda le persone, non se stesso"
    )


def test_recovery_never_sends_and_never_reasons():
    """§34: deterministic, and it happens before anything else at startup."""
    code = _code_only(_source("ambient", "eligibility.py"))
    recovery = code.split("async def recover_after_downtime")[1]
    for forbidden in ("send", "evaluate", "_ask_model", "get_provider"):
        assert forbidden not in recovery, f"il recupero fa {forbidden}"

    runtime = _source("ambient", "runtime.py")
    assert "recover_after_downtime" in runtime


def test_no_eligibility_reason_names_a_domain():
    """A checker that knows what a flight is has taken the judgement."""
    reasons = {
        "delivery_pending", "wake_overdue", "changes_unprocessed",
        "temporal_window", "revisit_due",
    }
    code = _source("ambient", "eligibility.py")
    for reason in reasons:
        assert f'"{reason}"' in code
    for domain in ("flight", "bill", "invoice", "medical", "home", "work"):
        assert f'reasons.append("{domain}' not in code
