"""Document analysis version helpers — never ``int("2.0")``.

Two orthogonal concepts:

* **Schema version** (semantic string, e.g. ``"2.0"``) — shape of the analysis
  payload / document schema. Compared as strings (or major/minor ints).
* **Revision counter** (plain int) — how many times analysis/reasoning was
  recomputed for cache invalidation and provenance. Never parse a dotted
  semantic version with ``int()``.
"""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple, Union

DOCUMENT_SCHEMA_VERSION = "2.0"
ANALYSIS_SCHEMA_VERSION = "2.0"
PROCESSING_VERSION = "intel-docs-2.0"

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?([a-zA-Z0-9\-\.]*)?$")
_INT_RE = re.compile(r"^\d+$")


def parse_schema_version(value: Any) -> Tuple[int, int, int]:
    """Parse a semantic schema version into (major, minor, patch).

    Accepts ``"2.0"``, ``"2.0.1"``, ints (treated as major), or None → (0,0,0).
    Never calls ``int("2.0")``.
    """
    if value is None or value == "":
        return (0, 0, 0)
    if isinstance(value, bool):
        return (int(value), 0, 0)
    if isinstance(value, int):
        return (max(0, value), 0, 0)
    if isinstance(value, float):
        # 2.0 float → major=2, minor=0 (float is already split)
        major = int(value)
        minor = int(round((value - major) * 10)) if value != major else 0
        return (max(0, major), max(0, minor), 0)
    s = str(value).strip()
    m = _SEMVER_RE.match(s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    if _INT_RE.match(s):
        return (int(s), 0, 0)
    return (0, 0, 0)


def schema_version_string(value: Any = None) -> str:
    """Normalize to a dotted schema version string."""
    if value is None or value == "":
        return ANALYSIS_SCHEMA_VERSION
    if isinstance(value, str) and _SEMVER_RE.match(value.strip()):
        return value.strip()
    major, minor, patch = parse_schema_version(value)
    if patch:
        return f"{major}.{minor}.{patch}"
    return f"{major}.{minor}"


def is_semantic_version_string(value: Any) -> bool:
    """True when value looks like a dotted schema version (e.g. ``"2.0"``)."""
    if not isinstance(value, str):
        return False
    return bool(_SEMVER_RE.match(value.strip()))


def coerce_analysis_revision(value: Any) -> int:
    """Safe integer revision counter.

    Dotted semantic strings like ``"2.0"`` are schema labels, not counters —
    they coerce to ``0`` (fresh counter) instead of raising ValueError.
    """
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    s = str(value).strip()
    if is_semantic_version_string(s):
        return 0
    if _INT_RE.match(s):
        return max(0, int(s))
    m = re.match(r"^(\d+)", s)
    if m:
        return max(0, int(m.group(1)))
    return 0


def next_analysis_revision(previous: Any) -> int:
    """Bump the revision counter safely from any stored previous value."""
    return coerce_analysis_revision(previous) + 1


def normalize_analysis_version_for_storage(
    analysis_dump: Optional[dict] = None,
    previous_doc_version: Any = None,
) -> int:
    """Pick the integer revision to persist on the document root.

    Prefer the revision computed inside ``DocumentAnalysis``; fall back to a
    safe bump of whatever was previously stored (including legacy ``"2.0"``).
    """
    if analysis_dump and analysis_dump.get("analysis_version") is not None:
        return coerce_analysis_revision(analysis_dump.get("analysis_version"))
    return next_analysis_revision(previous_doc_version)


VersionLike = Union[int, str, float, None]
