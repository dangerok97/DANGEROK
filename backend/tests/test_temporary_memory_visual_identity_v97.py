"""V97 — every temporary Situation has a semantic visual identity and creation explanation."""

from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

from situations.models import SituationUpdate
from situations.service import SituationService


ROOT = Path(__file__).resolve().parents[1]


def test_prompt_requires_visual_identity_and_tracking_copy_without_domain_router():
    prompt = (
        ROOT / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")

    assert "For every create, semantic_kind MUST be a short human display label" in prompt
    assert "For every create, icon_key MUST be set" in prompt
    assert "For every create, tracking_summary MUST also be set" in prompt
    assert "Choose the icon by the MEANING of the Situation" in prompt
    assert "frontend keyword router" in prompt
    assert "shirt" in prompt
    assert "medicine" in prompt
    assert "shopping" in prompt
    assert "payment" in prompt
    assert "laundry" not in prompt.lower()
    assert "panni" not in prompt.lower()


@pytest.mark.asyncio
async def test_situation_persists_tracking_summary_and_safe_visual_fallback():
    db = AsyncMongoMockClient().test
    service = SituationService(db)

    created = await service.apply(
        user_id="visual-user",
        session_id="ces_visual",
        reasoning_epoch="visual-1",
        update=SituationUpdate(
            operation="create",
            summary="C'è una situazione temporanea da seguire.",
            semantic_kind="Controllo temporaneo",
            tracking_summary="ORA terrà questa situazione in vista finché resta attiva.",
            source_refs=["user_conversation"],
        ),
    )

    assert created["status"] == "success"
    assert created["situation"]["icon_key"] == "other"
    assert created["situation"]["tracking_summary"] == (
        "ORA terrà questa situazione in vista finché resta attiva."
    )

    stored = await db.situations.find_one({"id": created["situation"]["id"]}, {"_id": 0})
    assert stored["icon_key"] == "other"
    assert stored["tracking_summary"].startswith("ORA terrà")


def test_frontend_fallback_is_not_a_lightning_bolt():
    visual = (
        ROOT.parent
        / "frontend"
        / "src"
        / "components"
        / "ora"
        / "situationVisual.ts"
    ).read_text(encoding="utf-8")

    assert "flash-outline" not in visual
    assert "shirt-outline" in visual
    assert "bookmark-outline" in visual
