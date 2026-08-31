"""
V3.7 Sprint 1 — whether anything is worth saying, and who gets to decide.

    PROACTIVITY IS AN AI JUDGMENT, NOT A RULE TRIGGER.
    SILENCE IS A VALID DECISION.
    OPPORTUNITY != WORK. != NOTIFICATION. != ACTION.

The thing being tested is a refusal. Code assembles facts, keeps identity,
applies states and closes every door from an opportunity to a task, a push or
an action — and decides nothing about whether any of it matters. That question
goes to the model, and the model is allowed to answer "nothing", which is what
most of these tests are about.

So the model is stubbed wherever it is asked to judge, and what is asserted is
that the code neither judged for it, nor let it invent a fact, nor let the same
concern arrive twice.
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

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _service(db):
    from opportunities.service import OpportunityService

    return OpportunityService(db)


async def _clean(db, uid):
    for coll in (
        "opportunities", "opportunity_decisions", "life_places",
        "presence_sessions", "presence_states", "presence_observations",
        "place_candidates", "open_questions", "calendar_events",
        "comparison_runs", "home_snapshots", "observed_routines",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class FakeModel:
    """The model, saying what a test needs it to say."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.seen = []

    async def __call__(self, system, user):
        self.seen.append({"system": system, "user": user})
        return self.answers.pop(0) if self.answers else None


def _install(monkeypatch, model):
    # The name is bound into the module at import, so patching the shared
    # helper's home would leave this one pointing at the real provider.
    import opportunities.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", model)


def _silence(reason="niente di rilevante"):
    return {"opportunities": [], "reason_for_silence": reason}


def _proposal(identity, refs, **over):
    out = {
        "identity_key": identity,
        "what": "Manca il documento per l'appuntamento di giovedì.",
        "why_it_matters": "Senza quel documento l'appuntamento non si può fare.",
        "why_now": "Giovedì è fra due giorni e l'ufficio è aperto solo la mattina.",
        "relevance": "high",
        "urgency": "soon",
        "time_sensitivity": "perishable",
        "confidence": "reasonable",
        "evidence_refs": list(refs),
    }
    out.update(over)
    return out


async def _seed_calendar(db, uid, *, title, days_ahead=2):
    when = datetime.now(timezone.utc) + timedelta(days=days_ahead)
    ref = f"evt_{uuid.uuid4().hex[:8]}"
    await db.calendar_events.insert_one(
        {
            "user_id": uid,
            "id": ref,
            "title": title,
            "start_at": when.isoformat(),
            "end_at": (when + timedelta(hours=1)).isoformat(),
            "all_day": False,
        }
    )
    return ref


# ---------------------------------------------------------------------------
# Silence
# ---------------------------------------------------------------------------

def test_a_life_full_of_harmless_facts_produces_nothing(monkeypatch):
    """
    §30. A calendar, a home, a routine, a couple of facts, no problem. The
    model looks and says so, and nothing is written down — silence that leaves
    a record is not silence.
    """
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            from places.service import PlacesService
            from places.models import Coordinates

            places = PlacesService(db)
            await places.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=45.4064, longitude=11.8768),
            )
            await _seed_calendar(db, uid, title="Cena con Marco", days_ahead=3)

            model = FakeModel([_silence("tutto sembra sotto controllo")])
            _install(monkeypatch, model)

            result = await (await _service(db)).scan(uid)

            assert result.silence is True
            assert result.unavailable is False
            assert result.created == [] and result.updated == []
            assert result.reason_for_silence
            assert await db.opportunities.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_silence_is_not_an_error_and_not_an_outage(monkeypatch):
    """
    An unreachable provider must never be recorded as "there was nothing".
    One is a judgement; the other is a network.
    """
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            _install(monkeypatch, FakeModel([None]))
            result = await (await _service(db)).scan(uid)

            assert result.unavailable is True
            assert result.silence is True
            assert "disponibil" in result.reason_for_silence
            assert await db.opportunities.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# A real opportunity
# ---------------------------------------------------------------------------

def test_the_model_can_raise_something_and_it_is_kept_with_its_reasons(monkeypatch):
    """§31: one opportunity, with why it matters, why now, and what it rests on."""
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            ref = await _seed_calendar(db, uid, title="Appuntamento in comune")
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("documento-appuntamento-comune", [ref])]}
            ]))

            result = await (await _service(db)).scan(uid)

            assert result.silence is False
            assert len(result.created) == 1
            opportunity = result.created[0]
            assert opportunity.status == "active"
            assert opportunity.why_it_matters and opportunity.why_now
            assert opportunity.relevance == "high" and opportunity.urgency == "soon"
            assert [e.ref for e in opportunity.evidence] == [ref]
            assert opportunity.evidence[0].kind == "calendar_event"
            assert opportunity.decision_provenance == "model"

            # And nothing else in the person's day moved.
            for collection in ("home_snapshots", "attention_items", "work_items"):
                if collection in await db.list_collection_names():
                    assert await db[collection].count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_opportunity_shows_a_person_words_and_never_an_identity_key(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            ref = await _seed_calendar(db, uid, title="Visita")
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("visita-preparazione", [ref])]}
            ]))
            result = await (await _service(db)).scan(uid)
            public = result.created[0].public()

            assert "identity_key" not in public
            assert public["what"] and public["why_it_matters"]
            # Evidence is described, not dumped: a screen gets a label, not a
            # reference into the database.
            assert public["based_on"] == [
                {"kind": "calendar_event", "summary": None}
            ]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Evidence-bound
# ---------------------------------------------------------------------------

def test_a_claim_resting_on_a_fact_nobody_supplied_is_dropped(monkeypatch):
    """
    §9. The failure this prevents is ORA telling somebody about a deadline
    that does not exist. Failing closed costs an opportunity; the alternative
    costs trust.
    """
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("scadenza-inventata", ["evt_che_non_esiste"])]}
            ]))
            result = await (await _service(db)).scan(uid)

            assert result.created == []
            assert result.silence is True
            assert any("fatto reale" in s["reason"] for s in result.skipped)
            assert await db.opportunities.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_opportunity_with_no_evidence_at_all_is_refused(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("senza-prove", [])]}
            ]))
            result = await (await _service(db)).scan(uid)
            assert result.created == [] and result.silence is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def test_the_same_concern_worded_differently_updates_instead_of_arriving_twice(monkeypatch):
    """
    §12. "Preparare il documento" today and "Ricordati il documento" tomorrow
    are one worry, not two. The identity key is what makes that true.
    """
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            ref = await _seed_calendar(db, uid, title="Appuntamento")
            service = await _service(db)

            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("documento-appuntamento", [ref])]}
            ]))
            first = await service.scan(uid)
            assert len(first.created) == 1

            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal(
                    "documento-appuntamento", [ref],
                    what="Ricordati il documento per l'appuntamento.",
                    urgency="urgent",
                )]}
            ]))
            second = await service.scan(uid)

            assert second.created == []
            assert len(second.updated) == 1
            assert await db.opportunities.count_documents({"owner_id": uid}) == 1
            stored = second.updated[0]
            assert stored.id == first.created[0].id
            assert stored.urgency == "urgent"
            assert stored.semantic_summary.startswith("Ricordati")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_identity_that_could_not_be_matched_tomorrow_is_refused(monkeypatch):
    """
    A sentence is not a key: today's phrasing will not match next week's, and
    the concern would arrive twice. Fail closed rather than guess.
    """
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            ref = await _seed_calendar(db, uid, title="Appuntamento")
            for bad in (
                "Preparare il documento per giovedì",   # a sentence
                "doc appuntamento 2026-09-03",          # dated: never matches again
                "",
                "ab",
                "chiave con spazi",
            ):
                _install(monkeypatch, FakeModel([
                    {"opportunities": [_proposal(bad, [ref])]}
                ]))
                result = await (await _service(db)).scan(uid)
                assert result.created == [], f"identità accettata: {bad!r}"
            assert await db.opportunities.count_documents({"owner_id": uid}) == 0

            # Case is normalised rather than refused: two spellings of one
            # concern must not become two concerns.
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("Documento-Appuntamento", [ref])]}
            ]))
            created = (await (await _service(db)).scan(uid)).created
            assert len(created) == 1
            assert created[0].identity_key == "documento-appuntamento"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_identity_is_matched_exactly_and_never_by_resemblance():
    """
    Structural. Fuzzy identity is how two different concerns silently become
    one, which is worse than a duplicate: it hides something.
    """
    source = (HERE / "opportunities" / "service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                source = source.replace(doc, "")
    code = " ; ".join(
        l for l in source.splitlines() if not l.strip().startswith("#")
    )
    for cheat in ("difflib", "levenshtein", "fuzz", "startswith(", "in existing.semantic"):
        assert cheat not in code, f"l'identità si risolve per somiglianza: {cheat}"


# ---------------------------------------------------------------------------
# Dismissal and suppression
# ---------------------------------------------------------------------------

def test_something_just_dismissed_is_not_raised_again(monkeypatch):
    """§34: the same facts, the same scan, and ORA does not forget the answer."""
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            ref = await _seed_calendar(db, uid, title="Appuntamento")
            service = await _service(db)

            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("documento-appuntamento", [ref])]}
            ]))
            created = (await service.scan(uid)).created[0]
            assert (await service.dismiss(uid, created.id))["status"] == "dismissed"

            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("documento-appuntamento", [ref])]}
            ]))
            again = await service.scan(uid)

            assert again.created == [] and again.updated == []
            assert any("chiusa" in s["reason"] for s in again.skipped)
            assert await db.opportunities.count_documents({"owner_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_not_now_and_never_again_are_different_answers(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            ref = await _seed_calendar(db, uid, title="Appuntamento")
            service = await _service(db)
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("documento-appuntamento", [ref])]}
            ]))
            created = (await service.scan(uid)).created[0]

            assert (await service.dismiss(uid, created.id, suppress=True))[
                "status"
            ] == "suppressed"
            stored = await service.repo.get(uid, created.id)
            assert stored.decision_provenance == "user"

            decisions = await service.repo.decisions_for(uid, created.id)
            assert [d.outcome for d in decisions] == ["suppress"]
            assert decisions[0].source == "user"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

def test_a_concern_that_has_been_dealt_with_is_closed_not_duplicated(monkeypatch):
    """§33: the fact changed, so the opportunity ends — it does not respawn."""
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            ref = await _seed_calendar(db, uid, title="Appuntamento")
            service = await _service(db)
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("documento-appuntamento", [ref])]}
            ]))
            created = (await service.scan(uid)).created[0]

            _install(monkeypatch, FakeModel([
                {"outcome": "resolve", "rationale": "il documento è stato trovato"}
            ]))
            reviewed = await service.review(uid, created.id)

            assert reviewed["ok"] is True and reviewed["outcome"] == "resolve"
            stored = await service.repo.get(uid, created.id)
            assert stored.status == "resolved"
            assert stored.last_reviewed_at

            decisions = await service.repo.decisions_for(uid, created.id)
            assert decisions[-1].outcome == "resolve"
            assert decisions[-1].rationale

            # And a later scan does not bring it back.
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("documento-appuntamento", [ref])]}
            ]))
            after = await service.scan(uid)
            assert after.created == []
            assert await db.opportunities.count_documents({"owner_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_review_can_change_what_would_be_said_without_changing_what_it_is(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            ref = await _seed_calendar(db, uid, title="Appuntamento")
            service = await _service(db)
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("documento-appuntamento", [ref])]}
            ]))
            created = (await service.scan(uid)).created[0]

            _install(monkeypatch, FakeModel([{
                "outcome": "update",
                "rationale": "manca poco",
                "updated": {
                    "what": "Il documento serve domani mattina.",
                    "why_it_matters": "Domani è l'ultimo giorno utile.",
                    "urgency": "urgent",
                },
            }]))
            await service.review(uid, created.id)

            stored = await service.repo.get(uid, created.id)
            assert stored.status == "active"
            assert stored.urgency == "urgent"
            assert stored.semantic_summary.startswith("Il documento serve domani")
            assert stored.identity_key == created.identity_key
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_date_that_has_passed_is_the_one_thing_code_closes_on_its_own(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            ref = await _seed_calendar(db, uid, title="Appuntamento")
            service = await _service(db)
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal(
                    "documento-appuntamento", [ref], valid_until=yesterday
                )]}
            ]))
            created = (await service.scan(uid)).created[0]

            assert await service.expire_past(uid) == 1
            stored = await service.repo.get(uid, created.id)
            assert stored.status == "expired"
            # Even arithmetic leaves a record of who decided.
            assert stored.decision_provenance == "code_expiry"
            assert (await service.repo.decisions_for(uid, created.id))[-1].source == "code_expiry"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Context is not a trigger
# ---------------------------------------------------------------------------

def test_being_at_home_on_its_own_produces_nothing(monkeypatch):
    """
    §36. The snapshot says where they are because a judgement might need it,
    and says nothing about it mattering. There is no rule that turns a place
    into a reason to speak.
    """
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates
            from places.service import PlacesService

            places = PlacesService(db)
            await places.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=45.4064, longitude=11.8768),
                currently_here=True,
            )
            model = FakeModel([_silence("essere a casa non significa nulla di per sé")])
            _install(monkeypatch, model)

            result = await (await _service(db)).scan(uid)
            assert result.silence is True
            assert await db.opportunities.count_documents({"owner_id": uid}) == 0

            # The presence was in the payload — it is context, and was offered
            # as context — but nothing in the payload called it important.
            sent = model.seen[0]["user"]
            assert "at_a_known_place" in sent
            for grading in ("important", "urgent", "trigger", "score"):
                assert grading not in sent.lower(), f"lo snapshot pre-giudica: {grading}"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_no_rule_anywhere_turns_a_fact_into_an_opportunity():
    """
    §2/§38, structurally. `if event_tomorrow: opportunity()` is the shape this
    forbids, and so is every spelling of it.
    """
    for name in ("service.py", "snapshot.py", "models.py", "repository.py"):
        raw = (HERE / "opportunities" / name).read_text(encoding="utf-8")
        tree = ast.parse(raw)
        source = raw
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    source = source.replace(doc, "")
        code = " ; ".join(
            l for l in source.splitlines() if not l.strip().startswith("#")
        )
        for domain in (
            "mutuo", "mortgage", "insurance", "assicuraz", "palestra", "gym",
            "bolletta", "utility", "contract_expiring", "trip_in", "commute_long",
        ):
            assert domain not in code.lower(), f"{name} conosce un dominio: {domain}"
        for shape in (
            "days_until <", "days_until <=", "hours_until <", "== 'home'",
            'at_home', "if tomorrow", "event_tomorrow",
        ):
            assert shape not in code, f"{name} contiene una regola di trigger: {shape}"


def test_the_snapshot_hands_over_facts_and_grades_none_of_them():
    source = (HERE / "opportunities" / "snapshot.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    code = source
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                code = code.replace(doc, "")
    code = " ; ".join(l for l in code.splitlines() if not l.strip().startswith("#"))
    for grading in ("priority", "score", "weight", "importance", "is_urgent"):
        assert grading not in code.lower(), f"lo snapshot classifica: {grading}"


# ---------------------------------------------------------------------------
# No scores, no work, no notifications, no actions
# ---------------------------------------------------------------------------

def test_judgements_are_words_a_person_could_argue_with():
    """
    §6. `relevance: high` carries the reasoning; `relevance: 0.84` hides it
    behind a decimal point and invites arithmetic nobody can defend.
    """
    from opportunities.models import Opportunity

    fields = Opportunity.model_fields
    for numeric in ("score", "relevance_score", "urgency_score", "weight", "rank"):
        assert numeric not in fields, f"esiste un punteggio finto: {numeric}"

    source = (HERE / "opportunities" / "models.py").read_text(encoding="utf-8")
    assert 'Relevance = Literal["low", "medium", "high"]' in source
    assert 'Urgency = Literal["none", "soon", "urgent"]' in source


def test_ordering_is_arithmetic_over_a_judgement_and_not_a_judgement():
    from opportunities.models import Opportunity

    def make(relevance, urgency, created):
        return Opportunity(
            owner_id="u", identity_key="k-" + created, semantic_summary="x",
            why_it_matters="y", relevance=relevance, urgency=urgency,
            created_at=created,
        )

    rows = [
        make("low", "none", "2026-01-03T00:00:00+00:00"),
        make("high", "urgent", "2026-01-02T00:00:00+00:00"),
        make("high", "soon", "2026-01-01T00:00:00+00:00"),
    ]
    ordered = sorted(rows, key=lambda o: o.order_key)
    assert [(o.urgency, o.relevance) for o in ordered] == [
        ("urgent", "high"), ("soon", "high"), ("none", "low")
    ]
    # Deterministic: the same list twice.
    assert [o.id for o in sorted(rows, key=lambda o: o.order_key)] == [
        o.id for o in ordered
    ]


def test_an_opportunity_never_becomes_work_a_notification_or_an_action():
    """
    §15/§16/§17, structurally. Every one of these would be ORA doing something
    on somebody's behalf that they never agreed to.
    """
    for name in ("service.py", "router.py", "snapshot.py", "reasoning.py"):
        raw = (HERE / "opportunities" / name).read_text(encoding="utf-8")
        tree = ast.parse(raw)
        source = raw
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    source = source.replace(doc, "")
        code = " ; ".join(
            l for l in source.splitlines() if not l.strip().startswith("#")
        )
        for forbidden in (
            "attention_items", "work_items", "HomeItem",
            "send_notification", "notify", "sendmail", "smtp",
            "action_engine", "ActionEngine", "create_event", "open_navigation",
        ):
            assert forbidden not in code, f"{name} può creare {forbidden}"

    # Reading what is already on the plate is allowed and necessary — it is how
    # the model avoids repeating something the person is already looking at.
    # Writing to it is not: the snapshot only ever reads.
    snapshot = (HERE / "opportunities" / "snapshot.py").read_text(encoding="utf-8")
    assert "home_snapshots" in snapshot, "non sa cosa la persona ha già davanti"
    for write in ("insert_one", "update_one", "delete_many", "replace_one"):
        assert write not in snapshot, f"lo snapshot scrive: {write}"


def test_the_only_collections_written_are_its_own():
    service = (HERE / "opportunities" / "service.py").read_text(encoding="utf-8")
    repository = (HERE / "opportunities" / "repository.py").read_text(encoding="utf-8")
    assert 'OPPORTUNITIES = "opportunities"' in repository
    assert 'DECISIONS = "opportunity_decisions"' in repository
    # The service never touches a collection directly: it goes through the
    # repository, which knows only its own two.
    assert "self.db[" not in service


# ---------------------------------------------------------------------------
# Research, privacy, neutrality
# ---------------------------------------------------------------------------

def test_a_missing_external_fact_is_declared_rather_than_invented(monkeypatch):
    """§35/§18: needs_research is a request for evidence, not a guess."""
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            ref = await _seed_calendar(db, uid, title="Scadenza")
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal(
                    "verifica-requisito", [ref],
                    confidence="weak",
                    needs_research=True,
                    research_question="Quali documenti servono per questa pratica?",
                )]}
            ]))
            created = (await (await _service(db)).scan(uid)).created[0]

            assert created.needs_research is True
            assert created.research_question
            assert created.confidence == "weak"
            # Declaring the gap is not filling it: no research ran, and no
            # opportunity was manufactured from an assumed answer.
            assert created.public()["needs_research"] is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_research_is_reused_and_not_reimplemented():
    reasoning = (HERE / "opportunities" / "reasoning.py").read_text(encoding="utf-8")
    assert "from research.reasoning import _ask_model" in reasoning
    for own_client in ("httpx", "openai", "get_manager", "AsyncClient"):
        assert own_client not in reasoning, f"un secondo client LLM: {own_client}"


def test_the_provider_is_told_a_life_and_not_a_dossier(monkeypatch):
    """
    §26. Minimum necessary: names of places rather than coordinates, titles
    rather than descriptions, a bounded window rather than a history.
    """
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates
            from places.service import PlacesService

            await PlacesService(db).save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=45.40641234, longitude=11.87678901),
                address="Via Roma 1, Padova",
                currently_here=True,
            )
            model = FakeModel([_silence()])
            _install(monkeypatch, model)
            await (await _service(db)).scan(uid)

            sent = model.seen[0]["user"]
            assert "45.406" not in sent and "11.876" not in sent, "coordinate inviate"
            assert "latitude" not in sent and "longitude" not in sent
            assert "Casa" in sent, "il nome del luogo serve al giudizio"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_snapshot_is_bounded_rather_than_a_full_history():
    """
    Every source caps itself, and the check knows which sources exist.

    This used to count how many times `MAX_PER_SOURCE` appeared in the file
    and compare it to a number written by hand — which passed for the wrong
    reason the moment `recently_settled` was added, and would have passed
    just as happily if a new source had arrived with no cap at all. So the
    list of sources is read from `build()` itself and each one is checked.
    """
    import ast

    from opportunities.snapshot import HORIZON_DAYS, MAX_PER_SOURCE

    assert 1 <= HORIZON_DAYS <= 30
    assert 1 <= MAX_PER_SOURCE <= 10

    text = (HERE / "opportunities" / "snapshot.py").read_text(encoding="utf-8")
    tree = ast.parse(text)

    gatherers = {
        node.name: ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("_")
    }
    # The sources build() actually asks for, in its own words.
    named = re.findall(r'\(\s*"(\w+)",\s*(_\w+),?\s*\)', text)
    assert len(named) >= 8, f"solo {len(named)} fonti trovate: la lista è cambiata"

    for source_name, gatherer in named:
        body = gatherers.get(gatherer, "")
        assert body, f"{gatherer} non esiste"
        bounded = "MAX_PER_SOURCE" in body or "to_list(1)" in body or "where_now" in body
        assert bounded, f"la fonte «{source_name}» non è limitata"


def test_the_contract_forbids_commercial_motives(monkeypatch):
    """
    §27. Not a footnote: a proactive system with a commercial interest is an
    advertising channel wearing an assistant's clothes.
    """
    reasoning = (HERE / "opportunities" / "reasoning.py").read_text(encoding="utf-8")
    assert "no commercial interest" in reasoning
    assert "no partners, no" in reasoning and "sponsors" in reasoning

    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            model = FakeModel([_silence()])
            _install(monkeypatch, model)
            await (await _service(db)).scan(uid)
            system = model.seen[0]["system"]
            assert "Nobody is paying you" in system
            assert "useful to this person" in system
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_contract_says_out_loud_that_facts_are_not_conclusions(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_op_{uuid.uuid4().hex[:8]}"
        try:
            model = FakeModel([_silence()])
            _install(monkeypatch, model)
            await (await _service(db)).scan(uid)
            system = model.seen[0]["system"]
            for line in (
                "an event tomorrow is not an opportunity",
                "a deadline is not an opportunity",
                "being somewhere is not an opportunity",
                "Never invent a deadline",
            ):
                assert line in system, f"il contratto non dice: {line}"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# The surface
# ---------------------------------------------------------------------------

def test_there_is_no_tab_and_no_delivery():
    """
    Sprint 2 §9/§17: a quiet place inside Home, and still nowhere else.

    Sprint 1 asserted that nothing consumed opportunities at all, which was
    true then and is the wrong assertion now — Sprint 2 gave them a line
    inside Aggiornamenti. What has not changed is everything that would make
    them loud: no tab of their own, no dashboard, no route, and above all no
    delivery. A card on a page somebody chose to open is a presence. A push is
    an interruption, and V3.7 does not have one.
    """
    frontend = HERE.parent / "frontend"
    layout = (frontend / "app" / "(tabs)" / "_layout.tsx").read_text(encoding="utf-8")
    assert "opportunit" not in layout.lower(), "è comparsa una tab"

    routes = [
        p.name
        for p in (frontend / "app").rglob("*.tsx")
        if "opportunit" in p.name.lower()
    ]
    assert not routes, f"è comparsa una schermata dedicata: {routes}"

    # Nothing anywhere in the app may reach for a notification because of one.
    delivery = ("Notifications.schedule", "expo-notifications", "registerForPushNotifications")
    for path in list((frontend / "src").rglob("*.ts*")) + list((frontend / "app").rglob("*.tsx")):
        if "node_modules" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "pportunit" not in text:
            continue
        for word in delivery:
            assert word not in text, f"{path.name} consegna un'opportunity"

    router = (HERE / "opportunities" / "router.py").read_text(encoding="utf-8")
    assert "debug surface" in router


# ---------------------------------------------------------------------------
# What the model is told
# ---------------------------------------------------------------------------

def test_the_code_counts_the_days_and_the_model_is_not_asked_to():
    """
    §29: arithmetic is the code's half of the split.

    The live QA caught the model calling the day after tomorrow "in three
    days" — the one part of the sentence a person checks against their own
    calendar. So the count arrives already done.
    """
    from opportunities.snapshot import _days_from_now

    now = datetime(2026, 9, 1, 23, 0, tzinfo=timezone.utc)
    # Domani mattina e' domani, non "fra 0 giorni" perche' mancano dieci ore.
    assert _days_from_now("2026-09-02T09:00:00+00:00", now) == 1
    assert _days_from_now("2026-09-03T09:00:00+00:00", now) == 2
    assert _days_from_now("2026-09-01T23:30:00+00:00", now) == 0
    # Gia' passato: mai un numero negativo da leggere.
    assert _days_from_now("2026-08-20T09:00:00+00:00", now) == 0
    assert _days_from_now(None, now) is None
    assert _days_from_now("non una data", now) is None


def test_the_calendar_hands_over_a_count_and_not_only_a_timestamp(monkeypatch):
    """A snapshot that only carries ISO strings makes the model do the sums."""
    async def body():
        client, db = await _db()
        uid = f"t37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities import snapshot as life_snapshot

            await db.calendar_events.insert_one({
                "user_id": uid, "id": "evt_count", "title": "Visita",
                "start_at": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
                "all_day": False,
            })
            snap = await life_snapshot.build(db, uid)
            event = snap["calendar"][0]
            assert event["in_days"] == 4
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_what_was_settled_is_shown_beside_what_is_still_missing(monkeypatch):
    """
    §33: without this a review can only ever say "nothing has changed".

    An answered question leaves `open` and vanishes from the snapshot, so the
    very fact that resolves a concern is the one fact the reviewer never sees.
    The live QA D failed exactly here before this source existed.
    """
    async def body():
        client, db = await _db()
        uid = f"t37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities import snapshot as life_snapshot
            from waiting.models import OpenQuestion
            from waiting.repository import OpenQuestionRepository

            repo = OpenQuestionRepository(db)
            answered = OpenQuestion(
                user_id=uid, question="Hai gia' il certificato?",
                why_needed="Serve all'appuntamento.", context_label="Residenza",
                dedupe_key=f"t37:{uid}:a",
            )
            still_open = OpenQuestion(
                user_id=uid, question="Che orario preferisci?",
                context_label="Residenza", dedupe_key=f"t37:{uid}:b",
            )
            await repo.insert(answered)
            await repo.insert(still_open)
            await repo.answer(uid, answered.id, answer_raw="Si', preso ieri.", source="user")

            snap = await life_snapshot.build(db, uid)

            open_refs = [r["ref"] for r in snap["open_questions"]]
            settled = snap["recently_settled"]
            assert open_refs == [still_open.id]
            assert [r["ref"] for r in settled] == [answered.id]
            # La risposta arriva nelle parole in cui e' stata data.
            assert settled[0]["answer"] == "Si', preso ieri."

            # E puo' essere citata come prova, altrimenti una review che la usa
            # verrebbe scartata come inventata.
            assert life_snapshot.evidence_refs(snap)[answered.id] == "settled_question"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_unanswered_question_carries_what_is_at_stake(monkeypatch):
    """
    Otherwise the model sees that something was asked and nothing about
    whether the answer still matters — and answers, correctly, that it
    cannot tell.
    """
    async def body():
        client, db = await _db()
        uid = f"t37_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities import snapshot as life_snapshot
            from waiting.models import OpenQuestion
            from waiting.repository import OpenQuestionRepository

            q = OpenQuestion(
                user_id=uid, question="Hai il certificato?",
                why_needed="Senza, l'appuntamento non si conclude.",
                context_label="Residenza", dedupe_key=f"t37:{uid}",
            )
            await OpenQuestionRepository(db).insert(q)
            snap = await life_snapshot.build(db, uid)
            assert snap["open_questions"][0]["why_it_matters"] == (
                "Senza, l'appuntamento non si conclude."
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_uncertainty_is_not_treated_as_a_reason_for_silence():
    """
    §31: the prompt must leave a door open that is not silence.

    Told only that silence is expected, the model answered "I cannot confirm
    the certificate was obtained" and said nothing — two days before the
    appointment. The contract has always had `requires_clarification`; the
    instructions now say when to use it.
    """
    import opportunities.reasoning as reasoning
    import inspect

    text = inspect.getsource(reasoning)
    assert "Silence and uncertainty are not the same thing" in text
    assert "requires_clarification" in text
    # E il divieto di trasformare l'incertezza in un fatto resta.
    assert "never write" in text and "as though it were a fact" in text


def test_a_refusal_is_filed_as_a_refusal_and_the_model_cannot_conclude_one():
    """
    §35: the history has to be readable, and "dismiss" is the user's word.

    A dismissal recorded as `keep` makes the one thing a person did to an
    opportunity invisible in the record of what happened to it. It is also
    the only outcome the model may never reach on its own: refusing is the
    person's decision, so the review vocabulary does not contain it.
    """
    from opportunities.models import DecisionOutcome, ReviewOutcome
    import typing

    review_words = set(typing.get_args(ReviewOutcome))
    decision_words = set(typing.get_args(DecisionOutcome))
    assert "dismiss" not in review_words
    assert "dismiss" in decision_words
    assert review_words < decision_words


def test_the_record_of_a_dismissal_says_dismissed(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"t37_{uuid.uuid4().hex[:8]}"
        try:
            _install(monkeypatch, FakeModel([{
                "opportunities": [{
                    "identity_key": "bollo-auto",
                    "what": "Il bollo scade a fine mese.",
                    "why_it_matters": "Dopo la scadenza si paga una mora.",
                    "why_now": "Mancano pochi giorni.",
                    "relevance": "medium", "urgency": "soon",
                    "confidence": "reasonable",
                    "evidence_refs": ["evt_bollo"],
                }]
            }]))
            await db.calendar_events.insert_one({
                "user_id": uid, "id": "evt_bollo", "title": "Scadenza bollo",
                "start_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
                "all_day": True,
            })
            svc = await _service(db)
            created = (await svc.scan(uid)).created
            assert len(created) == 1

            await svc.dismiss(uid, created[0].id)
            history = await svc.repo.decisions_for(uid, created[0].id)
            assert [d.outcome for d in history] == ["dismiss"]
            assert history[0].source == "user"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())
