"""Slot schema primitives — required / optional / conditional."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from semantic_engine.models import QuestionChip

SlotKind = Literal["required", "optional", "conditional"]


class SlotDef(BaseModel):
    name: str
    kind: SlotKind = "required"
    question_template: str
    question_reason: str = ""
    chips: List[QuestionChip] = Field(default_factory=list)
    # Conditional: ask only if predicate returns True given known_slots
    when: Optional[str] = None  # named condition key resolved in gap_analyzer
    # Validation hint
    validation: Optional[str] = None
    # Human label for UI summary
    ui_label: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)


class FlowSlotSchema(BaseModel):
    flow: str
    slots: List[SlotDef]
    completion: List[str] = Field(default_factory=list)  # slots required for completion
    description: str = ""

    def slot_map(self) -> Dict[str, SlotDef]:
        return {s.name: s for s in self.slots}

    def ordered_names(self) -> List[str]:
        return [s.name for s in self.slots]
