"""
V3.6 final — the native runtime, and the line it must not cross.

    OS EVENT != PRESENCE FACT.

A phone woken by a geofence knows one thing: it is somewhere near a circle it
was asked to watch. It does not know which place that is to the person, whether
arriving there matters, or whether anybody should be told. All of that stays on
the server, behind the same zones, hysteresis and dwell that Sprint 2 built —
the native region is a cheap way of getting woken up, not a verdict.

Most of what follows is structural, because the parts that only run on a device
cannot be executed here and pretending otherwise would be the exact dishonesty
this sprint is meant to avoid. What can be checked from here is checked: that
the background task decides nothing, that a duplicated delivery does not become
a second stay, and that no routing answer is invented when there is no service
to ask.
"""

from __future__ import annotations

import os
import re
import sys
import uuid
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


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _service(db):
    from places.service import PlacesService

    return PlacesService(db)


def _read(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def _code(relative: str) -> str:
    """
    The file with its explanations removed.

    Prose is allowed to name the thing it is drawing a line against — a
    docstring saying "no watchPositionAsync, ever" is the opposite of a
    violation — so the guards below read code and not comments.
    """
    source = _read(relative)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    kept = [l for l in source.splitlines() if not l.strip().startswith("//")]
    return " ; ".join(kept)


# ---------------------------------------------------------------------------
# One delivery, however many times it arrives
# ---------------------------------------------------------------------------

def test_the_same_native_event_delivered_twice_is_one_sighting():
    """
    §7. An OS can hand back the same callback, and a batch that failed halfway
    is retried whole. Ten deliveries of one arrival must stay one evening.
    """
    async def body():
        client, db = await _db()
        uid = f"u_nat_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            first = await service.record_observation(
                uid, latitude=HOME[0], longitude=HOME[1],
                accuracy_meters=20, event_id="evt_abc",
            )
            assert first["recorded"] is True

            for _ in range(4):
                again = await service.record_observation(
                    uid, latitude=HOME[0], longitude=HOME[1],
                    accuracy_meters=20, event_id="evt_abc",
                )
                assert again["recorded"] is False
                assert again["duplicate"] is True

            stored = await service.repo.recent_observations(uid)
            assert len([o for o in stored if o.event_id == "evt_abc"]) == 1
        finally:
            for coll in ("presence_observations", "place_candidates",
                         "presence_sessions", "presence_states"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_a_duplicate_never_reaches_the_state_machine():
    """
    The dedupe has to happen before anything moves. A repeated arrival that got
    as far as `advance()` would count as a second sample towards dwell, which
    is how a duplicated callback becomes an early "sei qui".
    """
    source = (HERE / "places" / "service.py").read_text(encoding="utf-8")
    body = source[source.index("async def record_observation"):]
    already = body.index("already_seen")
    advanced = body.index("_advance_presence")
    assert already < advanced, "il duplicato viene scartato dopo aver mosso lo stato"


def test_two_sightings_without_an_event_id_are_still_two_sightings():
    """Web fixes carry no id; absence of one must not collapse them."""
    async def body():
        client, db = await _db()
        uid = f"u_nat_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            for _ in range(2):
                result = await service.record_observation(
                    uid, latitude=HOME[0], longitude=HOME[1], accuracy_meters=20
                )
                assert result["recorded"] is True
            assert len(await service.repo.recent_observations(uid)) == 2
        finally:
            for coll in ("presence_observations", "place_candidates"):
                await db[coll].delete_many({"user_id": uid})
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# What the device is told about a place
# ---------------------------------------------------------------------------

def test_a_place_carries_a_region_to_watch_but_not_a_precise_position():
    async def body():
        client, db = await _db()
        uid = f"u_nat_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates

            service = await _service(db)
            place = await service.save_place(
                uid, label="Casa", role="home",
                coordinates=Coordinates(
                    latitude=45.406412345, longitude=11.876787654
                ),
            )
            public = place.public()
            zone = public["zone_center"]
            assert zone is not None
            # The wider circle: woken slightly early rather than slightly late.
            assert zone["exit_radius_m"] > 90
            # Coarse, not the pair that would point at a window.
            assert zone["latitude"] == round(45.406412345, 4)
            assert "exact" not in str(zone.get("precision"))
        finally:
            await db.life_places.delete_many({"user_id": uid})
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# The background task decides nothing
# ---------------------------------------------------------------------------

def test_the_background_task_records_and_interprets_nothing():
    """
    §4. The task may write down where the phone was. It may not decide which
    place that is, whether it matters, or whether to say anything.
    """
    source = _code("src/location/presenceTask.ts")
    for forbidden in (
        "home", "work", "casa", "lavoro", "palestra",
        "entry_radius", "dwell", "hysteresis",
        "Notification", "scheduleNotification", "alert(",
    ):
        assert forbidden not in source, f"il task nativo decide qualcosa: {forbidden}"

    # It writes to the buffer and does nothing else with the data.
    assert "remember(" in source
    assert "defineTask" in source


def test_the_task_is_defined_at_module_scope():
    """
    A phone woken by a region loads the bundle and looks for a task by name. A
    definition inside a component would not exist yet, and the wake-up would be
    wasted.
    """
    source = _read("src/location/presenceTask.ts")
    for line in source.splitlines():
        if "defineTask" in line and not line.strip().startswith("*"):
            assert not line.startswith(" "), (
                "defineTask è annidato: il runtime non lo troverebbe al risveglio"
            )

    layout = _read("app/_layout.tsx")
    assert "presenceTask" in layout, "il task non viene mai importato"
    assert "Platform.OS === 'ios'" in layout, "il bundle web tirerebbe dentro il nativo"


def test_a_geofence_crossing_is_stored_as_an_observation_not_as_an_arrival():
    source = _code("src/location/presenceTask.ts")
    assert "geofence_enter" in source and "geofence_exit" in source
    # It records the crossing; it does not open or close anything.
    for forbidden in ("session", "present", "entered", "exited"):
        assert f"{forbidden}(" not in source, f"il task crea presenza: {forbidden}"


# ---------------------------------------------------------------------------
# Battery
# ---------------------------------------------------------------------------

def test_nothing_asks_for_continuous_high_accuracy_gps():
    """
    §5. `watchPositionAsync` at Highest is what empties a battery in an
    afternoon, and a hundred-metre zone does not need a three-metre fix.
    """
    runtime = _code("src/location/presenceRuntime.ts")
    assert "watchPositionAsync" not in runtime
    assert "Accuracy.Highest" not in runtime and "Accuracy.BestForNavigation" not in runtime
    assert "Accuracy.Balanced" in runtime

    # And the updates are bounded in both distance and time.
    assert re.search(r"distanceInterval:\s*\w+", runtime)
    assert re.search(r"timeInterval:\s*\w+", runtime)
    assert "pausesUpdatesAutomatically: true" in runtime


# ---------------------------------------------------------------------------
# Permission, in two steps
# ---------------------------------------------------------------------------

def test_background_is_asked_second_and_never_at_first_run():
    runtime = _read("src/location/presenceRuntime.ts")
    background = runtime[runtime.index("export async function askBackground"):]
    background = background[: background.index("export async function isEnabled")]
    # It refuses to ask for "always" before "while using" exists.
    assert "getForegroundPermissionsAsync" in background
    assert "requestBackgroundPermissionsAsync" in background
    assert background.index("Foreground") < background.index("requestBackgroundPermissionsAsync")

    # And nothing in the first-run path reaches for it.
    for screen in ("app/life-setup", "app/(tabs)/index.tsx"):
        path = FRONTEND / screen
        files = list(path.rglob("*.tsx")) if path.is_dir() else ([path] if path.exists() else [])
        for f in files:
            assert "askBackground" not in f.read_text(encoding="utf-8"), (
                f"{f.name} chiede il background al primo avvio"
            )


def test_saying_no_leaves_ora_working():
    runtime = _read("src/location/presenceRuntime.ts")
    assert "Tutto il resto continua a" in runtime or "continua a funzionare" in runtime
    permessi = _read("app/account/permessi.tsx")
    assert "ORA continua a funzionare" in permessi


def test_the_web_says_it_cannot_do_this_rather_than_pretending():
    runtime = _read("src/location/presenceRuntime.ts")
    support = runtime[runtime.index("export function support"):]
    support = support[: support.index("export async function permissions")]
    assert "supported: false" in support
    assert "browser" in support.lower()


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------

def test_turning_it_off_stops_watching_without_deleting_anything():
    """
    §9. Off means the phone stops looking. What ORA already knows is the
    person's to keep or erase, separately and on purpose.
    """
    runtime = _read("src/location/presenceRuntime.ts")
    disable = runtime[runtime.index("export async function disable"):]
    disable = disable[: disable.index("export async function syncRegions")]

    assert "stopLocationUpdatesAsync" in disable
    assert "stopGeofencingAsync" in disable
    for destructive in ("placesRemove", "ForgetHistory", "delete", "clear("):
        assert destructive not in disable, f"disattivare cancella qualcosa: {destructive}"


def test_logging_out_leaves_no_phone_watching():
    auth = _read("src/contexts/AuthContext.tsx")
    assert "presenceRuntime" in auth and "shutdown" in auth


def test_regions_are_resynced_when_the_places_change():
    section = _read("src/components/vita/PlacesSection.tsx")
    assert "syncRegions" in section
    layout = _read("app/_layout.tsx")
    assert "syncRegions" in layout and "reconcile" in layout


# ---------------------------------------------------------------------------
# Routing: configured or honest
# ---------------------------------------------------------------------------

def test_with_no_provider_configured_nothing_resembles_a_live_eta():
    from places import routing

    caps = routing.capabilities()
    if caps["available"]:
        pytest.skip("un provider di routing è configurato in questo ambiente")

    assert caps["live_traffic"] is False
    assert "ROUTING_PROVIDER" in caps["why_unavailable"]

    async def ask():
        return await routing.get_route(
            origin={"latitude": HOME[0], "longitude": HOME[1]},
            destination={"latitude": 45.418, "longitude": 11.89},
        )

    result = _run(ask())
    assert result["available"] is False
    for invented in ("duration_seconds", "distance_meters", "reflects_current_traffic"):
        assert invented not in result, f"ha inventato {invented}"


def test_the_provider_is_configuration_not_code():
    source = (HERE / "places" / "routing.py").read_text(encoding="utf-8")
    assert 'PROVIDER_ENV = "ROUTING_PROVIDER"' in source
    assert 'KEY_ENV = "ROUTING_API_KEY"' in source
    # One adapter, not three speculative ones.
    adapters = re.findall(r"async def _(\w+)\(\s*origin", source)
    assert len(adapters) == 1, f"adattatori implementati: {adapters}"


def test_a_routing_failure_is_a_failure_and_not_an_eta_of_zero():
    source = (HERE / "places" / "routing.py").read_text(encoding="utf-8")
    handler = source[source.index("    except Exception as e:"):]
    assert '"available": False' in handler[:400]
    assert "duration" not in handler[:400]
