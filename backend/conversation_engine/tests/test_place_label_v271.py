"""Generic place-label resolver — no city hardcoding."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from location.place_label import (
    ACCURACY_ADMIN_ONLY_M,
    resolve_place_from_address,
)


def test_a_locality_and_municipality():
    addr = {
        "village": "Sample Locality",
        "town": "Sample Municipality",
        "state": "Sample Region",
        "country": "Sample Country",
    }
    p = resolve_place_from_address(addr, accuracy_meters=25)
    assert p.display_label == "Sample Locality"
    assert p.locality == "Sample Locality"
    assert p.municipality == "Sample Municipality"
    assert p.region == "Sample Region"
    assert p.precision == "locality"


def test_a2_village_beats_neighbourhood():
    """Settlement (village) preferred over micro neighbourhood when both present."""
    addr = {
        "neighbourhood": "Micro Quarter",
        "village": "Named Settlement",
        "town": "Admin Town",
        "country": "X",
    }
    p = resolve_place_from_address(addr, accuracy_meters=25)
    assert p.display_label == "Named Settlement"
    assert p.locality == "Named Settlement"
    assert p.municipality == "Admin Town"


def test_b_village_preferred_over_town():
    addr = {"village": "Harbor Village", "town": "Big Town", "country": "X"}
    p = resolve_place_from_address(addr, accuracy_meters=40)
    assert p.display_label == "Harbor Village"
    assert p.municipality == "Big Town"


def test_c_suburb_inside_city_no_duplication():
    addr = {"suburb": "Northside", "city": "Metrocity", "country": "X"}
    p = resolve_place_from_address(addr, accuracy_meters=30)
    assert p.display_label == "Northside"
    assert p.locality == "Northside"
    assert p.municipality == "Metrocity"
    # display is locality only — municipality kept structured
    assert p.display_label != p.municipality


def test_d_only_city():
    addr = {"city": "OnlyCity", "country": "X"}
    p = resolve_place_from_address(addr, accuracy_meters=50)
    assert p.display_label == "OnlyCity"
    assert p.municipality == "OnlyCity"
    assert p.locality is None
    assert p.precision == "municipality"


def test_e_only_municipality():
    addr = {"municipality": "OnlyMuni"}
    p = resolve_place_from_address(addr, accuracy_meters=50)
    assert p.display_label == "OnlyMuni"
    assert p.precision == "municipality"


def test_f_conflicting_empty_conservative():
    p = resolve_place_from_address({}, display_name="Fallback Place, Somewhere")
    assert p.display_label == "Fallback Place"
    p2 = resolve_place_from_address({})
    assert p2.display_label is None
    assert p2.precision == "none"
    # locality same as admin → still ok, no forced split
    p3 = resolve_place_from_address(
        {"village": "SameName", "town": "SameName"}, accuracy_meters=20
    )
    assert p3.display_label == "SameName"


def test_g_hamlet_does_not_beat_village():
    addr = {
        "hamlet": "Tiny Hamlet",
        "village": "Useful Village",
        "town": "Admin Town",
    }
    p = resolve_place_from_address(addr, accuracy_meters=20)
    assert p.display_label == "Useful Village"
    assert p.locality == "Useful Village"


def test_h_poor_accuracy_blocks_locality():
    addr = {
        "village": "Precise Village",
        "town": "Admin Town",
        "country": "X",
    }
    p = resolve_place_from_address(
        addr, accuracy_meters=ACCURACY_ADMIN_ONLY_M + 500
    )
    assert p.display_label == "Admin Town"
    assert p.locality is None
    assert p.precision == "municipality"


def test_i_hamlet_only_when_accuracy_good():
    addr = {"hamlet": "Micro Spot", "town": "Admin Town"}
    poor = resolve_place_from_address(addr, accuracy_meters=400)
    assert poor.display_label == "Admin Town"
    good = resolve_place_from_address(addr, accuracy_meters=40)
    assert good.display_label == "Micro Spot"


def test_j_no_hardcoded_places():
    src = inspect.getsource(resolve_place_from_address)
    blob = src.lower()
    for bad in (
        "vibo",
        "tarquinia",
        "marina",
        "home",
        "work",
        "gym",
        "office",
    ):
        assert bad not in blob


@pytest.mark.asyncio
async def test_k_broker_minimized_structured(db=None):
    from location.models import PresenceContext

    p = PresenceContext(
        user_id="u1",
        freshness="CURRENT",
        place_label="Sample Locality",
        place_locality="Sample Locality",
        place_municipality="Sample Municipality",
        place_region="Sample Region",
        place_country="Sample Country",
        place_label_precision="locality",
        latitude=10.0,
        longitude=20.0,
    )
    b = p.for_broker()
    assert b["label"] == "Sample Locality"
    assert b["locality"] == "Sample Locality"
    assert b["municipality"] == "Sample Municipality"
    assert "house_number" not in b
    assert "road" not in str(b)
    ai = p.for_ai()
    assert ai["place"]["display_label"] == "Sample Locality"
    assert ai["place"]["municipality"] == "Sample Municipality"
