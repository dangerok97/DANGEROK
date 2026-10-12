"""Recognize a human region without estimating sex, gender or identity.

For a photographed person, only use a generic, locally rendered atlas. Neither
the photographed pixels nor anatomical traits enter the persistent object catalog.
"""
from __future__ import annotations

REGIONS = frozenset({"full_body", "face", "hand", "arm", "torso", "abdomen", "leg"})
_KEYS = {
    "human_anatomy": "full_body", "human_body": "full_body", "human": "full_body",
    "person": "full_body", "person_body": "full_body", "person_full_body": "full_body",
    "human_face": "face", "face": "face", "human_head": "face", "head": "face",
    "human_hand": "hand", "hand": "hand", "palm": "hand", "fingers": "hand",
    "human_arm": "arm", "arm": "arm", "forearm": "arm",
    "human_torso": "torso", "torso": "torso", "chest": "torso",
    "abdomen": "abdomen", "human_abdomen": "abdomen", "belly": "abdomen",
    "leg": "leg", "human_leg": "leg", "thigh": "leg", "foot": "leg",
}

def anatomy_region(identification: dict) -> str | None:
    key = identification.get("canonical_key", "")
    if key not in _KEYS:
        return None
    requested = identification.get("body_region")
    if isinstance(requested, str) and requested in REGIONS:
        return requested
    return _KEYS[key]


# Public API uses this only for one-shot, approximate study-space orientation.
# Images, raw landmarks and inferred traits are not stored in the shared catalog.
LANDMARK_NAMES = frozenset({
    "left_shoulder","right_shoulder","left_hip","right_hip",
    "left_elbow","right_elbow","left_wrist","right_wrist",
    "left_knee","right_knee","left_ankle","right_ankle",
})
def normalize_pose_points(raw) -> dict | None:
    import math
    if not isinstance(raw, dict):
        return None
    accepted = {}
    for name, pair in raw.items():
        if name not in LANDMARK_NAMES or not isinstance(pair, list) or len(pair)!=2:
            continue
        if any(isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) for n in pair):
            continue
        if not all(0 <= v <= 1000 for v in pair):
            continue
        divisor = 1 if max(pair) <= 1 else 1000
        accepted[name] = [round(float(pair[0])/divisor,5),round(float(pair[1])/divisor,5)]
    left=accepted.get("left_shoulder")
    right=accepted.get("right_shoulder")
    if not left or not right:
        return None
    if not .06 <= abs(left[0]-right[0]) <= .90:
        return None
    if abs(left[1]-right[1]) > .45:
        return None
    return accepted
