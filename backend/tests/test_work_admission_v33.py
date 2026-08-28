"""
V3.3 — knowledge acquisition must not create work by itself.

The recording: somebody uploaded their car insurance policy during the first
setup. ORA read it correctly — 0.95 confidence, no warnings, no ambiguous
field, `requires_review` false — and produced five things for them to do,
starting with a card carrying the document's own name and a "Verifica" button.

Nothing in that document needed a decision, a confirmation, or an action. The
work existed because a file had been read.

These tests run the real Home against real document records. The word
"polizza" appears in the fixtures because that is where the bug was found;
none of the rules under test know what a policy is.
"""

from __future__ import annotations

import ast
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")

HERE = Path(__file__).resolve().parents[1]


def _run(coro):
    return asyncio.run(coro)


def _now():
    return datetime.now(timezone.utc)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, user_id: str):
    for col in (
        "documents", "decisions", "tasks", "life_nodes", "ingestion_events",
        "home_item_state", "home_snapshots", "home_insights", "reminders", "users",
        "user_profiles",
    ):
        await db[col].delete_many({"user_id": user_id})


async def _home(db, user_id: str):
    from home.service import HomeService

    svc = HomeService(db)
    await svc.ensure_indexes()
    return await svc.build_home(user_id)


def _items(home):
    out = []
    if home.primary_focus:
        out.append(home.primary_focus)
    for group in home.priorities:
        for item in group.items:
            out.append(item.model_dump() if hasattr(item, "model_dump") else item)
    return out


# The policy exactly as the pipeline stored it, the day it went wrong: read
# well, understood, and with a payment deadline two and a half weeks out.
def _policy_doc(user_id: str, *, days_to_due: int = 18, **over):
    due = (_now() + timedelta(days=days_to_due)).date().isoformat()
    doc = {
        "id": f"doc_{uuid.uuid4().hex[:10]}",
        "user_id": user_id,
        "filename": "polizza_auto.txt",
        "display_title": "Polizza Assicurativa Auto - Generali Italia",
        "pipeline_status": "awaiting_confirmation",
        "analysis": {
            "macro_category": "contract",
            "subcategory": "insurance_policy",
            "confidence": 0.95,
            "requires_review": False,
            "warnings": [],
            "suggested_title": "Polizza Assicurativa Auto - Generali Italia",
            "short_description": "Polizza auto Generali per Fiat Panda.",
        },
        "admin_analysis": {
            "document_number": "402118893",
            "amount": "512,40 EUR",
            "due_date": due,
            "simple_explanation": f"Importo indicato: 512,40 EUR. Scadenza: {due}.",
            "completed": False,
            "priority": "high",
            "urgency": "soon",
            "confidence": 0.65,
        },
        "event_candidates": [{
            "id": "ev1",
            "title": "Scadenza pagamento: 512,40 EUR",
            "status": "proposed",
            "start_datetime": f"{due}T09:00:00+00:00",
            "confidence": 0.65,
            "ambiguous_date": False,
            "missing_fields": [],
        }],
        "generic_actions": [
            {"id": "g1", "action_type": "create_reminder", "title": "Promemoria scadenza",
             "label": "Promemoria scadenza", "completed": False},
            {"id": "g2", "action_type": "needs_review", "title": "Revisione richiesta",
             "label": "Revisione richiesta", "completed": False},
        ],
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }
    doc.update(over)
    return doc


# ---------------------------------------------------------------------------
# Reading is not working
# ---------------------------------------------------------------------------

def test_ingesting_a_document_creates_no_work_at_all():
    """The recording, as a test: upload, read well, and Home stays quiet."""
    async def body():
        client, db = await _db()
        user = f"u_wa_ingest_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            await db.documents.insert_one(_policy_doc(user))
            home = await _home(db, user)
            assert home.primary_focus is None, (
                f"reading a document opened the day with {home.primary_focus!r}"
            )
            assert _items(home) == [], (
                f"a well-read document still produced work: "
                f"{[i.get('title') for i in _items(home)]}"
            )
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_a_document_ora_understood_never_becomes_a_review_card():
    """
    No card carrying the document's own name, and no "Verifica" on something
    nobody was asked about. `awaiting_confirmation` means ORA proposed
    something to itself, which is not a job for anybody else.
    """
    async def body():
        client, db = await _db()
        user = f"u_wa_review_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            await db.documents.insert_one(_policy_doc(user))
            titles = [str(i.get("title") or "") for i in _items(await _home(db, user))]
            assert not any("Polizza Assicurativa Auto" in t for t in titles), titles
            assert not any(
                i.get("type") in ("needs_review", "verify") for i in _items(await _home(db, user))
            )
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_a_confident_reading_asks_nothing():
    """`blocking_uncertainty` is the whole of it: sure means silent."""
    from home.adapters.document_uncertainty import blocking_uncertainty

    assert blocking_uncertainty(_policy_doc("u")) is None


def test_ora_keeps_its_own_bookkeeping_to_itself():
    """
    "Promemoria scadenza" and "Revisione richiesta" are notes the analyzer
    writes to itself off the back of a category. They stay in the record and
    out of the day.
    """
    async def body():
        client, db = await _db()
        user = f"u_wa_book_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            doc = _policy_doc(user)
            await db.documents.insert_one(doc)
            titles = [str(i.get("title") or "") for i in _items(await _home(db, user))]
            assert "Promemoria scadenza" not in titles
            assert "Revisione richiesta" not in titles
            # Still on the document, for whatever reads documents.
            stored = await db.documents.find_one({"id": doc["id"]}, {"_id": 0})
            assert len(stored.get("generic_actions") or []) == 2
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# Uncertainty: only when it is real, and only about the thing that is unclear
# ---------------------------------------------------------------------------

def test_an_uncertainty_about_nothing_in_particular_asks_nothing():
    """
    Marked for review with no field behind it, on a document read well enough.
    "Controlla questo documento" with nothing to check is not a question.
    """
    from home.adapters.document_uncertainty import blocking_uncertainty

    doc = _policy_doc("u")
    doc["analysis"]["requires_review"] = True
    doc["analysis"]["confidence"] = 0.82
    doc["event_candidates"] = [{
        "id": "ev1", "title": "Scadenza", "status": "proposed",
        "start_datetime": doc["event_candidates"][0]["start_datetime"],
        "confidence": 0.8, "ambiguous_date": False, "missing_fields": [],
    }]
    assert blocking_uncertainty(doc) is None


def test_an_unreadable_date_becomes_exactly_one_question_about_the_date():
    """
    §"Non riesco a capire se la scadenza è il 14 o il 17 ottobre." One item,
    phrased as the question, naming the field — not the document handed back.
    """
    async def body():
        client, db = await _db()
        user = f"u_wa_amb_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            doc = _policy_doc(user)
            doc["pipeline_status"] = "needs_review"
            doc["analysis"]["requires_review"] = True
            doc["event_candidates"] = [{
                "id": "ev1", "title": "Scadenza pagamento", "status": "proposed",
                "ambiguous_date": True, "date_candidates": ["14 ottobre", "17 ottobre"],
                "confidence": 0.4, "missing_fields": [],
            }]
            doc["admin_analysis"]["completed"] = True
            await db.documents.insert_one(doc)

            items = _items(await _home(db, user))
            questions = [i for i in items if (i.get("meta") or {}).get("uncertain_field")]
            assert len(questions) == 1, [i.get("title") for i in items]
            q = questions[0]
            assert q["meta"]["uncertain_field"] == "date"
            assert q["meta"]["work_reason"] == "confirmation_required"
            assert "14 ottobre" in q["title"] and "17 ottobre" in q["title"], q["title"]
            assert "Polizza Assicurativa Auto" not in q["title"]
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# What a document is still allowed to do
# ---------------------------------------------------------------------------

def test_the_document_is_still_in_documenti():
    """The gate is about the day, not about the record."""
    async def body():
        client, db = await _db()
        user = f"u_wa_lib_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            doc = _policy_doc(user)
            await db.documents.insert_one(doc)
            await _home(db, user)

            from documents.library import build_library

            library = await build_library(db, user_id=user, domain_labels={})
            ids = [
                d.get("id")
                for section in (library.get("sections") or [])
                for d in (section.get("items") or [])
            ] or [d.get("id") for d in (library.get("items") or [])]
            assert doc["id"] in ids, library
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_the_facts_still_reach_the_life_profile():
    """
    A document that produces no work still teaches ORA. The profile reads what
    the extraction wrote, exactly as before.
    """
    async def body():
        client, db = await _db()
        user = f"u_wa_prof_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            await db.documents.insert_one(_policy_doc(user))

            from life_setup.profile_service import LifeProfileService as Profiles

            await Profiles(db).upsert_fact(
                user,
                domain="auto",
                key="auto.assicurazione_scadenza",
                value="2026-09-15",
                source="document_extract",
            )
            await _home(db, user)

            from life_profile.service import LifeProfileService

            facts, provenance, _ = await LifeProfileService(db)._profile_facts(user)
            assert facts.get("auto.assicurazione_scadenza") == "2026-09-15"
            assert provenance.get("auto.assicurazione_scadenza")
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_the_same_deadline_arrives_on_its_own_when_it_gets_close():
    """
    Nothing is thrown away. The date that was too far off to matter is the same
    date that opens the day a week later — no new ingestion, no re-upload, the
    identical document record read on a different day.
    """
    async def body():
        client, db = await _db()
        user = f"u_wa_soon_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            far = _policy_doc(user, days_to_due=18)
            await db.documents.insert_one(far)
            assert _items(await _home(db, user)) == []

            await db.documents.update_one(
                {"id": far["id"]},
                {"$set": {
                    "admin_analysis.due_date": (_now() + timedelta(days=3)).date().isoformat(),
                    "event_candidates.0.start_datetime": (
                        _now() + timedelta(days=3)
                    ).isoformat(),
                }},
            )
            items = _items(await _home(db, user))
            assert items, "a deadline three days out never came back"
            assert any(
                (i.get("meta") or {}).get("work_reason") in ("deadline", "consent")
                for i in items
            ), [(i.get("title"), (i.get("meta") or {}).get("work_reason")) for i in items]
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_something_the_person_deferred_is_still_theirs():
    """
    The gate must not quietly clear what somebody chose to postpone. They were
    shown it and pushed it back: that is their decision, not an ingestion
    artefact.
    """
    async def body():
        client, db = await _db()
        user = f"u_wa_def_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            doc = _policy_doc(user, days_to_due=40)
            doc["admin_analysis"]["deferred"] = True
            doc["event_candidates"] = []
            await db.documents.insert_one(doc)
            items = _items(await _home(db, user))
            assert any(
                (i.get("meta") or {}).get("work_reason") == "user_request" for i in items
            ), [(i.get("title"), (i.get("meta") or {}).get("work_reason")) for i in items]
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# The rule itself
# ---------------------------------------------------------------------------

def test_every_reason_is_about_the_person_and_none_is_about_ingestion():
    from home.work_admission import WORK_REASONS

    assert WORK_REASONS == {
        "decision", "confirmation_required", "deadline", "risk",
        "goal_blocker", "user_request", "opportunity", "consent",
    }
    for not_a_reason in ("document_processed", "ingested", "analyzed", "known", "extracted"):
        assert not_a_reason not in WORK_REASONS


def test_an_item_with_no_reason_is_not_admitted():
    """The gate itself, without a database: no reason, no place in the day."""
    from home.models import HomeItem
    from home.work_admission import admit

    read_something = HomeItem(
        id="x", type="needs_review", title="Un documento qualsiasi",
        source_type="document", source_id="doc_x",
    )
    assert admit([read_something], now=_now()) == []

    theirs = HomeItem(
        id="y", type="activity", title="Qualcosa che ha chiesto lei",
        source_type="task", source_id="t_y",
    )
    assert len(admit([theirs], now=_now())) == 1


def test_nothing_in_the_rule_knows_what_it_is_reading():
    """§28. No `if insurance`, no category special-cased anywhere in the gate."""
    banned = ("polizza", "insurance", "bolletta", "mutuo", "fattura", "esame", "invoice")
    for name in ("work_admission.py", "adapters/document_uncertainty.py"):
        src = (HERE / "home" / name).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    src = src.replace(doc, "")
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        for word in banned:
            assert word not in code.lower(), f"{name} knows about {word}"


def test_the_adapter_itself_refuses_to_build_the_card():
    """
    Not only the gate. The adapter is where the card used to be born, and it
    has to stop being born there — otherwise the day is quiet by luck, and the
    next thing that reads these items inherits the same wrong idea.
    """
    async def body():
        client, db = await _db()
        user = f"u_wa_adapter_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.documents.insert_one(_policy_doc(user))

            from home.adapters.documents import load_documents

            items, _ = await load_documents(db, user)
            assert not any(i.type in ("needs_review", "verify") for i in items), (
                f"the adapter still builds a review card: "
                f"{[(i.type, i.title) for i in items]}"
            )
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_an_ambiguity_ora_did_not_flag_is_not_a_question():
    """
    The guard, on its own. A proposal state means ORA is talking to itself, and
    a field it never said it was unsure about is not something to ask.
    """
    from home.adapters.document_uncertainty import blocking_uncertainty

    doc = _policy_doc("u")
    doc["event_candidates"][0]["ambiguous_date"] = True
    doc["event_candidates"][0]["date_candidates"] = ["14 ottobre", "17 ottobre"]
    assert doc["pipeline_status"] == "awaiting_confirmation"
    assert not doc["analysis"]["requires_review"]
    assert blocking_uncertainty(doc) is None


def test_a_real_ambiguity_is_asked_even_while_ora_has_a_proposal_open():
    """
    The two are independent. ORA proposing an event to itself says nothing
    about whether it could read the date, and a document can carry both.
    """
    from home.adapters.document_uncertainty import blocking_uncertainty

    doc = _policy_doc("u")
    doc["analysis"]["requires_review"] = True
    doc["event_candidates"][0]["ambiguous_date"] = True
    doc["event_candidates"][0]["date_candidates"] = ["14 ottobre", "17 ottobre"]
    found = blocking_uncertainty(doc)
    assert found and found["field"] == "date"
    assert "14 ottobre" in found["question"]


def test_an_amount_is_not_given_its_currency_twice():
    """
    Found on the same real policy, in Documenti: "Scadenza pagamento: 512,40
    EUR EUR". The extraction keeps the amount as the document wrote it, and
    the label was appending the currency to it regardless.
    """
    from types import SimpleNamespace

    from documents.intelligence.analyzer import _admin_deadline_title

    def title_for(amount):
        admin = SimpleNamespace(
            sender=None, subject=None, amount=amount, currency="EUR",
        )
        return _admin_deadline_title(admin=admin, title="", text="")

    assert title_for("512,40 EUR") == "Scadenza pagamento: 512,40 EUR"
    # And an amount written without one still gets it.
    assert title_for("512,40") == "Scadenza pagamento: 512,40 EUR"
