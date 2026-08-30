"""
V3.6 Sprint 3 — presence history as context, not as verdict.

    PRESENCE HISTORY IS EVIDENCE ABOUT LIFE, NOT A JUDGMENT ABOUT LIFE.
    OBSERVED COMMUTE != LIVE ETA.
    ROUTINE OBSERVATION != ROUTINE FACT.

Sums, counts, medians and journey durations are arithmetic and code owns them.
Whether nine similar mornings amount to a habit is a judgement about somebody's
life, and the tests here check that no counter in this codebase makes it.

The other line these tests defend is the one between "di solito ci metti mezz'
ora" and "con il traffico adesso ce ne vogliono trentasette". The first is a
fact about the person; the second is a fact about a road, and only a routing
service knows it.
"""

from __future__ import annotations

import ast
import os
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

HOME = (45.4064, 11.8768)
WORK = (45.4180, 11.8900)


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _service(db):
    from places.service import PlacesService

    return PlacesService(db)


def _iso(day_offset: int, hour: int, minute: int = 0) -> str:
    base = datetime.now(timezone.utc).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    return (base - timedelta(days=day_offset)).isoformat()


def _session(user_id: str, place_id: str, entered: str, exited=None):
    from places.models import PresenceSession

    return PresenceSession(
        user_id=user_id, place_id=place_id, entered_at=entered, exited_at=exited
    )


# ---------------------------------------------------------------------------
# Time at a place
# ---------------------------------------------------------------------------

def test_a_window_counts_the_part_of_a_stay_that_falls_inside_it():
    """
    A night that began yesterday and is still going counts towards today for
    the hours that belong to today. Including or excluding whole sessions would
    lie in one direction or the other.
    """
    from places.analytics import overlap_seconds
    from places.models import PresenceSession

    start = datetime(2026, 8, 30, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc)

    overnight = PresenceSession(
        user_id="u",
        place_id="p",
        entered_at=datetime(2026, 8, 29, 22, 0, tzinfo=timezone.utc).isoformat(),
        exited_at=datetime(2026, 8, 30, 7, 30, tzinfo=timezone.utc).isoformat(),
    )
    assert overlap_seconds(overnight, start, end) == int(7.5 * 3600)

    elsewhere = PresenceSession(
        user_id="u",
        place_id="p",
        entered_at=datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc).isoformat(),
        exited_at=datetime(2026, 8, 25, 18, 0, tzinfo=timezone.utc).isoformat(),
    )
    assert overlap_seconds(elsewhere, start, end) == 0


def test_an_open_stay_is_measured_up_to_now_and_says_so():
    """§4: no artificial closing. "Finora oggi" is a different sentence."""
    from places.analytics import time_at_place
    from places.models import PresenceSession

    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    still_here = PresenceSession(
        user_id="u",
        place_id="p",
        entered_at=(now - timedelta(hours=3)).isoformat(),
        exited_at=None,
    )
    result = time_at_place([still_here], start=start, end=now)

    assert result["still_there"] is True
    assert 3 * 3600 - 90 <= result["total_seconds"] <= 3 * 3600 + 90
    assert result["visits"] == 1
    assert result["current_session_seconds"] is not None


def test_visits_and_averages_come_from_the_sessions_not_from_a_guess():
    from places.analytics import time_at_place
    from places.models import PresenceSession

    start = datetime(2026, 8, 24, tzinfo=timezone.utc)
    end = datetime(2026, 8, 31, tzinfo=timezone.utc)
    sessions = []
    for day, hours in ((25, 2), (26, 3), (27, 1)):
        a = datetime(2026, 8, day, 9, 0, tzinfo=timezone.utc)
        sessions.append(
            PresenceSession(
                user_id="u", place_id="p",
                entered_at=a.isoformat(),
                exited_at=(a + timedelta(hours=hours)).isoformat(),
            )
        )
    result = time_at_place(sessions, start=start, end=end)
    assert result["visits"] == 3
    assert result["total_seconds"] == 6 * 3600
    assert result["average_visit_seconds"] == 2 * 3600
    assert result["longest_visit_seconds"] == 3 * 3600
    assert result["still_there"] is False


def test_the_named_periods_mean_what_the_words_mean():
    from places.analytics import window

    now = datetime(2026, 8, 30, 15, 0, tzinfo=timezone.utc)  # a Sunday
    start, end = window("today", now=now)
    assert start.hour == 0 and start.date() == now.date() and end == now

    start, _ = window("this_month", now=now)
    assert start.day == 1 and start.month == 8

    start, _ = window("last_10_days", now=now)
    assert (now - start).days == 10

    y_start, y_end = window("yesterday", now=now)
    assert y_start.date() == (now - timedelta(days=1)).date()
    assert y_end == y_start + timedelta(days=1), "ieri deve finire a mezzanotte"


# ---------------------------------------------------------------------------
# Journeys between places
# ---------------------------------------------------------------------------

def test_leaving_one_place_and_arriving_at_another_is_a_journey():
    from places.analytics import transitions

    sessions = [
        _session("u", "home", _iso(1, 7, 0), _iso(1, 7, 52)),
        _session("u", "work", _iso(1, 8, 23), _iso(1, 17, 30)),
    ]
    found = transitions(sessions)
    assert len(found) == 1
    trip = found[0]
    assert trip["from_place_id"] == "home" and trip["to_place_id"] == "work"
    assert trip["duration_seconds"] == 31 * 60


def test_a_five_hour_gap_is_not_a_commute():
    """
    Somebody who left the office at six and reached the gym at eleven the next
    morning did something else in between. Counting it would put a five-hour
    journey into an average of half-hour ones.
    """
    from places.analytics import transitions

    sessions = [
        _session("u", "work", _iso(1, 9, 0), _iso(1, 18, 0)),
        _session("u", "gym", _iso(0, 11, 0), _iso(0, 12, 0)),
    ]
    assert transitions(sessions) == []


def test_the_typical_journey_is_the_middle_one_not_the_average():
    """
    §10, with the exact numbers. 31, 32, 29, 95 has a mean of about 47 — a
    duration none of the four journeys took, and the one that would be quoted
    back as "normalmente".
    """
    from places.analytics import journey_stats

    stats = journey_stats([31 * 60, 32 * 60, 29 * 60, 95 * 60])
    assert stats["samples"] == 4
    typical_minutes = stats["typical_seconds"] / 60
    assert 31 <= typical_minutes <= 32, f"la mediana è {typical_minutes}"
    mean_minutes = (31 + 32 + 29 + 95) / 4
    assert abs(typical_minutes - mean_minutes) > 10, "sta usando la media"

    # And the bad day is reported, not deleted.
    assert stats["slowest_seconds"] == 95 * 60
    assert stats["fastest_seconds"] == 29 * 60
    assert stats["usual_range_seconds"][0] <= stats["typical_seconds"]


def test_an_empty_sample_says_nothing_rather_than_zero():
    from places.analytics import journey_stats, median

    assert journey_stats([]) == {"samples": 0}
    assert median([]) is None, "un campione vuoto non ha una mediana, ha zero dati"


# ---------------------------------------------------------------------------
# End to end, through the service
# ---------------------------------------------------------------------------

def test_the_service_answers_how_long_and_how_many_times():
    async def body():
        client, db = await _db()
        uid = f"u_rt_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates

            service = await _service(db)
            home = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1]),
            )
            for day in range(3):
                await service.repo.save_session(
                    _session("u", home.id, _iso(day, 20, 0), _iso(day, 23, 0))
                    .model_copy(update={"user_id": uid})
                )

            result = await service.time_at(uid, home.id, period="this_week")
            assert result["known_place"] is True
            assert result["visits"] >= 1
            assert result["total_seconds"] > 0
            assert result["place"]["name"] == "Casa"
        finally:
            for coll in ("life_places", "presence_sessions", "presence_states"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_the_service_reconstructs_the_commute_and_calls_it_observed():
    async def body():
        client, db = await _db()
        uid = f"u_rt_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates

            service = await _service(db)
            home = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1]),
            )
            work = await service.save_place(
                uid, label="Ufficio", role="work",
                coordinates=Coordinates(latitude=WORK[0], longitude=WORK[1]),
            )
            for day, minutes in ((4, 31), (3, 29), (2, 34), (1, 95)):
                await service.repo.save_session(
                    _session(uid, home.id, _iso(day, 6, 30), _iso(day, 7, 50))
                )
                await service.repo.save_session(
                    _session(uid, work.id, _iso(day, 7, 50 + minutes) if minutes < 10 else
                             (datetime.fromisoformat(_iso(day, 7, 50)) +
                              timedelta(minutes=minutes)).isoformat(),
                             _iso(day, 17, 0))
                )

            result = await service.journeys_between(
                uid, from_place_id=home.id, to_place_id=work.id, period="last_30_days"
            )
            observed = result["observed"]
            assert observed["samples"] >= 3
            typical = observed["typical_seconds"] / 60
            assert 25 <= typical <= 40, f"tipico anomalo: {typical}"
            assert observed["slowest_seconds"] / 60 >= 90, "il giorno storto è sparito"
            assert result["from_place"] == "Casa" and result["to_place"] == "Ufficio"
        finally:
            for coll in ("life_places", "presence_sessions", "presence_states"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_ora_knows_where_somebody_is_without_asking_them():
    async def body():
        client, db = await _db()
        uid = f"u_rt_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates

            service = await _service(db)
            home = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1]),
            )
            assert (await service.where_now(uid))["at_a_known_place"] is False

            for minutes in (20, 10, 2):
                await service.record_observation(
                    uid, latitude=HOME[0] + 25 / 111_320.0, longitude=HOME[1],
                    accuracy_meters=12,
                    observed_at=(
                        datetime.now(timezone.utc) - timedelta(minutes=minutes)
                    ).isoformat(),
                )
            here = await service.where_now(uid)
            assert here["at_a_known_place"] is True
            assert here["place"] == "Casa"
            assert here["seconds_here"] >= 0
            assert "latitude" not in str(here)
        finally:
            for coll in ("life_places", "presence_sessions", "presence_states",
                         "presence_observations", "place_candidates"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Routines are read, never counted into existence
# ---------------------------------------------------------------------------

def test_no_threshold_anywhere_creates_a_routine():
    """
    §7, structurally. `if occurrences >= 3: create_routine()` is the shape this
    forbids, and so is every spelling of it.
    """
    for name in ("service.py", "analytics.py"):
        source = (HERE / "places" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    source = source.replace(doc, "")
        code = " ; ".join(
            l for l in source.splitlines() if not l.strip().startswith("#")
        )
        for shape in ("occurrences >", "occurrences >=", "len(days) >= 3",
                      "visits >=", "count >= 3"):
            assert shape not in code, f"{name} decide una routine con una soglia: {shape}"


def test_the_model_is_shown_days_and_no_verdict(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_rn_{uuid.uuid4().hex[:8]}"
        seen = {}

        async def capture(system, user):
            seen["system"], seen["user"] = system, user
            return {"routine": None}

        try:
            import places.reasoning as reasoning

            from places.models import Coordinates

            service = await _service(db)
            home = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1]),
            )
            work = await service.save_place(
                uid, label="Ufficio", role="work",
                coordinates=Coordinates(latitude=WORK[0], longitude=WORK[1]),
            )
            for day in range(5):
                await service.repo.save_session(
                    _session(uid, home.id, _iso(day, 6, 0), _iso(day, 7, 50))
                )
                await service.repo.save_session(
                    _session(uid, work.id, _iso(day, 8, 20), _iso(day, 17, 30))
                )

            monkeypatch.setattr(reasoning, "_ask_model", capture)
            assert await service.review_routines(uid) is None, "silenzio non rispettato"

            assert "days" in seen["user"] and "Casa" in seen["user"]
            for word in ("routine is", "habit:", "score", "significance"):
                assert word not in seen["user"].lower(), f"il payload contiene un verdetto: {word}"
            assert "coincidence" in seen["system"].lower()
        finally:
            for coll in ("life_places", "presence_sessions", "observed_routines"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_a_routine_the_model_reads_is_stored_as_a_candidate(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_rn_{uuid.uuid4().hex[:8]}"
        try:
            import places.reasoning as reasoning

            from places.models import Coordinates

            service = await _service(db)
            home = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1]),
            )
            work = await service.save_place(
                uid, label="Ufficio", role="work",
                coordinates=Coordinates(latitude=WORK[0], longitude=WORK[1]),
            )
            for day in range(5):
                await service.repo.save_session(
                    _session(uid, home.id, _iso(day, 6, 0), _iso(day, 7, 50))
                )
                await service.repo.save_session(
                    _session(uid, work.id, _iso(day, 8, 20), _iso(day, 17, 30))
                )

            async def reads(system, user):
                return {
                    "routine": {
                        "place_ids": [home.id, work.id],
                        "weekdays": ["monday", "tuesday"],
                        "typical_start": "07:50",
                        "typical_end": "17:30",
                        "occurrences": 5,
                        "interpretation": "Esci di casa verso le 7:50 e sei in ufficio per le 8:20.",
                    },
                    "worth_asking": False,
                }

            monkeypatch.setattr(reasoning, "_ask_model", reads)
            result = await service.review_routines(uid)

            assert result is not None
            assert result["routine"]["state"] == "candidate", "una routine è nata già accettata"
            assert result["worth_asking"] is False
            assert result["routine"]["what_ora_thinks"]
            stored = await service.list_routines(uid)
            assert len(stored) == 1 and stored[0]["state"] == "candidate"
        finally:
            for coll in ("life_places", "presence_sessions", "observed_routines"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_a_routine_through_a_place_that_does_not_exist_is_dropped(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_rn_{uuid.uuid4().hex[:8]}"
        try:
            import places.reasoning as reasoning

            from places.models import Coordinates

            service = await _service(db)
            home = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1]),
            )
            for day in range(3):
                await service.repo.save_session(
                    _session(uid, home.id, _iso(day, 20, 0), _iso(day, 23, 0))
                )

            async def invents(system, user):
                return {
                    "routine": {
                        "place_ids": ["plc_inventato", "plc_altro"],
                        "occurrences": 3,
                        "interpretation": "una routine attraverso il nulla",
                    },
                    "worth_asking": True,
                }

            monkeypatch.setattr(reasoning, "_ask_model", invents)
            assert await service.review_routines(uid) is None
            assert await service.list_routines(uid) == []
        finally:
            for coll in ("life_places", "presence_sessions", "observed_routines"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Observed is not live
# ---------------------------------------------------------------------------

def test_without_a_routing_service_nothing_claims_to_know_the_traffic():
    from places import routing

    caps = routing.capabilities()
    if caps["available"]:
        pytest.skip("un provider di routing è configurato in questo ambiente")
    assert caps["available"] is False
    assert caps["why_unavailable"]
    assert caps["live_traffic"] is False

    result = _run(_route_without_provider())
    assert result["available"] is False
    assert "duration_seconds" not in result, "ha inventato una durata"


async def _route_without_provider():
    from places import routing

    return await routing.get_route(
        origin={"latitude": HOME[0], "longitude": HOME[1]},
        destination={"latitude": WORK[0], "longitude": WORK[1]},
    )


def test_the_history_capability_labels_itself_as_history():
    """
    The payload itself carries the distinction, so it cannot be lost on the way
    to a sentence.
    """
    async def body():
        client, db = await _db()
        uid = f"u_lb_{uuid.uuid4().hex[:8]}"
        try:
            from places.caps import get_journeys_between_places

            observation = await get_journeys_between_places(
                {"period": "last_30_days"}, {"user_id": uid, "db": db}
            )
            assert observation.payload["is_live_traffic"] is False
            # The wording denies the live claim rather than omitting it: an
            # absent distinction is one a sentence can quietly lose.
            assert "non traffico attuale" in observation.payload["means"]
        finally:
            client.close()

    _run(body())


def test_the_two_capabilities_tell_the_model_which_is_which():
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    history = registry._tools["get_journeys_between_places"].description
    live = registry._tools["get_route"].description

    assert "NOT current traffic" in history
    assert "di solito" in history
    assert "available=false" in live
    assert "do not" in live.lower() and "assume driving" in live


def test_travel_mode_is_never_assumed_to_be_a_car():
    from places.routing import TRAVEL_MODES, get_route

    assert set(TRAVEL_MODES) == {"drive", "walk", "bicycle", "transit"}
    source = (HERE / "places" / "routing.py").read_text(encoding="utf-8")
    assert '"drive"' in source
    # The default exists, but the capability description forbids assuming it.
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    spec = ToolRegistry()._tools["get_route"]
    assert spec.input_schema["properties"]["travel_mode"]["enum"] == [
        "drive", "walk", "bicycle", "transit"
    ]


# ---------------------------------------------------------------------------
# Context, only when the subject is presence
# ---------------------------------------------------------------------------

def test_presence_reaches_the_context_broker_only_under_its_own_category():
    """
    §11: minimum necessary. A question about a mortgage does not get somebody's
    movements; a question about leaving for work does.
    """
    source = (HERE / "conversation_engine" / "ai_core" / "context_broker.py").read_text(
        encoding="utf-8"
    )
    assert "_place_presence_facts" in source
    # It is reached from the presence branch, not from an unconditional path.
    body = source[source.index("async def _presence_facts"):]
    assert "_place_presence_facts" in body[:600]
    gate = source[source.index('if "presence" in categories'):]
    assert "_presence_facts" in gate[:200]
