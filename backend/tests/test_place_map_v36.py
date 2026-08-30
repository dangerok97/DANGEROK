"""
Adding a place by address, by map, or by standing in it.

    ADDRESS != LOCATION
    GOOGLE SUGGESTS. MAP VISUALIZES. USER CONFIRMS.

An address is a readable description of somewhere. The point is where the
person actually means, and the two disagree often enough to matter: Google
drops the pin on the street and the entrance is round the back. So the map has
the last word, and `location_source` records who had it.

The Places key never leaves the server — the browser asks ORA, and ORA asks
Google. The Maps key does ship to the browser, because a Maps JS key is a
browser key by definition; what must not happen, and is checked here, is
either of them living in the repository.
"""

from __future__ import annotations

import os
import re
import subprocess
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
REPO = HERE.parent

GOOGLE_KEY = re.compile(r"AIzaSy[0-9A-Za-z_\-]{25,}")

# Two points a few metres apart: what Google proposes, and where the person
# actually means once they have moved the map.
PROPOSED = (45.40640, 11.87680)
CORRECTED = (45.40668, 11.87712)


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

    return Coordinates(latitude=lat, longitude=lon, precision="exact")


async def _clean(db, uid):
    for coll in ("life_places", "presence_sessions", "presence_states",
                 "presence_observations", "place_candidates"):
        await db[coll].delete_many({"user_id": uid})


def _read(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def _code(text: str) -> str:
    """
    The file with its explanations removed.

    A docstring saying "we do not ask for reviews" is the opposite of asking
    for reviews, and a guard that cannot tell the difference is a guard that
    fails on its own good behaviour.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    triple = chr(34) * 3
    text = re.sub(triple + "(?:.|" + chr(10) + ")*?" + triple, "", text)
    kept = [l for l in text.splitlines()
            if not l.strip().startswith("//") and not l.strip().startswith("#")]
    return " ; ".join(kept)


# ---------------------------------------------------------------------------
# Asking Google as little as possible
# ---------------------------------------------------------------------------

def test_the_detail_call_asks_for_four_fields_and_no_more():
    """
    Places (New) will return opening hours, photographs and reviews, each of
    them billed and none of them anybody's business here. A place needs a name
    somebody can read and a point on the earth.
    """
    raw = (HERE / "places" / "lookup.py").read_text(encoding="utf-8")
    source = _code(raw)
    mask = re.search(r'"X-Goog-FieldMask":\s*"([^"]+)"', source.split("async def resolve")[1])
    assert mask, "la resolve non dichiara una field mask"
    fields = set(mask.group(1).split(","))
    assert fields == {"id", "formattedAddress", "location", "addressComponents"}
    for extra in ("photos", "reviews", "regularOpeningHours", "rating", "priceLevel"):
        assert extra not in source, f"chiede un campo che non serve: {extra}"


def test_a_search_is_one_billed_lookup_and_not_one_per_keystroke():
    source = (HERE / "places" / "lookup.py").read_text(encoding="utf-8")
    assert "sessionToken" in source
    # And the client debounces rather than firing on every character.
    editor = _read("src/components/vita/PlaceEditor.tsx")
    assert "setTimeout" in editor and "350" in editor
    assert "sessionToken" in editor


def test_two_characters_are_not_worth_asking_google_about(monkeypatch):
    from places import lookup

    monkeypatch.setenv("PLACES_API_KEY", "unused-because-nothing-is-sent")

    async def ask():
        return await lookup.suggest("Vi")

    result = _run(ask())
    assert result["too_short"] is True and result["suggestions"] == []


def test_the_places_key_never_reaches_the_browser():
    for relative in ("src", "app"):
        for path in (FRONTEND / relative).rglob("*.ts*"):
            if "node_modules" in str(path):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert "PLACES_API_KEY" not in text, f"{path.name} nomina la chiave server-side"
            assert "places.googleapis.com" not in text, (
                f"{path.name} chiama Google direttamente invece di passare da ORA"
            )


# ---------------------------------------------------------------------------
# The map has the last word
# ---------------------------------------------------------------------------

def test_a_point_moved_by_hand_is_the_one_that_gets_saved():
    """
    §9. Google proposes A, the person leaves the map on B. B is saved, and
    `map_selection` says why — putting A back would be ORA overruling somebody
    about where their own front door is.
    """
    async def body():
        client, db = await _db()
        uid = f"u_map_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(
                uid,
                label="Casa test",
                coordinates=_coords(*CORRECTED),
                address="Via Roma 1, Padova PD, Italia",
                locality="Padova",
                google_place_id="ChIJ_test_place_id",
                location_source="map_selection",
            )
            assert place.coordinates.latitude == pytest.approx(CORRECTED[0])
            assert place.coordinates.longitude == pytest.approx(CORRECTED[1])
            assert place.coordinates.latitude != pytest.approx(PROPOSED[0])
            assert place.location_source == "map_selection"
            # The address stays: it is still what the place is called.
            assert place.address.startswith("Via Roma 1")
            assert place.google_place_id == "ChIJ_test_place_id"

            # And it survives being read back, which is what "riapri il luogo"
            # actually means.
            again = await (await _service(db)).get_place(uid, place.id)
            assert again.coordinates.latitude == pytest.approx(CORRECTED[0])
            assert again.location_source == "map_selection"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_address_accepted_as_proposed_says_so():
    async def body():
        client, db = await _db()
        uid = f"u_map_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(
                uid,
                label="Ufficio test",
                coordinates=_coords(*PROPOSED),
                address="Via Roma 1, Padova PD, Italia",
                google_place_id="ChIJ_test_place_id",
                location_source="google_place",
            )
            assert place.location_source == "google_place"
            assert place.public()["from_address"] is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_place_chosen_only_on_the_map_needs_no_address_at_all():
    """§22: "Casa dei nonni" has a point and a name and nothing else."""
    async def body():
        client, db = await _db()
        uid = f"u_map_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(
                uid,
                label="Casa dei nonni",
                coordinates=_coords(*CORRECTED),
                location_source="map_selection",
            )
            assert place.google_place_id == ""
            assert place.address == ""
            assert place.coordinates is not None
            assert place.public()["from_address"] is False
            assert place.location_source == "map_selection"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_name_with_nowhere_attached_is_honest_about_it():
    async def body():
        client, db = await _db()
        uid = f"u_map_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(uid, label="Da capire")
            assert place.coordinates is None
            assert place.location_source == "name_only"
            assert place.public()["has_coordinates"] is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_correcting_a_place_later_uses_the_same_path_that_created_it():
    """§14: one editor, so a place fixed in six months matches one got right."""
    async def body():
        client, db = await _db()
        uid = f"u_map_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(
                uid,
                label="Casa",
                role="home",
                coordinates=_coords(*PROPOSED),
                address="Via Roma 1, Padova",
                google_place_id="ChIJ_old",
                location_source="google_place",
            )
            # The zone was drawn around the old point.
            await service.set_zone(uid, place.id, entry_radius_m=90, exit_radius_m=140)

            moved = await service.relocate_place(
                uid,
                place.id,
                coordinates=_coords(*CORRECTED),
                location_source="map_selection",
            )
            assert moved.coordinates.latitude == pytest.approx(CORRECTED[0])
            assert moved.location_source == "map_selection"
            # The zone follows: a circle round the old pin would watch the
            # wrong building.
            assert moved.zone.center.latitude == pytest.approx(CORRECTED[0])
            assert moved.zone.entry_radius_m == 90
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_editor_keeps_the_address_when_the_pin_is_moved():
    """
    Structural. Moving the map changes where, not what the place is called —
    dropping the address would lose the only readable thing about it.
    """
    editor = _read("src/components/vita/PlaceEditor.tsx")
    moved = editor[editor.index("const onPointChange"):]
    moved = moved[: moved.index("const save")]
    assert "setSource('map_selection')" in moved
    assert "setAddress('')" not in moved, "spostare il punto cancella l'indirizzo"


# ---------------------------------------------------------------------------
# Standing in it
# ---------------------------------------------------------------------------

def test_being_here_still_opens_a_stay_without_waiting_for_dwell():
    async def body():
        client, db = await _db()
        uid = f"u_map_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(
                uid,
                label="Casa",
                role="home",
                coordinates=_coords(*PROPOSED),
                source="current_position",
                location_source="current_position",
                currently_here=True,
            )
            summary = (await service.presence_summary(uid))[place.id]
            assert summary["present"] is True
            open_stays = [
                s for s in await service.repo.sessions_for(uid, place_id=place.id)
                if s.exited_at is None
            ]
            assert len(open_stays) == 1
            assert open_stays[0].source == "user_confirmation"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_moving_the_map_after_using_your_position_stops_claiming_you_are_here():
    """
    A point somebody dragged away from where the device said they are is no
    longer a statement about being there.
    """
    editor = _read("src/components/vita/PlaceEditor.tsx")
    assert "currently_here: !nameOnly && fromCurrentPosition && !movedByHand" in editor


# ---------------------------------------------------------------------------
# The map itself
# ---------------------------------------------------------------------------

def test_the_pin_does_not_move_the_map_does():
    raw = _read("src/components/vita/MapPicker.tsx")
    assert 'pointerEvents="none"' in raw, "il pin intercetta i gesti"
    # The answer is where the map came to rest, not every pixel of the drag.
    picker = _code(raw)
    assert "addListener('idle'" in picker
    assert "center_changed" not in picker


def test_the_picker_says_what_is_wrong_instead_of_showing_a_grey_box():
    picker = _read("src/components/vita/MapPicker.tsx")
    for state in ("unavailable", "failed", "loading"):
        assert state in picker
    assert "script-error" in picker, "un referrer non autorizzato non viene gestito"
    assert "versione web" in picker, "su nativo non spiega perché non c'è la mappa"


def test_the_maps_key_is_never_written_into_a_component():
    for relative in ("src/components/vita/MapPicker.tsx",
                     "src/components/vita/PlaceEditor.tsx"):
        source = _read(relative)
        assert not GOOGLE_KEY.search(source)
        assert "EXPO_PUBLIC_MAPS_WEB_KEY" not in source, (
            f"{relative} legge la chiave invece di passare da src/config/maps"
        )


def test_no_google_key_is_tracked_or_waiting_to_be():
    tracked = subprocess.run(
        ["git", "grep", "-lI", "-E", r"AIzaSy[0-9A-Za-z_\-]{25,}", "--", "."],
        cwd=str(REPO), capture_output=True, text=True,
    )
    assert not tracked.stdout.strip(), f"chiavi tracciate: {tracked.stdout}"

    listed = subprocess.run(
        ["git", "ls-files", "-mo", "--exclude-standard"],
        cwd=str(REPO), capture_output=True, text=True,
    )
    offenders = []
    for name in listed.stdout.splitlines():
        if not name.strip() or "node_modules" in name or "__pycache__" in name:
            continue
        path = REPO / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        if GOOGLE_KEY.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(name)
    assert not offenders, f"chiavi committabili: {offenders}"


# ---------------------------------------------------------------------------
# Nothing needs a manual refresh, and no reverse geocoding was smuggled in
# ---------------------------------------------------------------------------

def test_saving_and_deleting_both_invalidate():
    section = _read("src/components/vita/PlacesSection.tsx")
    detail = _read("app/place/[placeId].tsx")
    assert "invalidatePlace()" in section
    assert "invalidatePlace(String(placeId))" in detail
    remove = detail[detail.index("await api.placesRemove"):]
    assert remove.index("invalidatePlace") < remove.index("router.back")


def test_the_row_shows_an_address_and_never_a_coordinate():
    section = _read("src/components/vita/PlacesSection.tsx")
    assert "place.address || place.locality" in section
    # What is *rendered*, not what is passed to the API on the way out: the
    # row must never print a number nobody can check.
    rendered = re.findall(r"<Text[^>]*>([\s\S]*?)</Text>", section)
    for chunk in rendered:
        # A JSX comment saying "never coordinates" is not a coordinate.
        chunk = re.sub(r"\{/\*[\s\S]*?\*/\}", "", chunk)
        for leak in ("latitude", "longitude", "coordinates"):
            assert leak not in chunk, f"la lista mostra {leak}"


def test_no_geocoding_api_was_enabled_behind_anybody_s_back():
    """
    §17. A point with no address is saved as a point with no address. Turning
    on another billed API to invent one is not a decision this task had.
    """
    for path in (HERE / "places").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "maps.googleapis.com/maps/api/geocode" not in source
        assert "reverseGeocode" not in source


# ---------------------------------------------------------------------------
# Navigation, as buttons that open
# ---------------------------------------------------------------------------

def test_the_map_apps_reach_the_turn_as_openable_links():
    # Computed in the loop, where the observations of the turn actually exist,
    # carried on the turn result, and forwarded by the orchestrator. Reading
    # them anywhere else was a NameError in production and is why this checks
    # all three links rather than one.
    loop = (HERE / "conversation_engine" / "ai_core" / "loop.py").read_text(encoding="utf-8")
    assert "navigation=_navigation_options(observations)" in loop
    assert "open_navigation" in loop

    models = (HERE / "conversation_engine" / "ai_core" / "models.py").read_text(encoding="utf-8")
    assert "navigation: List[Dict[str, str]]" in models

    orchestrator = (
        HERE / "conversation_engine" / "ai_core" / "orchestrator.py"
    ).read_text(encoding="utf-8")
    assert 'getattr(result, "navigation", None)' in orchestrator

    turns = _read("src/components/ora/OraTurns.tsx")
    assert "OraNavigation" in turns
    assert "Linking.openURL" in turns
    # A button with no link is a button that does nothing.
    assert "url && label" in turns

    # History knows the words and nothing else, so a turn rebuilt from it
    # would lose the buttons and leave "con quale app vuoi navigare?" with
    # nothing to answer it.
    screen = _read("src/components/ora/OraConversationScreen.tsx")
    assert "lastNavigation" in screen
    assert "rememberExtras" in screen


def test_only_apps_the_platform_can_actually_open_are_offered():
    """Apple Maps on Android is a dead end with a logo on it."""
    from places.navigation import available_apps

    android = {a["id"] for a in available_apps("android")}
    assert "apple_maps" not in android
    assert {"google_maps", "waze"} <= android

    web = {a["id"] for a in available_apps("web")}
    assert {"google_maps", "waze"} <= web
