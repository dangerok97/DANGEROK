"""Search provider protocol — retrieval only, not synthesis."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional


SnippetOrigin = Literal["unknown", "search_snippet", "grounded_model_segment"]


def normalize_snippet_origin(value: object) -> SnippetOrigin:
    """Only adapter-supplied provenance; absent/invalid tags attest nothing."""
    if isinstance(value, str):
        if value == "search_snippet":
            return "search_snippet"
        if value == "grounded_model_segment":
            return "grounded_model_segment"
    return "unknown"


@dataclass
class RawHit:
    title: str = ""
    url: str = ""
    snippet: str = ""
    snippet_origin: SnippetOrigin = "unknown"


@dataclass
class ProviderResult:
    ok: bool
    provider: str
    hits: List[RawHit] = field(default_factory=list)
    failure_code: Optional[str] = None
    raw_answer: Optional[str] = None  # never treat as authoritative fact
