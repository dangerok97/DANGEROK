"""
V3.4 — an exchange is not a task because it happened.

Somebody asked what a car inspection costs. ORA answered, correctly, with real
sources. Home then said:

    DA FARE ADESSO
    Conoscere il costo medio della revisione auto
    Continua la collaborazione con ORA

Nobody had taken anything on. There was no goal, no commitment, no deadline, no
decision waiting, nothing anyone had asked ORA to do. The conversation had
simply occurred, and occurring was being read as unfinished work — the same
mistake as the policy card in V3.3, in a different place.

What separates the two here is not what was said. It is whether the reasoning
went on to leave something open: a plan it drew up, a guided flow it started, a
question it is blocked on. Those are artefacts of decisions the model made. The
titles below are deliberately varied and deliberately irrelevant: swap them
between the fixtures and every assertion still holds.
"""

from __future__ import annotations

import ast
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(__file__).resolve().parents[1]


def _run(coro):
    return asyncio.run(coro)


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, user_id: str):
    for col in (
        "conversation_sessions", "open_questions", "life_os_plans", "documents",
        "tasks", "decisions", "home_item_state", "home_snapshots", "home_insights",
        "reminders", "users",
    ):
        await db[col].delete_many({"user_id": user_id})


def _session(user_id: str, summary: str, **over):
    """A conversation that has happened. What it left behind is up to `over`."""
    doc = {
        "id": f"ces_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "status": "waiting_user",
        "summary": summary,
        "origin": "text",
        "goal_id": None,
        "action_session_id": None,
        "project_id": None,
        "resume_token": uuid.uuid4().hex,
        "created_at": _now(),
        "updated_at": _now(),
        # The model fills this on every turn as a running description of what is
        # being discussed — including for a question it simply answered.
        "meta": {"ai_core": {"active_goal": {"summary": summary, "status": "active"}}},
    }
    doc.update(over)
    return doc


def _with_plan(user_id: str, summary: str):
    doc = _session(user_id, summary)
    doc["meta"]["ai_core"]["active_plan_id"] = f"lop_{uuid.uuid4().hex[:12]}"
    return doc


async def _conversation_items(db, user_id: str):
    from home.adapters.conversation_adapter import load_conversation_items

    items, _ = await load_conversation_items(db, user_id)
    return items


async def _home_items(db, user_id: str):
    from home.service import HomeService

    svc = HomeService(db)
    await svc.ensure_indexes()
    home = await svc.build_home(user_id)
    out = []
    if home.primary_focus:
        out.append(home.primary_focus)
    for group in home.priorities:
        for item in group.items:
            out.append(item.model_dump() if hasattr(item, "model_dump") else item)
    return home, out


# ---------------------------------------------------------------------------
# A and D — a question, answered
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "asked",
    [
        "Quanto costa mediamente fare la revisione auto?",
        "Quanto costa la patente B?",
    ],
)
def test_a_question_that_was_answered_is_not_on_anybodys_plate(asked):
    async def body():
        client, db = await _db()
        user = f"u_info_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            await db.conversation_sessions.insert_one(_session(user, asked))

            assert await _conversation_items(db, user) == []
            home, items = await _home_items(db, user)
            assert home.primary_focus is None, home.primary_focus
            assert items == [], [i.get("title") for i in items]
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_ordinary_chit_chat_is_not_work_either():
    async def body():
        client, db = await _db()
        user = f"u_chat_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            await db.conversation_sessions.insert_one(
                _session(user, "Ciao, spiegami in due righe come funzioni.")
            )
            home, items = await _home_items(db, user)
            assert home.primary_focus is None
            assert items == []
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_the_self_referential_card_is_gone_at_the_root():
    """
    "Continua la collaborazione con ORA" was a need of the product's, not of
    the person's. It is not hidden by title — it is not built, because there is
    nothing behind it.
    """
    async def body():
        client, db = await _db()
        user = f"u_selfref_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            for text in ("Ciao!", "Quanto costa la revisione?", "Grazie, utile."):
                await db.conversation_sessions.insert_one(_session(user, text))
            _, items = await _home_items(db, user)
            assert not any(
                "collaborazione con ORA" in str(i.get("description") or "") for i in items
            ), items
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# B, C and E — something was actually left open
# ---------------------------------------------------------------------------

def test_a_conversation_that_produced_a_plan_is_still_work():
    """
    E. "Voglio prendere la patente B quest'anno, aiutami a organizzarmi" — ORA
    draws something up, and the plan is waiting.
    """
    async def body():
        client, db = await _db()
        user = f"u_goal_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            await db.conversation_sessions.insert_one(
                _with_plan(user, "Prendere la patente B quest'anno")
            )
            items = await _conversation_items(db, user)
            assert len(items) == 1
            assert items[0].meta["work_reason"] == "goal_blocker"
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_a_guided_flow_part_way_through_is_still_work():
    """B. A commitment ORA started acting on: steps exist and are unfinished."""
    async def body():
        client, db = await _db()
        user = f"u_flow_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            await db.conversation_sessions.insert_one(
                _session(
                    user,
                    "Vorrei ricordarmi di fare la revisione dell'auto entro ottobre.",
                    action_session_id="aes_x",
                )
            )
            items = await _conversation_items(db, user)
            assert len(items) == 1
            assert items[0].meta["work_reason"] == "user_request"
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_a_conversation_stopped_on_a_question_is_still_work():
    """
    C. V3.1, untouched: an OpenQuestion means work halted and only this person
    can restart it. Home has to be able to bring them back.
    """
    async def body():
        client, db = await _db()
        user = f"u_block_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            session = _session(
                user, "Sto valutando se vendere la macchina prima della revisione."
            )
            await db.conversation_sessions.insert_one(session)

            from waiting.models import ResumePointer, WorkRefs
            from waiting.service import get_waiting_service

            service = get_waiting_service(db)
            await service.ensure_indexes()
            await service.record_blocking_question(
                user,
                question="Entro quando devi decidere?",
                refs=WorkRefs(session_id=session["id"]),
                resume=ResumePointer(session_id=session["id"]),
            )
            items = await _conversation_items(db, user)
            assert len(items) == 1, [i.title for i in items]
            assert items[0].meta["work_reason"] == "confirmation_required"
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# How it decides
# ---------------------------------------------------------------------------

def test_nothing_here_reads_what_anybody_said():
    """
    §2 and §10. No keyword, no regex over a title, no category, no phrase map.
    The adapter looks at artefacts of decisions and nothing else — which is why
    the two fixtures above can swap titles and still behave the same.
    """
    src = (HERE / "home" / "adapters" / "conversation_adapter.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))

    decider = code[code.index("def _what_it_left_behind"):]
    decider = decider[: decider.index("\ndef ")] if "\ndef " in decider else decider
    for reading in ("summary", "title", "lower()", "startswith", "in text", "re.", "intent =="):
        assert reading not in decider, f"the decision reads {reading}"
    assert "import re" not in code


def test_swapping_the_titles_changes_nothing():
    """The same statement, made by construction rather than by inspection."""
    async def body():
        client, db = await _db()
        user = f"u_swap_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            # The "goal-sounding" sentence, with nothing behind it.
            await db.conversation_sessions.insert_one(
                _session(user, "Voglio prendere la patente B quest'anno, aiutami a organizzarmi")
            )
            assert await _conversation_items(db, user) == []

            # The "question-sounding" sentence, with a plan behind it.
            await db.conversation_sessions.insert_one(
                _with_plan(user, "Quanto costa mediamente fare la revisione auto?")
            )
            items = await _conversation_items(db, user)
            assert len(items) == 1
            assert items[0].meta["work_reason"] == "goal_blocker"
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_conversations_go_through_the_same_gate_as_everything_else():
    from home.work_admission import KNOWLEDGE_SOURCES

    assert "conversation_session" in KNOWLEDGE_SOURCES
