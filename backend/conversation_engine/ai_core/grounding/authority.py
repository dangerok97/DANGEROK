"""Lightweight source authority bands — metadata for AI, not domain logic."""
from __future__ import annotations

import re
from typing import Literal

SourceAuthority = Literal[
    "OFFICIAL_PRIMARY",
    "AUTHORITATIVE_PRIMARY",
    "REPUTABLE_SECONDARY",
    "COMMUNITY",
    "UNKNOWN",
]

_OFFICIAL = re.compile(
    r"(\.gov|\.gov\.|\.edu|europa\.eu|who\.int|istat\.it|inps\.it|"
    r"agenziaentrate|mit\.gov|poliziadistato|interno\.gov)",
    re.I,
)
_AUTH = re.compile(
    r"(wikipedia\.org|reuters\.com|bbc\.|nytimes\.|ft\.com|"
    r"ilsole24ore|ansa\.it|corriere\.it|repubblica\.it)",
    re.I,
)
_COMMUNITY = re.compile(
    r"(reddit\.com|quora\.com|forum|blogspot|medium\.com|facebook\.com)",
    re.I,
)


def authority_for_url(url: str, *, title: str = "") -> SourceAuthority:
    blob = f"{url or ''} {title or ''}"
    if _OFFICIAL.search(blob):
        return "OFFICIAL_PRIMARY"
    if _AUTH.search(blob):
        return "AUTHORITATIVE_PRIMARY"
    if _COMMUNITY.search(blob):
        return "COMMUNITY"
    if url and url.startswith("http"):
        return "REPUTABLE_SECONDARY"
    return "UNKNOWN"
