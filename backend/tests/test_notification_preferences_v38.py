"""
V3.8 Sprint 3 — what a person asked for, and what happened last time.

Two things arrive in the judgement here, and they are different in kind.

A **preference** is a fact about somebody, and it must stay a fact. `if level
== "minimal": never_push()` is one line, reads as respectful, and would be the
end of the judgement: somebody who asked for less noise has not asked to be
kept in the dark about the one thing that would have mattered, and only
reasoning can tell those apart. So the setting travels in their own words and
the model weighs it against everything else.

A **veto** is not a fact, it is an instruction. "Non notificarmi per questa
cosa" names one concern, and code enforces it — a person saying stop should
not depend on a model agreeing. It is also carefully not a dismissal: the
concern goes on living wherever it was living, and only the pocket goes quiet.

The history is the third thing, and the danger there is arithmetic. Counts,
never ratios: an open rate is a metric, a metric invites optimising, and
optimising for opens is exactly the product nobody wants ORA to become.
"""

from __future__ import annotations

import ast
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
        "notification_preferences", "delivery_suppressions", "delivery_plans",
        "opportunities", "opportunity_decisions", "ambient_wakes",
        "ambient_activity", "app_presence", "calendar_events",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class FakeModel:
    def __init__(self, answers):
        self.answers = list(answers)
        self.seen = []

    async def __call__(self, system, user):
        self.seen.append({"system": system, "user": user})
        return self.answers.pop(0) if self.answers else None


def _install(monkeypatch, model):
    import delivery.reasoning as delivery_reasoning

    monkeypatch.setattr(delivery_reasoning, "_ask_model", model)


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


def _push(**over):
    answer = {
        "mode": "push",
        "timing": "now",
        "reason_to_interrupt": "La finestra si chiude.",
        "reason_to_open": "Ti dico cosa manca.",
        "confidence": "strong",
        "copy": {"title": "t", "body": "b"},
    }
    answer.update(over)
    return answer


async def _an_opportunity(db, uid, **over):
    from opportunities.models import EvidenceRef, Opportunity
    from opportunities.repository import OpportunityRepository

    fields = {
        "owner_id": uid,
        "identity_key": f"cosa-{uuid.uuid4().hex[:6]}",
        "status": "active",
        "semantic_summary": "Manca il certificato.",
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


def _rendered_prompt() -> str:
    """The delivery instruction as the model receives it, not as it is written."""
    import asyncio

    import delivery.reasoning as reasoning

    captured = {}

    async def capture(system, user):
        captured["system"] = system
        return {"mode": "silence"}

    original = reasoning._ask_model  # noqa: SLF001
    reasoning._ask_model = capture  # noqa: SLF001
    try:
        _run(reasoning.decide_delivery({}))
    finally:
        reasoning._ask_model = original  # noqa: SLF001
    return captured.get("system", "")


def _code_only(text: str) -> str:
    """
    Strip docstrings and comments before scanning.

    A guard that reads its own explanation is a guard that fires on the words
    describing what it forbids — which is how a real rule gets deleted for
    being noisy.
    """
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


# ---------------------------------------------------------------------------
# A preference is a fact
# ---------------------------------------------------------------------------

def test_the_preference_reaches_the_judgement_in_the_persons_own_words(monkeypatch):
    """
    §12/§45: a fact for the model, never a switch around it.

    What travels is a sentence about this person — not a level, not a number,
    not something a branch could compare against.
    """
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.preferences import LEVEL_MEANING, PreferenceService
            from delivery.service import DeliveryService

            await _allow_push(True)
            _provider(monkeypatch)
            await PreferenceService(db).set_level(uid, "minimal")
            opportunity = await _an_opportunity(db, uid)

            model = FakeModel([_push()])
            _install(monkeypatch, model)
            await DeliveryService(db).evaluate(uid, opportunity.id)

            asked = model.seen[0]["user"]
            assert LEVEL_MEANING["minimal"] in asked, "la preferenza non arriva al giudizio"
            assert "they_chose_this" in asked
            # And the raw label is not what the model reasons about.
            assert "how_much_they_want_to_be_interrupted" in asked
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_default_is_not_a_decision(monkeypatch):
    """Weighing a default as a choice would read a preference into silence."""
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.preferences import PreferenceService

            service = PreferenceService(db)
            fresh = await service.get(uid)
            assert fresh.level == "balanced"
            assert fresh.chosen_by_user is False
            assert fresh.for_ai()["they_chose_this"] is False

            await service.set_level(uid, "balanced")
            chosen = await service.get(uid)
            assert chosen.chosen_by_user is True, "scegliere lo stesso valore è comunque scegliere"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_no_branch_anywhere_decides_from_the_preference():
    """
    §55: the line that must never exist.

    `if level == "minimal": never_push()` reads as respectful and would end
    the judgement. Checked on the AST so a future diff cannot slip it in.
    """
    levels = {"minimal", "balanced", "proactive"}
    for module in ("delivery/service.py", "delivery/context.py", "ambient/service.py"):
        tree = ast.parse(HERE.joinpath(*module.split("/")).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                continue
            for side in [node.left, *node.comparators]:
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    assert side.value not in levels, (
                        f"{module}:{node.lineno} decide in base a «{side.value}»"
                    )


def test_quiet_hours_are_a_window_the_person_set(monkeypatch):
    """§13/§50: off unless set, and correct across midnight."""
    from ambient.preferences import QuietHours

    off = QuietHours()
    assert off.covers(3) is False, "ore di silenzio attive senza che nessuno le abbia chieste"
    assert off.human() is None

    night = QuietHours(enabled=True, start_hour=22, end_hour=7)
    assert night.covers(23) is True
    assert night.covers(3) is True
    assert night.covers(8) is False
    assert night.human() == "dalle 22:00 alle 7:00"

    daytime = QuietHours(enabled=True, start_hour=9, end_hour=17)
    assert daytime.covers(12) is True
    assert daytime.covers(20) is False


def test_the_model_is_told_whether_it_is_inside_their_quiet_hours(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.preferences import PreferenceService

            await PreferenceService(db).set_quiet_hours(
                uid, enabled=True, start_hour=22, end_hour=7
            )
            prefs = await PreferenceService(db).get(uid)

            assert prefs.for_ai(local_hour=23)["inside_their_quiet_hours"] is True
            assert prefs.for_ai(local_hour=10)["inside_their_quiet_hours"] is False
            assert prefs.for_ai(local_hour=23)["quiet_hours"] == "dalle 22:00 alle 7:00"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# A veto is an instruction
# ---------------------------------------------------------------------------

def test_muting_one_concern_is_not_dismissing_it(monkeypatch):
    """
    §17/§46: the distinction the whole feature rests on.

    Somebody can want to keep seeing something and want it to stop reaching
    their pocket. Conflating the two would mean "stop buzzing me" quietly
    deleted the thing they were still thinking about.
    """
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.preferences import PreferenceService
            from delivery.service import DeliveryService
            from opportunities.repository import OpportunityRepository

            await _allow_push(True)
            channel = _provider(monkeypatch)
            opportunity = await _an_opportunity(
                db, uid, surface_state="surfaced",
                last_surfaced_at=datetime.now(timezone.utc).isoformat(),
            )

            await PreferenceService(db).suppress(uid, opportunity.id)

            # The concern is untouched.
            stored = await OpportunityRepository(db).get(uid, opportunity.id)
            assert stored.status == "active", "silenziare ha chiuso la cosa"
            assert stored.surface_state == "surfaced", "silenziare l'ha tolta da Home"

            # But nothing reaches them about it.
            _install(monkeypatch, FakeModel([_push()]))
            verdict = await DeliveryService(db).evaluate(uid, opportunity.id)
            assert verdict.blocked_by == "muted_by_user"
            assert channel.sent == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_muting_cancels_what_was_already_going_to_arrive(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.preferences import PreferenceService
            from delivery.models import DeliveryPlan, PushCopy
            from delivery.service import DeliveryService

            opportunity = await _an_opportunity(db, uid)
            plan = DeliveryPlan(
                owner_id=uid, opportunity_id=opportunity.id, mode="push",
                status="pending",
                not_before=(datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
                words=PushCopy(title="t", body="b"),
            )
            await DeliveryService(db).repo.save_plan(plan)
            _provider(monkeypatch)

            await PreferenceService(db).suppress(uid, opportunity.id)

            stored = await DeliveryService(db).repo.get_plan(uid, plan.id)
            assert stored.status == "cancelled"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_veto_belongs_to_one_person(monkeypatch):
    """§55: owner-bound at every read, not filtered afterwards."""
    async def body():
        client, db = await _db()
        mine = f"p38_{uuid.uuid4().hex[:8]}"
        theirs = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.preferences import PreferenceService

            service = PreferenceService(db)
            await service.suppress(mine, "opp_shared")

            assert await service.is_suppressed(mine, "opp_shared") is True
            assert await service.is_suppressed(theirs, "opp_shared") is False
            assert await service.suppressed_targets(theirs) == []
        finally:
            for uid in (mine, theirs):
                await _clean(db, uid)
            client.close()

    _run(body())


def test_unmuting_gives_the_concern_its_voice_back(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from ambient.preferences import PreferenceService

            service = PreferenceService(db)
            await service.suppress(uid, "opp_x")
            assert await service.is_suppressed(uid, "opp_x") is True
            await service.unsuppress(uid, "opp_x")
            assert await service.is_suppressed(uid, "opp_x") is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# History, and the metric that must not exist
# ---------------------------------------------------------------------------

def test_the_model_can_see_that_it_has_said_this_before(monkeypatch):
    """
    §20/§22/§47: "gliel'ho già detto due volte e non ha aperto" is a real reason.

    Not available from any single plan, and not something code should conclude
    from — it is handed over and the judgement does what it likes with it.
    """
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            await _allow_push(True)
            _provider(monkeypatch)
            now = datetime.now(timezone.utc)

            for hours, outcome in ((5, "delivered"), (3, "opened")):
                await db.delivery_plans.insert_one({
                    "owner_id": uid, "id": f"dlv_{uuid.uuid4().hex[:8]}",
                    "opportunity_id": "other", "mode": "push", "status": "delivered",
                    "delivered_at": (now - timedelta(hours=hours)).isoformat(),
                    "outcome": outcome,
                    "created_at": now.isoformat(), "updated_at": now.isoformat(),
                })

            opportunity = await _an_opportunity(db, uid)
            model = FakeModel([_push()])
            _install(monkeypatch, model)
            await DeliveryService(db).evaluate(uid, opportunity.id)

            asked = model.seen[0]["user"]
            assert "how_past_notifications_went" in asked
            assert "they_opened" in asked
            assert "they_did_not_open" in asked
            assert "minutes_since_the_last_one" in asked
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_history_carries_counts_and_never_a_rate():
    """
    §21: no CTR, no open rate, no score to maximise.

    A ratio is a metric and a metric invites optimising. Counts describe; they
    do not suggest a direction to push.
    """
    code = _code_only((HERE / "delivery" / "context.py").read_text(encoding="utf-8"))
    history = code.split("async def _history")[1].split("def _hours_until")[0]

    for banned in ("rate", "score", "ctr", "engagement", "/ len(", "* 100"):
        assert banned not in history.lower(), f"la storia calcola {banned}"
    assert "sent_in_the_last_days" in history
    assert "they_opened" in history


def test_nothing_anywhere_optimises_for_being_opened():
    """§21/§60: the product this must never become."""
    for module in ("delivery/service.py", "delivery/context.py",
                   "ambient/preferences.py", "ambient/service.py"):
        code = _code_only(HERE.joinpath(*module.split("/")).read_text(encoding="utf-8"))
        for banned in (
            "open_rate", "click_through", "engagement_score", "retention_score",
            "maximize", "streak",
        ):
            assert banned not in code, f"{module} ottimizza {banned}"

    # The prompt is prose by nature, so it is checked for the opposite: it has
    # to forbid these out loud rather than merely not mention them.
    prompt = (HERE / "delivery" / "reasoning.py").read_text(encoding="utf-8")
    assert "no streak" in prompt
    assert "You gain nothing from being opened" in prompt


# ---------------------------------------------------------------------------
# Honest outcomes
# ---------------------------------------------------------------------------

def test_not_opened_is_never_called_dismissed(monkeypatch):
    """
    §27/§49: NO FAKE DISMISS.

    The OS rarely tells us a notification was swept away. "Nobody opened it"
    is what we know; "they refused it" is a decision we would be putting in
    somebody's mouth.
    """
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.models import DeliveryPlan, PushCopy
            from delivery.service import DeliveryService

            now = datetime.now(timezone.utc)
            service = DeliveryService(db)
            opportunity = await _an_opportunity(db, uid)
            plan = DeliveryPlan(
                owner_id=uid, opportunity_id=opportunity.id, mode="push",
                status="pending",
                not_before=(now - timedelta(hours=3)).isoformat(),
                not_after=(now - timedelta(hours=1)).isoformat(),
                delivered_at=(now - timedelta(hours=3)).isoformat(),
                words=PushCopy(title="t", body="b"),
            )
            await service.repo.save_plan(plan)
            _provider(monkeypatch)

            await service.deliver_due(uid)

            stored = await service.repo.get_plan(uid, plan.id)
            assert stored.status == "expired"
            assert stored.outcome == "expired"
            assert stored.outcome != "dismissed", "non aperta è diventata rifiutata"
            assert stored.opened_at is None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_opening_is_recorded_once_and_never_overwritten(monkeypatch):
    """§25/§48: idempotent, and `opened` outlives anything that follows."""
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.models import DeliveryPlan, PushCopy
            from delivery.service import DeliveryService

            service = DeliveryService(db)
            opportunity = await _an_opportunity(db, uid)
            plan = DeliveryPlan(
                owner_id=uid, opportunity_id=opportunity.id, mode="push",
                status="delivered",
                delivered_at=datetime.now(timezone.utc).isoformat(),
                words=PushCopy(title="t", body="b"),
            )
            await service.repo.save_plan(plan)

            first = await service.record_outcome(uid, plan.id, "opened")
            assert first["ok"] is True
            stamp = (await service.repo.get_plan(uid, plan.id)).opened_at
            assert stamp

            await service.record_outcome(uid, plan.id, "opened")
            assert (await service.repo.get_plan(uid, plan.id)).opened_at == stamp

            # And a later "expired" does not erase the fact that they came.
            await service.record_outcome(uid, plan.id, "expired")
            stored = await service.repo.get_plan(uid, plan.id)
            assert stored.outcome == "opened"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_accepted_by_a_provider_is_not_shown_on_a_phone():
    """§28: the certainty we do not have is not claimed anywhere."""
    from delivery.models import DeliveryPlan

    fields = set(DeliveryPlan.model_fields)
    for overclaim in ("shown_at", "displayed_at", "seen_on_device", "read_at"):
        assert overclaim not in fields, f"il piano afferma {overclaim}"
    assert "delivered_at" in fields and "opened_at" in fields

    push = (HERE / "ambient" / "push.py").read_text(encoding="utf-8")
    assert "provider_accepted" in push


def test_settled_plans_age_out_and_open_ones_never_do(monkeypatch):
    """§24: enough history for fatigue, not a permanent record."""
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.models import DeliveryPlan, PushCopy
            from delivery.repository import HISTORY_RETENTION_DAYS
            from delivery.service import DeliveryService

            assert 0 < HISTORY_RETENTION_DAYS <= 90
            service = DeliveryService(db)
            opportunity = await _an_opportunity(db, uid)

            waiting = DeliveryPlan(
                owner_id=uid, opportunity_id=opportunity.id, mode="push",
                status="pending", words=PushCopy(title="t", body="b"),
            )
            await service.repo.save_plan(waiting)
            assert (await service.repo.get_plan(uid, waiting.id)).expires_at is None, (
                "un piano ancora in attesa può svanire"
            )

            waiting.status = "delivered"
            await service.repo.save_plan(waiting)
            assert (await service.repo.get_plan(uid, waiting.id)).expires_at is not None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# The surface
# ---------------------------------------------------------------------------

def test_the_setting_lives_where_the_other_permissions_live():
    """§14/§60: no new tab, no notification dashboard."""
    frontend = HERE.parent / "frontend"
    screen = (frontend / "app" / "account" / "permessi.tsx").read_text(encoding="utf-8")
    assert 'testID="perm-notifications"' in screen
    # The testID is built from the choice id, so both halves are checked.
    assert "notification-level-${c.id}" in screen
    for level in ("'minimal'", "'balanced'", "'proactive'"):
        assert level in screen, f"manca la scelta {level}"

    routes = [
        p.name for p in (frontend / "app").rglob("*.tsx")
        if "notific" in p.name.lower()
    ]
    assert not routes, f"è comparsa una schermata dedicata: {routes}"

    layout = (frontend / "app" / "(tabs)" / "_layout.tsx").read_text(encoding="utf-8")
    for tab in re.findall(r'name="([^"]+)"', layout):
        assert "notific" not in tab.lower(), f"è comparsa una tab: {tab}"


def test_the_copy_asks_rather_than_sells():
    """No FOMO in a settings screen either."""
    frontend = HERE.parent / "frontend"
    screen = (frontend / "app" / "account" / "permessi.tsx").read_text(encoding="utf-8")
    for banned in ("non perderti", "non perdere nulla", "resta aggiornato", "attiva subito"):
        assert banned not in screen.lower(), f"copy da marketing: {banned}"
    assert "Quanto vuoi che ORA ti interrompa" in screen or "interrompa" in screen


def test_the_history_of_this_one_thing_is_kept_apart_from_the_rest(monkeypatch):
    """
    §7: "ti ho già interrotto ieri per QUESTA cosa" is a different fact.

    The general history cannot answer it — three notifications yesterday about
    three unrelated things says nothing about whether this one has already
    been raised. Only one of the two is a reason to say this one differently.
    """
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery import context as delivery_context
            from opportunities.repository import OpportunityRepository

            now = datetime.now(timezone.utc)
            mine = await _an_opportunity(db, uid)
            other = await _an_opportunity(db, uid)

            # Two about something else, one about this.
            for opportunity_id, hours, outcome in (
                (other.id, 20, "opened"),
                (other.id, 9, "delivered"),
                (mine.id, 4, "delivered"),
            ):
                await db.delivery_plans.insert_one({
                    "owner_id": uid, "id": f"dlv_{uuid.uuid4().hex[:8]}",
                    "opportunity_id": opportunity_id, "mode": "push",
                    "status": "delivered",
                    "delivered_at": (now - timedelta(hours=hours)).isoformat(),
                    "outcome": outcome,
                    "created_at": now.isoformat(), "updated_at": now.isoformat(),
                })

            stored = await OpportunityRepository(db).get(uid, mine.id)
            moment = await delivery_context.build(db, uid, opportunity=stored)

            general = moment["how_past_notifications_went"]
            this_one = moment["about"]["how_this_one_went_before"]

            assert general["sent_in_the_last_days"] == 3
            assert this_one["times_already_sent"] == 1, (
                "la storia di questa cosa conta anche le altre"
            )
            assert this_one["ever_opened"] is False
            assert general["they_opened"] == 1, "l'altra è stata aperta, questa no"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_concern_never_raised_before_says_so(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery import context as delivery_context

            fresh = await _an_opportunity(db, uid)
            moment = await delivery_context.build(db, uid, opportunity=fresh)
            this_one = moment["about"]["how_this_one_went_before"]

            assert this_one["times_already_sent"] == 0
            assert this_one["ever_opened"] is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_model_is_told_that_a_preference_can_decide_a_close_call():
    """
    §2: the preference has decisional weight without becoming a rule.

    Two things have to be true at once and the prompt has to say both. An
    extreme situation is not overturned by somebody having asked for quiet;
    and when the situation alone does not settle it, what they asked for is
    one of the things that does. Without the second sentence the preference
    travels into the payload and changes nothing, which is what the live QA
    found.
    """
    # Rendered, not read from source: the instruction is written across a
    # dozen string literals and a source scan would miss a sentence broken
    # over two lines — which is exactly how a guard passes for the wrong
    # reason.
    prompt = _rendered_prompt()

    # It may not be overruled by a preference.
    assert "Some situations settle the question by themselves" in prompt
    assert "the situation decides" in prompt

    # And it may not be ignored either.
    assert "does not clearly settle whether an interruption is worth its cost" in prompt
    assert "one of the main things that decides between them" in prompt

    # And a default is not a decision.
    assert "a default carries less weight than a choice" in prompt

    # Still not a rule: the prompt never names an outcome for a level.
    for level in ("minimal", "balanced", "proactive"):
        assert level not in prompt, f"il prompt nomina il livello «{level}»"


# ---------------------------------------------------------------------------
# What decided the mode
# ---------------------------------------------------------------------------

def test_the_decision_says_what_tipped_it(monkeypatch):
    """
    §1: the field the contract was missing.

    `reason_to_interrupt` and `reason_to_open` are both about the situation —
    what makes it worth attention, and what somebody would find. Neither can
    answer why a quiet line was preferred to a buzz, so when a preference or
    an hour tipped the choice there was nowhere to say so and it stayed
    invisible. That was not the model ignoring the preference; it was the
    contract having no room for the answer.
    """
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            await _allow_push(True)
            _provider(monkeypatch)
            opportunity = await _an_opportunity(db, uid)

            _install(monkeypatch, FakeModel([_push(
                reason_to_interrupt="La finestra si chiude stasera.",
                what_decided_the_mode=(
                    "Ha chiesto poche interruzioni, ma la finestra si chiude "
                    "prima che riapra l'app."
                ),
            )]))
            verdict = await DeliveryService(db).evaluate(uid, opportunity.id)

            plan = verdict.plan
            assert plan.what_decided_the_mode, "la decisione non dice cosa l'ha decisa"
            assert plan.what_decided_the_mode != plan.reason_to_interrupt, (
                "ripete perché la situazione conta invece di dire cosa ha deciso"
            )
            # And it survives even when there is no plan to hang it on, which
            # is most of the time: `in_app` and `silence` create nothing, and
            # those are exactly the cases where a preference is likeliest to
            # have been what tipped the choice.
            assert verdict.what_decided_the_mode == plan.what_decided_the_mode
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_trade_off_is_rewritten_at_every_recheck(monkeypatch):
    """
    §8: the trade-off that held last night is not the one that holds now.

    A plan carries the words that were decided; it must also carry why that
    channel was chosen, and both have to move when the judgement moves.
    """
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            await _allow_push(True)
            _provider(monkeypatch)
            opportunity = await _an_opportunity(db, uid)
            service = DeliveryService(db)
            later = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()

            _install(monkeypatch, FakeModel([_push(
                timing="at", not_before=later,
                what_decided_the_mode="Prima versione del compromesso.",
            )]))
            first = (await service.evaluate(uid, opportunity.id)).plan
            assert first.what_decided_the_mode == "Prima versione del compromesso."

            _install(monkeypatch, FakeModel([_push(
                timing="at", not_before=later,
                what_decided_the_mode="Adesso è cambiato il momento, non il fatto.",
            )]))
            second = (await service.evaluate(uid, opportunity.id)).plan

            assert second.id == first.id, "una seconda valutazione ha creato un piano"
            assert second.what_decided_the_mode == "Adesso è cambiato il momento, non il fatto."
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_trade_off_is_auditable_and_never_reaches_a_person(monkeypatch):
    """
    §8/§9: a short product justification, not a scratchpad and not copy.

    It exists so a delivered notification can be explained afterwards. It has
    no business on a screen, and it must not become a place where the model
    is asked to think out loud.
    """
    from delivery.models import DeliveryDecision, DeliveryPlan

    assert DeliveryDecision.model_fields["what_decided_the_mode"].metadata[0].max_length == 300
    assert "what_decided_the_mode" in DeliveryPlan.model_fields

    # Present in the debug view, absent from anything a person reads.
    plan = DeliveryPlan(
        owner_id="u", opportunity_id="o", mode="push",
        what_decided_the_mode="il compromesso",
    )
    assert "what_decided" not in plan.public(), "il compromesso finisce in un payload"

    prompt = _rendered_prompt()
    for scratchpad in ("step by step", "think through", "reasoning steps", "chain of thought"):
        assert scratchpad not in prompt.lower(), f"il prompt chiede uno scratchpad: {scratchpad}"
    assert "one short sentence" in prompt


def test_the_prompt_asks_for_the_trade_off_and_forbids_preference_theatre():
    """
    §3: name the preference when it tipped the choice — and only then.

    A field that always mentions the preference would be theatre: it would
    look like weight without being it. So the instruction requires the truth
    in both directions.
    """
    prompt = _rendered_prompt()

    assert "what_decided_the_mode" in prompt
    assert "beat the alternatives that were also defensible" in prompt
    # Name it when it mattered.
    assert "If what they asked for is part of what tipped it, name it" in prompt
    # And do not when it did not.
    assert "Do not mention a preference that did not actually weigh" in prompt
    # Still never a rule: no level is named anywhere.
    for level in ("minimal", "balanced", "proactive"):
        assert level not in prompt, f"il prompt nomina il livello «{level}»"


def test_the_trade_off_survives_a_decision_that_creates_no_plan(monkeypatch):
    """
    §8: `in_app` and `silence` write no plan — and are where preference bites.

    Keeping the trade-off only on a push would discard it in exactly the cases
    it was added for: the ones where somebody asked for quiet and got it.
    """
    async def body():
        client, db = await _db()
        uid = f"p38_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            await _allow_push(True)
            _provider(monkeypatch)
            opportunity = await _an_opportunity(db, uid)

            _install(monkeypatch, FakeModel([{
                "mode": "in_app",
                "reason_to_interrupt": "Vale la pena vederlo.",
                "what_decided_the_mode": (
                    "Ha chiesto poche interruzioni e questa può aspettare "
                    "che apra l'app."
                ),
            }]))
            verdict = await DeliveryService(db).evaluate(uid, opportunity.id)

            assert verdict.plan is None, "una decisione in_app ha creato un piano"
            assert verdict.what_decided_the_mode, "il compromesso è andato perso"
            assert "interruzioni" in verdict.what_decided_the_mode
            assert verdict.what_decided_the_mode != verdict.reason
            assert verdict.public()["what_decided"] == verdict.what_decided_the_mode
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())
