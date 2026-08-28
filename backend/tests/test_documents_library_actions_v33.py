"""
V3.3 — "Con azioni suggerite" has to mean what it says.

On the Documenti page, beside a policy ORA had read perfectly and deliberately
said nothing about, the rail claimed:

    Tutti i documenti     1
    In scadenza           1
    Con azioni suggerite  1

The third line was counting proposed event candidates — the pipeline handing a
date onward inside ORA. Nobody had been suggested anything.

The metric is not removed here, it is made true: it now asks the same gate that
decides what reaches a person anywhere else.
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
    for col in ("documents", "life_nodes", "life_profiles", "users"):
        await db[col].delete_many({"user_id": user_id})


async def _library(db, user_id: str):
    from documents.library import build_library

    return await build_library(db, user_id=user_id, domain_labels={})


def _row(library, label):
    return next((r for r in library["summary"] if r["label"] == label), None)


def _policy_doc(user_id: str, *, days_to_due: int = 53, **over):
    """The real record: read at 0.95, no ambiguity, a deadline nearly two months out."""
    due = (_now() + timedelta(days=days_to_due))
    doc = {
        "id": f"doc_{uuid.uuid4().hex[:10]}",
        "user_id": user_id,
        "filename": "polizza_auto.txt",
        "mime_type": "text/plain",
        "display_title": "Polizza Assicurativa Auto Generali Italia",
        "pipeline_status": "awaiting_confirmation",
        "analysis": {
            "macro_category": "contract",
            "confidence": 0.95,
            "requires_review": False,
            "warnings": [],
            "short_description": "Polizza auto Generali per Fiat Panda.",
            "summary": "Polizza auto Generali.",
        },
        "admin_analysis": {
            "amount": "512,40 EUR",
            "due_date": due.date().isoformat(),
            "simple_explanation": "Scadenza pagamento.",
            "completed": False,
            "confidence": 0.65,
        },
        "event_candidates": [{
            "id": "ev1",
            "title": "Scadenza pagamento: 512,40 EUR",
            "status": "proposed",
            "category": "deadline",
            "start_datetime": due.isoformat(),
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

def test_internal_bookkeeping_is_not_counted_as_a_suggestion():
    """A. The screenshot, as a test."""
    async def body():
        client, db = await _db()
        user = f"u_lib_book_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.documents.insert_one(_policy_doc(user))
            library = await _library(db, user)
            assert _row(library, "Con azioni suggerite") is None, (
                f"ORA claimed to be suggesting something: {library['summary']}"
            )
            assert library["items"][0]["open_actions"] == 0
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_a_real_suggestion_is_still_counted():
    """
    B. The metric is made true, not hidden. The same document with a deadline
    close enough to be work — nothing else changed — counts.
    """
    async def body():
        client, db = await _db()
        user = f"u_lib_real_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.documents.insert_one(_policy_doc(user, days_to_due=3))
            library = await _library(db, user)
            row = _row(library, "Con azioni suggerite")
            assert row is not None, library["summary"]
            assert row["value"] == 1
            assert library["items"][0]["open_actions"] >= 1
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_a_question_ora_needs_answered_is_a_suggestion_too():
    """
    B, the other shape: no date at all, but ORA could not read something it
    needs. That is put to the person, so it counts.
    """
    async def body():
        client, db = await _db()
        user = f"u_lib_q_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            doc = _policy_doc(user)
            doc["pipeline_status"] = "needs_review"
            doc["analysis"]["requires_review"] = True
            doc["admin_analysis"]["completed"] = True
            doc["event_candidates"] = [{
                "id": "ev1", "title": "Scadenza", "status": "proposed",
                "ambiguous_date": True, "date_candidates": ["14 ottobre", "17 ottobre"],
                "confidence": 0.4, "missing_fields": [],
            }]
            await db.documents.insert_one(doc)
            row = _row(await _library(db, user), "Con azioni suggerite")
            assert row is not None and row["value"] == 1
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_the_deadline_is_still_counted_separately():
    """C. "In scadenza" is about a date, not about work, and is untouched."""
    async def body():
        client, db = await _db()
        user = f"u_lib_exp_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.documents.insert_one(_policy_doc(user))
            library = await _library(db, user)
            expiring = _row(library, "In scadenza")
            assert expiring is not None and expiring["value"] == 1
            assert len(library["expiring"]) == 1
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_the_document_count_is_unchanged():
    """D."""
    async def body():
        client, db = await _db()
        user = f"u_lib_all_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            for _ in range(3):
                await db.documents.insert_one(_policy_doc(user))
            library = await _library(db, user)
            assert _row(library, "Tutti i documenti")["value"] == 3
            assert len(library["items"]) == 3
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_a_count_of_zero_is_a_row_that_is_not_there():
    """E. No "Con azioni suggerite: 0" — an absence is not a number."""
    async def body():
        client, db = await _db()
        user = f"u_lib_zero_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.documents.insert_one(_policy_doc(user))
            library = await _library(db, user)
            for row in library["summary"]:
                assert row["value"] != 0, row
            labels = [r["label"] for r in library["summary"]]
            assert "Con azioni suggerite" not in labels
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_the_count_asks_the_one_place_that_decides():
    """
    F. Not a second opinion: the same gate, so the page cannot drift from what
    Home does. And nothing here knows what kind of document it is looking at.
    """
    src = (HERE / "documents" / "library.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))

    assert "reason_to_act" in code, "the count still has its own opinion"
    assert 'e.get("status") == "proposed"' not in code, (
        "still counting the pipeline talking to itself"
    )
    for word in ("polizza", "insurance", "bolletta", "mutuo", "fattura"):
        assert word not in code.lower(), f"library knows about {word}"
