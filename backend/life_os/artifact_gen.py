"""DEPRECATED (V2.4) — closed artifact types removed from AI-native path.

Use GenerativeObject + create_object / validate_generative_spec instead.
This module remains only so old imports fail clearly; do not call from AI Core.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from life_os.models import LifeOsArtifact, LifeOsPlan


ALLOWED_TYPES = frozenset()  # intentionally empty — no closed product catalog


async def generate_artifact(
    *,
    user_id: str,
    artifact_type: str,
    title: str,
    instructions: str = "",
    plan: Optional[LifeOsPlan] = None,
    plan_item_id: Optional[str] = None,
    evidence_refs: Optional[list] = None,
    content_seed: Optional[Dict[str, Any]] = None,
) -> LifeOsArtifact:
    return LifeOsArtifact(
        user_id=user_id,
        type="notes",
        title=(title or "deprecated")[:200],
        plan_id=plan.id if plan else None,
        plan_item_id=plan_item_id,
        content={
            "error": "deprecated_v24",
            "message": (
                "Closed artifact types (flashcards/quiz/concept_map/…) were removed. "
                "Use create_object with declarative UI primitives."
            ),
            "requested_type": (artifact_type or "")[:40],
        },
        status="failed",
    )
