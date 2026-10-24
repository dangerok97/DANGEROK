"""
Rooms measured by hand, drawn in the same geometry a scan produces.

A web app on iPhone cannot reach the LiDAR sensor, so for most people the
tape measure is the scanner. Length, width and height of a rectangular room
become four walls, a floor, and doors and windows spread along two walls —
the same shapes the plan, the wall list and the measurement overlay already
understand. What is drawn is exactly what was typed: nothing is estimated.
"""
from __future__ import annotations

import math
import uuid

from .models import ManualRoom

DOOR_W, DOOR_H = 0.8, 2.1
WINDOW_W, WINDOW_H = 1.2, 1.2


def _transform(x: float, y: float, z: float, angle: float = 0.0) -> list[float]:
    """Column-major rigid transform: rotation about the vertical axis, then translation."""
    c, s = math.cos(angle), math.sin(angle)
    c = 0.0 if abs(c) < 1e-12 else c
    s = 0.0 if abs(s) < 1e-12 else s
    return [c, 0.0, -s, 0.0, 0.0, 1.0, 0.0, 0.0, s, 0.0, c, 0.0, x, y, z, 1.0]


def _flat(x: float, y: float, z: float) -> list[float]:
    """A surface lying on the floor: local Y turned to point along the room's depth."""
    return [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 1.0, 0.0, 0.0, x, y, z, 1.0]


def _spread(count: int, wall_length: float, width: float) -> list[tuple[float, float]]:
    """Centres along a wall, evenly spaced, each opening narrowed to fit."""
    if count <= 0:
        return []
    slot = wall_length / count
    w = min(width, slot * 0.8)
    return [(-wall_length / 2 + slot * (i + 0.5), w) for i in range(count)]


def build_room(room: ManualRoom) -> dict:
    length, width, height = room.length_m, room.width_m, room.height_m
    half_l, half_w, mid = length / 2, width / 2, height / 2
    walls = [
        {"id": "wall-1", "dimensions": {"x": length, "y": height, "z": 0.0},
         "transform": _transform(0.0, mid, -half_w), "confidence": "high"},
        {"id": "wall-2", "dimensions": {"x": width, "y": height, "z": 0.0},
         "transform": _transform(half_l, mid, 0.0, math.pi / 2), "confidence": "high"},
        {"id": "wall-3", "dimensions": {"x": length, "y": height, "z": 0.0},
         "transform": _transform(0.0, mid, half_w, math.pi), "confidence": "high"},
        {"id": "wall-4", "dimensions": {"x": width, "y": height, "z": 0.0},
         "transform": _transform(-half_l, mid, 0.0, -math.pi / 2), "confidence": "high"},
    ]
    door_h = min(DOOR_H, height - 0.05)
    doors = [
        {"id": f"door-{i + 1}", "dimensions": {"x": w, "y": door_h, "z": 0.0},
         "transform": _transform(x, door_h / 2, -half_w), "confidence": "high"}
        for i, (x, w) in enumerate(_spread(room.doors, length, DOOR_W))
    ]
    window_h = min(WINDOW_H, height / 2)
    windows = [
        {"id": f"window-{i + 1}", "dimensions": {"x": w, "y": window_h, "z": 0.0},
         # The window's centre is drawn at the window's height, not the floor's.
         "transform": _transform(-x, height * 0.55, half_w, math.pi), "confidence": "high"}
        for i, (x, w) in enumerate(_spread(room.windows, length, WINDOW_W))
    ]
    return {
        "id": "room-" + uuid.uuid4().hex[:12],
        "name": room.name,
        "walls": walls,
        "doors": doors,
        "windows": windows,
        "openings": [],
        "floors": [{"id": "floor-1", "dimensions": {"x": length, "y": width, "z": 0.0},
                    "transform": _flat(0.0, 0.0, 0.0), "confidence": "high"}],
        "objects": [],
    }
