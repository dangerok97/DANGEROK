"""
V3.6 Sprint 2 — being somewhere, as opposed to being measured near it.

    A PLACE IS A ZONE, NOT A POINT.
    ENTER/EXIT USE HYSTERESIS + DWELL.

The failure this exists to prevent is a life history in which somebody entered
and left their own home eleven times while asleep. A GPS fix is a claim with a
radius of doubt attached, and a stationary phone's claim wanders; one threshold
for both directions turns that wander into events.

Everything asserted here is geometry and time. Whether twelve seconds inside a
circle counts has a right answer, and code owns it. What a presence *means* is
somebody else's job entirely, and a test at the end checks that this file's
subject never wandered into that one's.
"""

from __future__ import annotations

import ast
import asyncio
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


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _service(db):
    from places.service import PlacesService

    return PlacesService(db)


def _at(minutes: float) -> str:
    """A timestamp `minutes` after a fixed start, so dwell is exercised for real."""
    base = datetime(2026, 8, 30, 18, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(minutes=minutes)).isoformat()


def _north(metres: float):
    """A point `metres` due north of home. One degree of latitude ≈ 111_320 m."""
    return (HOME[0] + metres / 111_320.0, HOME[1])


def _observation(user_id: str, metres: float, minutes: float, accuracy: float = 15.0):
    from places.models import Coordinates, PresenceObservation

    lat, lon = _north(metres)
    return PresenceObservation(
        user_id=user_id,
        coordinates=Coordinates(latitude=lat, longitude=lon, accuracy_meters=accuracy),
        observed_at=_at(minutes),
    )


def _zone(entry: float = 90.0, exit_: float = 140.0):
    from places.models import Coordinates, PresenceZone

    return PresenceZone(
        center=Coordinates(latitude=HOME[0], longitude=HOME[1]),
        entry_radius_m=entry,
        exit_radius_m=exit_,
    )


def _hit_for(observation, zone, place_id="plc_home"):
    from places import presence

    from places.models import LifePlace

    place = LifePlace(user_id=observation.user_id, id=place_id, label="Casa", zone=zone,
                      coordinates=zone.center)
    return next(iter(presence.hits(observation.coordinates, [place])), None)


# ---------------------------------------------------------------------------
# A place is a zone
# ---------------------------------------------------------------------------

def test_leaving_is_measured_against_a_wider_circle_than_arriving():
    """
    The contract, refused at construction rather than discovered in a log.
    Equal radii are the bug, so equal radii are not representable.
    """
    from pydantic import ValidationError

    from places.models import Coordinates, PresenceZone

    centre = Coordinates(latitude=HOME[0], longitude=HOME[1])
    ok = PresenceZone(center=centre, entry_radius_m=90, exit_radius_m=140)
    assert ok.exit_radius_m > ok.entry_radius_m

    for entry, leave in ((90, 90), (140, 90), (100, 99)):
        with pytest.raises(ValidationError):
            PresenceZone(center=centre, entry_radius_m=entry, exit_radius_m=leave)


def test_a_place_without_its_own_size_still_has_one():
    from places.models import Coordinates, LifePlace, PresenceZone
    from places.presence import zone_of

    place = LifePlace(
        user_id="u",
        label="Casa",
        coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1]),
    )
    zone = zone_of(place)
    assert isinstance(zone, PresenceZone)
    assert zone.exit_radius_m > zone.entry_radius_m

    # And a place nobody located is not a zone at all.
    assert zone_of(LifePlace(user_id="u", label="Da definire")) is None


def test_the_zone_size_is_a_property_of_the_place_not_of_its_kind():
    """
    Structural. A rule that made homes 90 metres *because they are homes*
    would be a domain detector holding a tape measure.
    """
    source = (HERE / "places" / "presence.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                source = source.replace(doc, "")
    code = "\n".join(l for l in source.splitlines() if not l.strip().startswith("#"))
    for word in ("home", "work", "gym", "palestra", "casa", "ufficio", "role"):
        assert word not in code.lower(), f"la geometria conosce un ruolo: {word}"


# ---------------------------------------------------------------------------
# One reading is not arrival
# ---------------------------------------------------------------------------

def test_a_single_fix_inside_the_zone_is_not_presence():
    from places import presence
    from places.models import PresenceState

    zone = _zone()
    state = PresenceState(user_id="u", place_id="plc_home")
    observation = _observation("u", 20, 0)

    state, change = presence.advance(state, observation, _hit_for(observation, zone))
    assert change is None, "una sola lettura ha creato una presenza"
    assert state.status == "pending_enter"
    assert presence.describe(state)["present"] is False


def test_presence_needs_time_and_a_second_reading():
    from places import presence
    from places.models import PresenceState

    zone = _zone()
    state = PresenceState(user_id="u", place_id="plc_home")

    first = _observation("u", 20, 0)
    state, change = presence.advance(state, first, _hit_for(first, zone))
    assert change is None

    # Still inside, but too soon.
    soon = _observation("u", 25, 1)
    state, change = presence.advance(state, soon, _hit_for(soon, zone))
    assert change is None and state.status == "pending_enter"

    # Past the dwell.
    later = _observation("u", 22, 4)
    state, change = presence.advance(state, later, _hit_for(later, zone))
    assert change == "entered"
    assert state.status == "present"
    assert state.since == first.observed_at, "la presenza non parte dal primo fix"


def test_driving_past_the_end_of_the_street_leaves_nothing_behind():
    """§9: a fix that enters and leaves within seconds is a pass, not a visit."""
    from places import presence
    from places.models import PresenceState

    zone = _zone()
    state = PresenceState(user_id="u", place_id="plc_home")

    inside = _observation("u", 40, 0)
    state, change = presence.advance(state, inside, _hit_for(inside, zone))
    assert state.status == "pending_enter" and change is None

    gone = _observation("u", 400, 0.5)
    state, change = presence.advance(state, gone, _hit_for(gone, zone))
    assert change is None, "un passaggio ha prodotto un ingresso"
    assert state.status == "outside"
    assert state.since is None


def test_leaving_also_takes_time():
    from places import presence
    from places.models import PresenceState

    zone = _zone()
    state = PresenceState(
        user_id="u", place_id="plc_home", status="present", since=_at(0)
    )

    away = _observation("u", 300, 10)
    state, change = presence.advance(state, away, _hit_for(away, zone))
    assert change is None and state.status == "pending_exit"

    still_away = _observation("u", 320, 12)
    state, change = presence.advance(state, still_away, _hit_for(still_away, zone))
    assert change is None, "uscita dichiarata prima del dwell"

    gone = _observation("u", 350, 16)
    state, change = presence.advance(state, gone, _hit_for(gone, zone))
    assert change == "exited" and state.status == "outside"


# ---------------------------------------------------------------------------
# Jitter — the test this sprint exists for
# ---------------------------------------------------------------------------

def test_a_phone_sitting_still_does_not_come_and_go():
    """
    QA B as a property. Readings drifting across the entry radius — 95, 105,
    98, 110 metres — while the person has not moved. With one threshold this
    is a night of arrivals and departures; with hysteresis it is one stay.
    """
    from places import presence
    from places.models import PresenceState

    zone = _zone(entry=100.0, exit_=150.0)
    state = PresenceState(user_id="u", place_id="plc_home")

    # Settle inside first.
    for minute, metres in ((0, 60), (4, 65)):
        o = _observation("u", metres, minute)
        state, change = presence.advance(state, o, _hit_for(o, zone))
    assert state.status == "present"

    changes = []
    for i, metres in enumerate([95, 105, 98, 110, 96, 108, 99, 112, 97, 104]):
        o = _observation("u", metres, 10 + i * 2)
        state, change = presence.advance(state, o, _hit_for(o, zone))
        if change:
            changes.append((metres, change))

    assert changes == [], f"il rumore ha prodotto transizioni: {changes}"
    assert state.status == "present", "la persona è stata dichiarata fuori dal rumore"


def test_going_out_for_real_still_registers():
    """The other half: hysteresis must not become deafness."""
    from places import presence
    from places.models import PresenceState

    zone = _zone(entry=100.0, exit_=150.0)
    state = PresenceState(
        user_id="u", place_id="plc_home", status="present", since=_at(0)
    )

    changes = []
    for i, metres in enumerate([95, 105, 98, 110]):
        o = _observation("u", metres, 10 + i * 2)
        state, change = presence.advance(state, o, _hit_for(o, zone))
        if change:
            changes.append(change)
    assert changes == []

    # Now actually beyond the exit radius, and staying there.
    for i, metres in enumerate([400, 900, 1500]):
        o = _observation("u", metres, 30 + i * 6)
        state, change = presence.advance(state, o, _hit_for(o, zone))
        if change:
            changes.append(change)

    assert changes == ["exited"]
    assert state.status == "outside"


def test_a_reading_too_vague_for_the_zone_decides_nothing():
    """
    §4. A fix accurate to 200 metres says plenty about a campus and nothing
    about a courtyard, so it is compared with the zone it is used against
    rather than against one global number.
    """
    from places import presence
    from places.models import PresenceState

    zone = _zone(entry=90.0, exit_=140.0)
    state = PresenceState(user_id="u", place_id="plc_home")

    vague = _observation("u", 20, 0, accuracy=200.0)
    state, change = presence.advance(state, vague, _hit_for(vague, zone))
    assert change is None
    assert state.status == "outside", "una lettura imprecisa ha avviato un ingresso"
    assert state.ignored_fixes == 1

    # The same reading against a place big enough for it is usable.
    big = _zone(entry=400.0, exit_=600.0)
    state2 = PresenceState(user_id="u", place_id="plc_campus")
    state2, _ = presence.advance(state2, vague, _hit_for(vague, big, "plc_campus"))
    assert state2.status == "pending_enter"


def test_a_vague_reading_does_not_cancel_a_pending_departure():
    """It is not evidence either way, so it must not act as evidence against."""
    from places import presence
    from places.models import PresenceState

    zone = _zone()
    state = PresenceState(
        user_id="u", place_id="plc_home", status="pending_exit",
        pending_since=_at(10), pending_samples=1,
    )
    vague = _observation("u", 20, 12, accuracy=300.0)
    state, change = presence.advance(state, vague, _hit_for(vague, zone))
    assert state.status == "pending_exit", "una lettura inutilizzabile ha annullato l'uscita"
    assert change is None


# ---------------------------------------------------------------------------
# Sessions, end to end
# ---------------------------------------------------------------------------

def test_one_stay_survives_ten_fixes_and_closes_once():
    """§8: idempotency, in the shape it actually takes."""
    async def body():
        client, db = await _db()
        uid = f"u_ps_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates

            service = await _service(db)
            home = await service.save_place(
                uid,
                label="Casa",
                role="home",
                coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1]),
            )

            async def observe(metres, minutes):
                lat, lon = _north(metres)
                return await service.record_observation(
                    uid, latitude=lat, longitude=lon, accuracy_meters=15,
                    observed_at=_at(minutes),
                )

            # Arrive, then keep being there.
            for i in range(10):
                await observe(30, i * 4)

            open_sessions = [
                s for s in await service.repo.sessions_for(uid, place_id=home.id)
                if s.exited_at is None
            ]
            assert len(open_sessions) == 1, f"{len(open_sessions)} sessioni aperte"
            assert open_sessions[0].observation_count > 1

            # Leave, then keep being away.
            for i in range(6):
                await observe(600, 60 + i * 8)

            sessions = await service.repo.sessions_for(uid, place_id=home.id)
            assert len(sessions) == 1, "l'uscita ha creato una seconda sessione"
            assert sessions[0].exited_at is not None
            assert sessions[0].duration_seconds() > 0
        finally:
            for coll in ("life_places", "presence_observations", "presence_sessions",
                         "presence_states", "place_candidates"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_the_summary_says_here_or_not_and_never_a_coordinate():
    async def body():
        client, db = await _db()
        uid = f"u_ps_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates

            service = await _service(db)
            home = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1]),
            )
            for minutes in (0, 5, 10):
                lat, lon = _north(30)
                await service.record_observation(
                    uid, latitude=lat, longitude=lon, accuracy_meters=15,
                    observed_at=_at(minutes),
                )

            summary = (await service.presence_summary(uid))[home.id]
            assert summary["present"] is True
            assert summary["since"]
            assert summary["current_session_seconds"] >= 0
            blob = str(summary)
            assert "45.40" not in blob and "11.87" not in blob, "coordinate nel riepilogo"
        finally:
            for coll in ("life_places", "presence_observations", "presence_sessions",
                         "presence_states"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_time_in_a_window_is_a_primitive_not_a_dashboard():
    async def body():
        client, db = await _db()
        uid = f"u_ps_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates, PresenceSession

            service = await _service(db)
            home = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1]),
            )
            await service.repo.save_session(
                PresenceSession(
                    user_id=uid, place_id=home.id,
                    entered_at=_at(0), exited_at=_at(120),
                )
            )
            total = await service.time_at_place(
                uid, home.id, since=_at(-60), until=_at(600)
            )
            assert total["sessions"] == 1
            assert total["total_seconds"] == 120 * 60
        finally:
            for coll in ("life_places", "presence_sessions", "presence_states"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Two places, one street
# ---------------------------------------------------------------------------

def test_two_overlapping_places_produce_ambiguity_rather_than_a_guess():
    """
    §10. A bar next door to an office is not a modelling error, it is a street.
    Picking the nearer centre by nine metres would be a fragile rule wearing
    the clothes of a fact.
    """
    async def body():
        client, db = await _db()
        uid = f"u_ov_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates

            service = await _service(db)
            lat_a, lon_a = HOME
            lat_b, lon_b = _north(40)
            await service.save_place(
                uid, label="Ufficio", role="work",
                coordinates=Coordinates(latitude=lat_a, longitude=lon_a),
            )
            await service.save_place(
                uid, label="Bar accanto",
                coordinates=Coordinates(latitude=lat_b, longitude=lon_b),
            )

            lat, lon = _north(20)
            result = await service.record_observation(
                uid, latitude=lat, longitude=lon, accuracy_meters=10,
                observed_at=_at(0),
            )
            assert "ambiguous_between" in result
            assert len(result["ambiguous_between"]) == 2
            assert "at_known_place" not in result

            # And no stay is opened for either, however long it goes on.
            for minutes in (5, 10, 15):
                await service.record_observation(
                    uid, latitude=lat, longitude=lon, accuracy_meters=10,
                    observed_at=_at(minutes),
                )
            assert await service.repo.sessions_for(uid) == []
        finally:
            for coll in ("life_places", "presence_observations", "presence_sessions",
                         "presence_states", "place_candidates"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Candidates, and the person's last word
# ---------------------------------------------------------------------------

def test_a_candidate_remembers_how_spread_out_it_is():
    """§11: the observed size, which is what a zone would be built from."""
    async def body():
        client, db = await _db()
        uid = f"u_cd_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            for i, metres in enumerate((0, 30, 55, 20)):
                lat, lon = _north(metres)
                await service.record_observation(
                    uid, latitude=lat, longitude=lon, accuracy_meters=10,
                    observed_at=_at(i * 10),
                )
            candidate = (await service.repo.list_candidates(uid))[0]
            assert candidate.observation_count == 4
            assert candidate.spread_m > 0, "il candidato non ricorda la sua estensione"
            assert candidate.became_place_id is None
        finally:
            for coll in ("presence_observations", "place_candidates"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_never_ask_me_again_survives_forgetting_everything(monkeypatch):
    """
    §13. "Non chiedermelo più" is an instruction, not a datum. Erasing it with
    the observations would mean asking again next week — which is the one
    outcome the person explicitly ruled out.
    """
    async def body():
        client, db = await _db()
        uid = f"u_sp_{uuid.uuid4().hex[:8]}"
        try:
            import places.reasoning as reasoning

            service = await _service(db)
            lat, lon = _north(0)
            await service.record_observation(
                uid, latitude=lat, longitude=lon, accuracy_meters=10, observed_at=_at(0)
            )
            candidate = (await service.repo.list_candidates(uid))[0]

            async def says_mute(system, user):
                return {"decision": "mute", "label": "", "role": "other"}

            monkeypatch.setattr(reasoning, "_ask_model", says_mute)
            result = await service.answer_candidate(uid, candidate.id, "non chiedermelo più")
            assert result["outcome"] == "suppressed"

            await service.forget_observations(uid)
            survivors = await service.repo.list_candidates(uid)
            assert [c.outcome for c in survivors] == ["suppressed"], (
                "l'istruzione di non chiedere più è stata cancellata"
            )
        finally:
            for coll in ("presence_observations", "place_candidates", "life_places"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------

def test_a_person_can_forget_where_they_have_been_and_keep_the_place():
    async def body():
        client, db = await _db()
        uid = f"u_pv_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates

            service = await _service(db)
            home = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1]),
            )
            for minutes in (0, 5, 10):
                lat, lon = _north(30)
                await service.record_observation(
                    uid, latitude=lat, longitude=lon, accuracy_meters=15,
                    observed_at=_at(minutes),
                )
            assert await service.repo.sessions_for(uid, place_id=home.id)

            erased = await service.forget_presence(uid, place_id=home.id)
            assert erased["sessions_deleted"] >= 1
            assert erased["states_deleted"] >= 1
            assert await service.repo.sessions_for(uid, place_id=home.id) == []
            # The place itself is theirs and stays.
            assert [p.label for p in await service.list_places(uid)] == ["Casa"]
            # And presence starts again from nothing, not from "still present".
            assert (await service.presence_summary(uid))[home.id]["present"] is False
        finally:
            for coll in ("life_places", "presence_observations", "presence_sessions",
                         "presence_states"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_removing_a_place_removes_having_been_there():
    async def body():
        client, db = await _db()
        uid = f"u_pv_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates

            service = await _service(db)
            home = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1]),
            )
            for minutes in (0, 5, 10):
                lat, lon = _north(30)
                await service.record_observation(
                    uid, latitude=lat, longitude=lon, accuracy_meters=15,
                    observed_at=_at(minutes),
                )
            await service.remove_place(uid, home.id)
            assert await service.repo.sessions_for(uid, place_id=home.id) == []
        finally:
            for coll in ("life_places", "presence_observations", "presence_sessions",
                         "presence_states"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# The line between geometry and meaning
# ---------------------------------------------------------------------------

def test_the_state_machine_never_asks_the_model_anything():
    """
    §6. Whether twelve seconds of GPS is inside a circle has a right answer.
    A model call in this file would mean the answer had become negotiable.
    """
    source = (HERE / "places" / "presence.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    # Prose is allowed to name the thing it is drawing a line against; code is
    # not. Strip the explanations before looking for the calls.
    code = source
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                code = code.replace(doc, "")
    code = " ; ".join(
        l for l in code.splitlines() if not l.strip().startswith("#")
    )
    for forbidden in ("_ask_model", "llm", "get_manager", "reasoning", "await "):
        assert forbidden not in code, f"la geometria chiama il ragionamento: {forbidden}"
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)], (
        "presence.py è sincrono per costruzione: niente qui deve attendere nulla"
    )
