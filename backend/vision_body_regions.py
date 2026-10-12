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
