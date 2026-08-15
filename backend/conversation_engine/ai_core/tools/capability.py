"""Capability metadata — AI sees capabilities; providers stay below."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional

from conversation_engine.ai_core.models import Observation

SideEffect = Literal["READ_ONLY", "REVERSIBLE_WRITE", "CONSEQUENTIAL_WRITE"]
Classification = Literal["external", "personal", "conversation"]

ToolHandler = Callable[[Dict[str, Any], Dict[str, Any]], Awaitable[Observation]]


@dataclass
class CapabilitySpec:
    capability: str
    description: str
    input_schema: Dict[str, Any]
    classification: Classification = "personal"
    side_effect: SideEffect = "READ_ONLY"
    freshness: str = "n/a"
    risk: str = "read"  # legacy compat: read | write_soft
    availability: str = "available"  # available | not_configured | disabled
    authority_hint: str = ""
    handler: Optional[ToolHandler] = None
    # Internal only — never in list_public
    provider_hint: str = ""
    tags: List[str] = field(default_factory=list)

    def public(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "name": self.capability,  # alias for tool_call.name
            "description": self.description,
            "classification": self.classification,
            "side_effect": self.side_effect,
            "freshness": self.freshness,
            "input_schema": self.input_schema,
            "availability": self.availability,
            "risk": self.risk,
        }
