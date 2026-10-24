"""Rooms measured by hand: the tape measure is the scanner for anyone without LiDAR."""
import asyncio
import math

import pytest
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError

from house_scans.caps import read_house_measurements
from house_scans.models import AddManualRoom, ManualRoom, UpdateHouseScan
from house_scans.service import HouseScanError, HouseScanService
from house_scans.stats import room_stats, scan_overview


def body(name="Soggiorno", **kw):
    room = {"name": name, "length_m": 5, "width_m": 4, "height_m": 2.7, "doors": 1, "windows": 2}
    room.update(kw.pop("room", {}))
    return AddManualRoom.model_validate({"room": room, **kw})


@pytest.mark.asyncio
async def test_first_room_starts_a_plan_and_more_rooms_join_it():
    svc = HouseScanService(AsyncMongoMockClient().house_manual)
    scan, created = await svc.add_manual_room("u1", body())
    assert created and scan["capture"]["source"] == "manual" and scan["room_count"] == 1
    room = scan["capture"]["rooms"][0]
    assert [w["dimensions"]["x"] for w in room["walls"]] == [5, 4, 5, 4]
    assert len(room["doors"]) == 1 and len(room["windows"]) == 2
    scan, created = await svc.add_manual_room(
        "u1", body("Camera", scan_id=scan["id"], revision=scan["revision"], room={"length_m": 3.5, "width_m": 3}))
    assert not created and scan["room_count"] == 2 and scan["revision"] == 2
    # Another person cannot add to it.
    with pytest.raises(HouseScanError):
        await svc.add_manual_room("u2", body("X", scan_id=scan["id"], revision=2))


@pytest.mark.asyncio
async def test_stale_revision_and_lidar_plans_are_refused():
    db = AsyncMongoMockClient().house_manual_refuse
    svc = HouseScanService(db)
    scan, _ = await svc.add_manual_room("u1", body())
    with pytest.raises(HouseScanError) as stale:
        await svc.add_manual_room("u1", body("B", scan_id=scan["id"], revision=7))
    assert stale.value.status == 409
    await db.house_scans.update_one({"id": scan["id"]}, {"$set": {"source": "apple_roomplan"}})
    with pytest.raises(HouseScanError) as lidar:
        await svc.add_manual_room("u1", body("B", scan_id=scan["id"], revision=1))
    assert lidar.value.status == 409


@pytest.mark.asyncio
async def test_removing_a_room_drops_its_names_and_measurements_but_not_the_last_room():
    svc = HouseScanService(AsyncMongoMockClient().house_manual_remove)
    scan, _ = await svc.add_manual_room("u1", body())
    scan, _ = await svc.add_manual_room("u1", body("Camera", scan_id=scan["id"], revision=1))
    camera = scan["capture"]["rooms"][1]["id"]
    scan = await svc.update("u1", scan["id"], UpdateHouseScan.model_validate({
        "revision": scan["revision"],
        "room_labels": [{"room_id": camera, "name": "Camera da letto"}],
        "wall_measurements": [{"room_id": camera, "wall_id": "wall-1", "length_m": 5.02}],
    }))
    assert scan["verified_wall_count"] == 1
    scan = await svc.remove_manual_room("u1", scan["id"], camera, scan["revision"])
    assert scan["room_count"] == 1 and scan["verified_wall_count"] == 0 and not scan["room_labels"]
    with pytest.raises(HouseScanError):
        await svc.remove_manual_room("u1", scan["id"], scan["capture"]["rooms"][0]["id"], scan["revision"])


def test_numbers_people_ask_for():
    from house_scans.manual import build_room
    room = build_room(ManualRoom(name="S", length_m=5, width_m=4, height_m=2.7, doors=1, windows=2))
    stats = room_stats(room)
    assert stats["floor_area_m2"] == 20 and not stats["floor_area_approximate"]
    assert stats["perimeter_m"] == 18 and stats["height_m"] == 2.7
    assert stats["wall_area_m2"] == pytest.approx(48.6)
    assert stats["paintable_wall_area_m2"] == pytest.approx(48.6 - 0.8 * 2.1 - 2 * 1.2 * 1.2)
    verified = room_stats(room, [{"room_id": room["id"], "wall_id": "wall-1", "length_m": 5.1}])
    assert verified["perimeter_m"] == 18.1 and verified["verified_walls"] == 1
    # Without a floor surface the area is the enclosed rectangle, flagged as approximate.
    bare = {**room, "floors": []}
    assert room_stats(bare)["floor_area_m2"] == pytest.approx(20) and room_stats(bare)["floor_area_approximate"]


def test_manual_room_bounds():
    with pytest.raises(ValidationError):
        ManualRoom(name="S", length_m=0.1, width_m=3)
    with pytest.raises(ValidationError):
        ManualRoom(name="S", length_m=3, width_m=3, doors=9)
    with pytest.raises(ValidationError):
        AddManualRoom.model_validate({"room": {"name": "S", "length_m": 3, "width_m": 3}, "scan_id": "a" * 32})


@pytest.mark.asyncio
async def test_ora_can_read_the_sizes_in_conversation():
    db = AsyncMongoMockClient().house_manual_caps
    empty = await read_house_measurements({}, {"user_id": "u1", "db": db})
    assert empty.payload["status"] == "NO_HOUSE_PLAN"
    svc = HouseScanService(db)
    await svc.add_manual_room("u1", body())
    seen = await read_house_measurements({}, {"user_id": "u1", "db": db})
    plan = seen.payload["plans"][0]
    assert plan["total_floor_area_m2"] == 20 and plan["rooms"][0]["name"] == "Soggiorno"
    assert "transform" not in str(seen.payload) and "wall-1" not in str(seen.payload)
