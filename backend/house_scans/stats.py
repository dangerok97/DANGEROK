"""
Numbers people actually ask for: how big is a room, how much wall to paint.

Lengths prefer a measurement the person verified with a tape over the scan's
estimate. Floor area comes from the floor surface when there is one, else
from the rectangle the walls enclose — and then it says it is approximate.
"""
from __future__ import annotations

import math


def _wall_line(wall: dict):
    t = wall.get("transform") or []
    length = float((wall.get("dimensions") or {}).get("x") or 0)
    if len(t) != 16 or length <= 0:
        return None
    dx, dz = t[0] * length / 2, t[2] * length / 2
    return (t[12] - dx, t[14] - dz), (t[12] + dx, t[14] + dz)


def room_stats(room: dict, measurements: list[dict] | None = None) -> dict:
    verified = {
        m["wall_id"]: float(m["length_m"])
        for m in (measurements or []) if m.get("room_id") == room.get("id")
    }
    walls = room.get("walls") or []
    lengths = [verified.get(w["id"], float(w["dimensions"]["x"])) for w in walls]
    heights = [float(w["dimensions"]["y"]) for w in walls if w["dimensions"].get("y")]
    height = max(heights) if heights else 0.0
    openings = sum(
        float(o["dimensions"]["x"]) * float(o["dimensions"]["y"])
        for group in ("doors", "windows", "openings") for o in (room.get(group) or [])
    )
    wall_area = sum(
        length * float(w["dimensions"]["y"]) for length, w in zip(lengths, walls)
    )
    floor_area, approximate = None, False
    floors = room.get("floors") or []
    if floors:
        d = floors[0]["dimensions"]
        depth = float(d.get("y") or 0) or float(d.get("z") or 0)
        if float(d.get("x") or 0) > 0 and depth > 0:
            floor_area = float(d["x"]) * depth
    if floor_area is None:
        points = [p for w in walls if (line := _wall_line(w)) for p in line]
        if points:
            xs, zs = [p[0] for p in points], [p[1] for p in points]
            floor_area = (max(xs) - min(xs)) * (max(zs) - min(zs))
            approximate = True
    return {
        "floor_area_m2": round(floor_area, 2) if floor_area else None,
        "floor_area_approximate": approximate,
        "perimeter_m": round(sum(lengths), 2),
        "height_m": round(height, 2),
        "wall_area_m2": round(wall_area, 2),
        "paintable_wall_area_m2": round(max(wall_area - openings, 0.0), 2),
        "doors": len(room.get("doors") or []),
        "windows": len(room.get("windows") or []),
        "verified_walls": len(verified),
        "walls": len(walls),
    }


def scan_overview(scan: dict) -> dict:
    labels = {l["room_id"]: l["name"] for l in scan.get("room_labels") or []}
    rooms = []
    for room in scan["capture"]["rooms"]:
        stats = room_stats(room, scan.get("wall_measurements"))
        rooms.append({"name": labels.get(room["id"], room["name"]), **stats})
    total = sum(r["floor_area_m2"] or 0 for r in rooms)
    return {
        "title": scan["title"],
        "source": "misure inserite a mano" if scan["capture"]["source"] == "manual" else "scansione LiDAR",
        "measured_on": scan["captured_at"],
        "total_floor_area_m2": round(total, 2) if not math.isclose(total, 0) else None,
        "rooms": rooms,
    }
