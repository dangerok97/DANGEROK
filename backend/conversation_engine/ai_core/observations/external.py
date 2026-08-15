"""External tool observations — evidence for AI re-entry, not UI dumps."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from conversation_engine.ai_core.grounding.authority import SourceAuthority

Freshness = Literal["realtime", "hours", "days", "unknown", "n/a"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_observation_id() -> str:
    return f"obs_{uuid.uuid4().hex[:12]}"


def new_source_id() -> str:
    return f"src_{uuid.uuid4().hex[:10]}"


class ExternalSource(BaseModel):
    source_id: str = Field(default_factory=new_source_id)
    title: str = ""
    url: str = ""
    snippet: str = ""
    authority_hint: SourceAuthority = "UNKNOWN"
    retrieved_at: str = Field(default_factory=_now)


class ExternalObservation(BaseModel):
    observation_id: str = Field(default_factory=new_observation_id)
    capability: str
    query: str = ""
    retrieved_at: str = Field(default_factory=_now)
    freshness: Freshness = "unknown"
    sources: List[ExternalSource] = Field(default_factory=list)
    findings: List[str] = Field(default_factory=list)
    status: str = "ok"  # ok | failed | empty
    failure_code: Optional[str] = None
    provider_internal: Optional[str] = None  # never expose to UI
    notes: List[str] = Field(default_factory=list)
    grounding: str = "TOOL_OBSERVATION"

    def to_loop_payload(self) -> Dict[str, Any]:
        """Public-to-AI payload (no secrets; provider name only as soft hint)."""
        return {
            "observation_id": self.observation_id,
            "capability": self.capability,
            "query": self.query[:200],
            "retrieved_at": self.retrieved_at,
            "freshness": self.freshness,
            "status": self.status,
            "failure_code": self.failure_code,
            "grounding": self.grounding,
            "findings": self.findings[:8],
            "sources": [
                {
                    "source_id": s.source_id,
                    "title": (s.title or "")[:120],
                    "url": (s.url or "")[:300],
                    "snippet": (s.snippet or "")[:280],
                    "authority_hint": s.authority_hint,
                }
                for s in self.sources[:6]
            ],
            "notes": self.notes[:4],
            # Explicit capability limits for web_search
            "capability_limits": (
                [
                    "web_search is NOT live traffic, Maps routing, booking, or weather APIs",
                    "Do not invent operational precision beyond these snippets",
                ]
                if self.capability == "web_search"
                else []
            ),
        }

    def public_sources_for_ui(self) -> List[Dict[str, str]]:
        out = []
        for s in self.sources[:5]:
            if not (s.title or s.url):
                continue
            out.append(
                {
                    "title": (s.title or s.url)[:80],
                    "url": (s.url or "")[:300],
                }
            )
        return out
