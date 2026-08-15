"""Search provider protocol — retrieval only, not synthesis."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RawHit:
    title: str = ""
    url: str = ""
    snippet: str = ""


@dataclass
class ProviderResult:
    ok: bool
    provider: str
    hits: List[RawHit] = field(default_factory=list)
    failure_code: Optional[str] = None
    raw_answer: Optional[str] = None  # never treat as authoritative fact
