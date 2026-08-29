"""
V3.4 — a window must not become a day.

Somebody said "vorrei prendere la patente B quest'anno", in August 2026. The
plan came back with a target of 24 June 2027 and Home counted down to it:
"tra 299g · gio 24 giu". Nobody had said June. Nobody had said 2027. The year
they *had* named was already contradicted by the date.

The cause was not the countdown, which was doing its job. It was that the plan
could hold exactly two things — a day, or nothing — so a period had nowhere to
go and arrived as a day.

What is tested here is that the grades of precision survive the trip: what
somebody said stays as precise as they said it and no more, from the plan
through ranking to what is rendered. The subjects below are a licence, a house
and a language exam, and the code cannot tell them apart.
"""

from __future__ import annotations

import ast
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
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


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, user_id: str):
    for col in ("life_os_plans", "conversation_sessions", "home_item_state", "users"):
        await db[col].delete_many({"user_id": user_id})


def _end_of_this_year() -> str:
    return date(datetime.now(timezone.utc).year, 12, 31).isoformat()


async def _make_plan(db, user_id: str, **kwargs):
    from life_os.service import LifeOsService

    return await LifeOsService(db).create_plan(
        user_id,
        summary=kwargs.pop("summary", "Un obiettivo"),
        items=[{"title": "Primo passo"}, {"title": "Secondo passo"}],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# The five grades
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "summary,said",
    [
        ("Prendere la patente B quest'anno", "quest'anno"),
        ("Comprare casa quest'anno", "quest'anno"),
        ("Dare la certificazione di inglese quest'anno", "quest'anno"),
    ],
)
def test_a_year_stays_inside_the_year_whatever_it_is_about(summary, said):
    """
    §7.1 and §7.10. The end of the window is the end of *this* year, and there
    is no day to count down to. Three subjects, one code path, identical result.
    """
    async def body():
        client, db = await _db()
        user = f"u_win_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            plan = await _make_plan(
                db, user, summary=summary,
                target={"precision": "window", "as_said": said, "latest": _end_of_this_year()},
            )
            assert plan.target.precision == "window"
            assert plan.target.as_said == said
            assert plan.target.latest == _end_of_this_year()
            # The thing everything downstream reads as a deadline stays empty.
            assert plan.target_date is None, plan.target_date
            assert plan.target.exact_day is None
            # And the window cannot end in a later year.
            assert plan.target.latest[:4] == str(datetime.now(timezone.utc).year)
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_a_day_somebody_gave_stays_a_day():
    """§7.3. The rule is about invented precision, not about precision."""
    async def body():
        client, db = await _db()
        user = f"u_exact_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            plan = await _make_plan(
                db, user,
                target={
                    "precision": "exact", "as_said": "entro il 20 novembre 2026",
                    "earliest": "2026-11-20", "latest": "2026-11-20",
                },
            )
            assert plan.target_date == "2026-11-20"
            assert plan.target.precision == "exact"
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_the_older_shape_still_works():
    """A bare `target_date` is a day, and is read as one."""
    async def body():
        client, db = await _db()
        user = f"u_legacy_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            plan = await _make_plan(db, user, target_date="2026-11-20")
            assert plan.target_date == "2026-11-20"
            assert plan.target.precision == "exact"
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_a_distance_stays_a_distance():
    """
    §7.4. "nei prossimi tre mesi" is a horizon. It fixes how far out the far
    edge is and never becomes the day itself — turning a distance into a date
    is the same mistake in a different sentence.
    """
    async def body():
        client, db = await _db()
        user = f"u_hor_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            plan = await _make_plan(db, user, resolve_relative_days=90)
            assert plan.target.precision == "horizon"
            assert plan.target_date is None
            expected = (datetime.now(timezone.utc).date() + timedelta(days=90)).isoformat()
            assert plan.target.latest == expected
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_saying_nothing_creates_no_deadline():
    """§7.5."""
    async def body():
        client, db = await _db()
        user = f"u_none_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            plan = await _make_plan(db, user)
            assert plan.target_date is None
            assert plan.target.precision == "none"
            assert plan.target.latest is None
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_claiming_a_day_without_giving_one_is_not_a_day():
    """
    The shape the failure would take next: `precision: exact` with nothing in
    it. Whatever that was, it was less than exact.
    """
    async def body():
        client, db = await _db()
        user = f"u_bad_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            plan = await _make_plan(
                db, user,
                target={"precision": "exact", "as_said": "presto", "latest": _end_of_this_year()},
            )
            assert plan.target_date is None
            assert plan.target.precision == "window"
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# Downstream: nothing invents a day either
# ---------------------------------------------------------------------------

def test_home_shows_no_countdown_for_a_window_and_one_for_a_day():
    """§7.6 and §7.7: presentation and ranking both read the same field."""
    async def body():
        client, db = await _db()
        user = f"u_home_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            await _make_plan(
                db, user, summary="Prendere la patente B quest'anno",
                target={
                    "precision": "window", "as_said": "quest'anno",
                    "latest": _end_of_this_year(),
                },
            )
            from home.adapters.life_os_plan import load_life_os_plans

            items, _ = await load_life_os_plans(db, user)
            assert items, "the plan itself must still be work"
            plan_item = items[0]
            assert plan_item.due_at is None, plan_item.due_at
            assert (plan_item.meta or {}).get("goal_target_date") is None
            assert (plan_item.meta or {}).get("goal_target_said") == "quest'anno"

            from home.ranking import rank_items

            ranked = rank_items([plan_item])
            assert ranked[0].due_at is None, "ranking invented a day"
            assert ranked[0].urgency in ("none", "upcoming"), ranked[0].urgency
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_nothing_reaches_the_calendar_from_a_window():
    """
    §7.8. A calendar entry is a day and an hour. A period is neither, and the
    only field that could carry one into a calendar is empty for a window.
    """
    async def body():
        client, db = await _db()
        user = f"u_cal_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            plan = await _make_plan(
                db, user,
                target={"precision": "window", "as_said": "quest'anno", "latest": _end_of_this_year()},
            )
            stored = await db.life_os_plans.find_one({"id": plan.id}, {"_id": 0})
            assert stored["target_date"] is None
            assert all(not (i.get("due_date")) for i in stored["items"])
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# How it decides
# ---------------------------------------------------------------------------

def test_no_phrase_is_written_anywhere_in_the_temporal_code():
    """
    §3 and §7.9. The precision is what the model reported, not what a regex
    recognised. No "quest'anno", no month names, no Italian-to-December map,
    and no subject.
    """
    banned = (
        "quest'anno", "questanno", "quest anno", "questo mese", "prossimi",
        "estate", "natale", "dicembre", "patente", "mutuo", "esame",
    )
    for path in (
        HERE / "life_os" / "service.py",
        HERE / "life_os" / "models.py",
        HERE / "home" / "adapters" / "life_os_plan.py",
    ):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        # Prose is allowed to name the failure it describes; code is not.
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docs.add(doc)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if node.value in docs:
                continue
            lowered = node.value.lower()
            for phrase in banned:
                assert phrase not in lowered, f"{path.name} contains {phrase!r}"


def test_the_only_route_to_a_deadline_is_an_exact_day():
    """
    The guarantee, stated once: `target_date` is filled from `exact_day` and
    from nothing else, so no path exists by which a window becomes a deadline.
    """
    src = (HERE / "life_os" / "service.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert "td = target_intent.exact_day" in code
    assert "plan.target_date = plan.target.exact_day" in code

    from life_os.models import TemporalTarget

    for precision in ("window", "horizon", "none"):
        target = TemporalTarget(
            precision=precision, earliest="2027-06-24", latest="2027-06-24"
        )
        assert target.exact_day is None, precision


def test_the_reasoning_is_told_not_to_fill_in_a_day():
    """
    §5. The contract can hold a window now; the model still has to use it. It
    is told the grades and told that inventing a day is not a helpful default —
    and that asking is the alternative when a day genuinely matters.
    """
    from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    text = COGNITIVE_SYSTEM_PROMPT.lower()
    assert "record it as precisely as it was said, and no more" in text
    assert "if a day genuinely matters for the next step, ask" in text

    spec = ToolRegistry().get("create_plan")
    described = (spec.description or "").lower()
    assert "at the grade the person actually expressed" in described
    # Both mistakes are named, because they are opposite and both were made:
    # a day nobody gave, and a constraint recorded as nothing.
    assert "a date nobody chose" in described
    assert "throws away something they told you" in described

    target = spec.input_schema["properties"]["target"]
    assert target["properties"]["precision"]["enum"] == [
        "exact", "window", "horizon", "none"
    ]
    # The grades are explained by what somebody did, not by phrases to match.
    grades = target["properties"]["precision"]["description"].lower()
    assert "a determined day was given" in grades
    assert "no calendar boundary" in grades
    assert "only when the person said nothing" in grades


def test_nothing_was_said_cannot_be_claimed_while_holding_what_was_said():
    """
    The residual blocker, as an invariant. The first real run came back
    `precision: none` for somebody who had said "quest'anno" — no invented
    date, which was the point, and no constraint either, which was not.

    `none` is a claim that nothing was said. It cannot be made while holding
    an edge or their words. Nothing here reads what the words mean.
    """
    from life_os.models import TemporalTarget

    kept_words = TemporalTarget(precision="none", as_said="quest'anno")
    assert kept_words.precision == "horizon"
    assert kept_words.is_stated

    kept_edge = TemporalTarget(precision="none", latest="2026-12-31")
    assert kept_edge.precision == "window"
    assert kept_edge.exact_day is None

    said_nothing = TemporalTarget(precision="none")
    assert said_nothing.precision == "none"
    assert not said_nothing.is_stated
    assert said_nothing.exact_day is None


def test_a_grade_that_carries_no_boundary_is_not_a_window():
    """The mirror of it: a period has edges, or it was a distance."""
    from life_os.models import TemporalTarget

    assert TemporalTarget(precision="window", as_said="presto").precision == "horizon"
    assert TemporalTarget(
        precision="window", as_said="quest'anno", latest="2026-12-31"
    ).precision == "window"


def test_the_invariant_reads_no_words():
    """
    §3. The validator decides on presence and absence, never on meaning: swap
    the words for any others, in any language, and it behaves identically.
    """
    from life_os.models import TemporalTarget

    for words in ("quest'anno", "this year", "before the summer", "asap", "叁月内"):
        assert TemporalTarget(precision="none", as_said=words).precision == "horizon"
        assert TemporalTarget(
            precision="none", as_said=words, latest="2026-12-31"
        ).precision == "window"

    src = (HERE / "life_os" / "models.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    validator = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_coherent"
    )
    body = ast.dump(validator).lower()
    for reading in ("startswith", "lower()", "regex", "re.", "in self.as_said"):
        assert reading not in body, f"the invariant reads the words: {reading}"
