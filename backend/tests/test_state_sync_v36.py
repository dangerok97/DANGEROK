"""
V3.6 close-out — three bugs somebody actually hit, and the line they revealed.

    LOCATION OBSERVATION != PRESENCE FACT
    EXPLICIT USER STATEMENT IS A LIFE FACT

Somebody created a place, said "sono qui adesso", opened it, and was told "non
sei qui". That is ORA arguing with a person about their own life. Dwell exists
because a sensor reading is a guess that needs corroborating; a statement is
not a guess, and making somebody wait three minutes to be believed treats it
as one.

The other two were the same bug wearing two hats: Vita and the place detail
each fetched into their own state, so a mutation on one surface could not
reach the other. A created place did not appear and a deleted one did not
leave until somebody reloaded the browser.
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
FRONTEND = HERE.parent / "frontend"

HOME = (45.4064, 11.8768)
OFFICE = (45.4180, 11.8900)


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _service(db):
    from places.service import PlacesService

    return PlacesService(db)


def _coords(lat, lon):
    from places.models import Coordinates

    return Coordinates(latitude=lat, longitude=lon)


async def _clean(db, uid):
    for coll in (
        "life_places", "presence_sessions", "presence_states",
        "presence_observations", "place_candidates", "observed_routines",
    ):
        await db[coll].delete_many({"user_id": uid})


# ---------------------------------------------------------------------------
# BUG B — being believed
# ---------------------------------------------------------------------------

def test_saying_you_are_here_makes_you_here_immediately():
    """
    No dwell, because there is nothing to corroborate. The person is the
    source, and they are a better one than the radio.
    """
    async def body():
        client, db = await _db()
        uid = f"u_uc_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(
                uid,
                label="Casa",
                role="home",
                coordinates=_coords(*HOME),
                source="current_position",
                currently_here=True,
            )

            summary = (await service.presence_summary(uid))[place.id]
            assert summary["present"] is True, "ORA sta contraddicendo la persona"
            assert summary["status"] == "present"
            assert summary["since"]

            sessions = await service.repo.sessions_for(uid, place_id=place.id)
            assert len(sessions) == 1
            assert sessions[0].exited_at is None
            assert sessions[0].source == "user_confirmation", (
                "la provenienza non distingue una dichiarazione da un sensore"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_creating_a_place_without_saying_so_does_not_claim_presence():
    """The other half: silence is not a statement."""
    async def body():
        client, db = await _db()
        uid = f"u_uc_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(
                uid, label="Ufficio", role="work", coordinates=_coords(*OFFICE)
            )
            summary = (await service.presence_summary(uid))[place.id]
            assert summary["present"] is False
            assert await service.repo.sessions_for(uid, place_id=place.id) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_confirming_twice_does_not_open_a_second_stay():
    async def body():
        client, db = await _db()
        uid = f"u_uc_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=_coords(*HOME), currently_here=True,
            )
            first = await service.repo.open_session(uid, place.id)
            for _ in range(3):
                await service.confirm_current_presence(uid, place.id)

            sessions = await service.repo.sessions_for(uid, place_id=place.id)
            assert len(sessions) == 1
            assert sessions[0].id == first.id, "la conferma ha ricreato la sessione"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_gps_arriving_after_a_confirmation_extends_the_same_stay():
    """
    §4. The two doors converge. A fix that agrees with what somebody said must
    not open a second stay beside the one they opened by saying it.
    """
    async def body():
        client, db = await _db()
        uid = f"u_uc_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=_coords(*HOME), currently_here=True,
            )
            opened = await service.repo.open_session(uid, place.id)

            now = datetime.now(timezone.utc)
            for minutes in (4, 8, 12):
                await service.record_observation(
                    uid,
                    latitude=HOME[0] + 20 / 111_320.0,
                    longitude=HOME[1],
                    accuracy_meters=15,
                    observed_at=(now + timedelta(minutes=minutes)).isoformat(),
                )

            sessions = await service.repo.sessions_for(uid, place_id=place.id)
            assert len(sessions) == 1, "il GPS ha duplicato una presenza dichiarata"
            assert sessions[0].id == opened.id
            assert sessions[0].observation_count > 1
            assert (await service.presence_summary(uid))[place.id]["present"] is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_being_here_means_not_being_somewhere_else():
    """Two places both saying "sei qui" is a contradiction, not two facts."""
    async def body():
        client, db = await _db()
        uid = f"u_uc_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            home = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=_coords(*HOME), currently_here=True,
            )
            office = await service.save_place(
                uid, label="Ufficio", role="work",
                coordinates=_coords(*OFFICE), currently_here=True,
            )

            summary = await service.presence_summary(uid)
            here = [pid for pid, info in summary.items() if info["present"]]
            assert here == [office.id], f"presente in {len(here)} luoghi"

            closed = await service.repo.sessions_for(uid, place_id=home.id)
            assert closed and closed[0].exited_at is not None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_dwell_is_untouched_for_anything_the_sensors_said():
    """
    §3. The narrow door must not have widened the other one. A single GPS fix
    inside a zone is still not presence.
    """
    async def body():
        client, db = await _db()
        uid = f"u_uc_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(
                uid, label="Casa", role="home", coordinates=_coords(*HOME)
            )
            await service.record_observation(
                uid, latitude=HOME[0], longitude=HOME[1], accuracy_meters=15
            )
            summary = (await service.presence_summary(uid))[place.id]
            assert summary["present"] is False, "una sola lettura è diventata presenza"
            assert summary["status"] == "pending_enter"
            assert await service.repo.sessions_for(uid, place_id=place.id) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_statement_about_a_place_with_no_position_changes_nothing():
    async def body():
        client, db = await _db()
        uid = f"u_uc_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(uid, label="Da definire", currently_here=True)
            assert await service.confirm_current_presence(uid, place.id) is None
            assert await service.repo.sessions_for(uid, place_id=place.id) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# BUG C — a deleted place is gone everywhere
# ---------------------------------------------------------------------------

def test_deleting_the_place_you_are_in_leaves_no_open_stay():
    async def body():
        client, db = await _db()
        uid = f"u_del_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=_coords(*HOME), currently_here=True,
            )
            assert (await service.presence_summary(uid))[place.id]["present"] is True

            assert await service.remove_place(uid, place.id) is True

            assert [p.label for p in await service.list_places(uid)] == []
            assert await service.repo.sessions_for(uid, place_id=place.id) == []
            assert (await service.where_now(uid))["at_a_known_place"] is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_deleted_place_is_not_offered_as_a_destination():
    async def body():
        client, db = await _db()
        uid = f"u_del_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(
                uid, label="Ufficio", role="work", coordinates=_coords(*OFFICE)
            )
            await service.remove_place(uid, place.id)
            assert (await service.resolve_destination(uid, "Ufficio")).resolved is False
            assert (await service.resolve_destination(uid, "lavoro")).resolved is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# BUGS A and C — one strategy, not three patches
# ---------------------------------------------------------------------------

def _read(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def test_every_place_mutation_invalidates_rather_than_hoping():
    section = _read("src/components/vita/PlacesSection.tsx")
    detail = _read("app/place/[placeId].tsx")

    for surface, source in (("PlacesSection", section), ("detail", detail)):
        assert "invalidatePlace" in source, f"{surface} non invalida nulla"
        assert "useRevalidate" in source, f"{surface} non ascolta le invalidazioni"

    # Delete invalidates before navigating: the other order shows the old list
    # for a frame, which reads as a place briefly coming back.
    remove = detail[detail.index("await api.placesRemove"):]
    assert remove.index("invalidatePlace") < remove.index("router.back")


def test_nothing_was_fixed_by_reloading_the_page():
    """
    §1. `window.location.reload()` and friends are how a state bug is hidden
    rather than removed, and they throw away everything else on the screen.
    """
    for relative in (
        "src/components/vita/PlacesSection.tsx",
        "app/place/[placeId].tsx",
        "src/lib/revalidate.ts",
    ):
        source = _read(relative)
        for patch in ("location.reload", "router.refresh", "setTimeout("):
            assert patch not in source, f"{relative} usa una toppa: {patch}"


def test_the_surfaces_reload_when_they_come_back_into_view():
    """
    Vita stays mounted underneath the detail route, so returning from it
    remounts nothing. Without this, the list shows whatever it had when it was
    born.
    """
    for relative in ("src/components/vita/PlacesSection.tsx", "app/place/[placeId].tsx"):
        assert "useFocusEffect" in _read(relative), f"{relative} non rivalida al focus"


def test_invalidation_holds_no_data():
    """
    §5/§8. It is a staleness signal, not a second store: a cache of places
    beside the server would be a second thing to keep honest.
    """
    source = _read("src/lib/revalidate.ts")
    for storeish in ("api.", "fetch(", "placesList", "useState<Places"):
        assert storeish not in source, f"revalidate.ts sta diventando uno store: {storeish}"
    assert "invalidate" in source and "useRevalidate" in source


def test_one_strategy_and_not_three():
    """A single module names the affected resources, so a new surface is
    added once instead of remembered at every call site."""
    source = _read("src/lib/revalidate.ts")
    assert "places:list" in source and "presence:current" in source
    assert "export function invalidatePlace" in source


# ---------------------------------------------------------------------------
# The duration nobody has ever lived
# ---------------------------------------------------------------------------

def test_there_is_one_duration_formatter_and_it_cannot_print_sixty_minutes():
    source = _read("src/utils/duration.ts")
    # Minutes are rounded once and the hours come from that, so there is no
    # arithmetic path left on which the remainder can reach sixty.
    assert "Math.round(seconds / 60)" in source
    assert "Math.round((seconds % 3600)" not in source

    cases = {
        59 * 60: "59m",
        60 * 60: "1h",
        61 * 60: "1h 1m",
        (3 * 3600) + 59 * 60: "3h 59m",
        # The reported bug: 3h 59m 30s used to print "3h 60m".
        (3 * 3600) + 59 * 60 + 30: "4h",
        4 * 3600: "4h",
        30: None,
    }
    for seconds, expected in cases.items():
        got = _format(seconds)
        assert got == expected, f"{seconds}s -> {got!r}, atteso {expected!r}"


def _format(seconds):
    """The TypeScript rule, restated, so the table above is checked and not read."""
    if seconds is None:
        return None
    total = round(seconds / 60)
    if total < 1:
        return None
    hours, minutes = divmod(total, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def test_no_surface_formats_a_duration_on_its_own():
    for relative in ("src/components/vita/PlacesSection.tsx", "app/place/[placeId].tsx"):
        source = _read(relative)
        assert "formatDuration" in source, f"{relative} non usa la funzione condivisa"
        assert "% 3600" not in source, f"{relative} calcola ancora i minuti da sé"
