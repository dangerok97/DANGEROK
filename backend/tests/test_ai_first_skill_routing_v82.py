"""V82: conversation belongs to AI; code exposes skills and validates effects."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_cognitive_prompt_declares_ai_first_skill_routing():
    from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT

    prompt = COGNITIVE_SYSTEM_PROMPT.lower()
    assert "ai owns the conversation" in prompt
    assert "ora's available skills" in prompt
    assert "must not require magic phrases" in prompt
    assert "active_skill_state" in prompt


def test_pre_model_phone_and_navigation_fast_path_responses_are_gone():
    source = (ROOT / "conversation_engine" / "ai_core" / "loop.py").read_text(
        encoding="utf-8"
    )
    # These were terminal pre-model dialogue branches: they answered the user
    # before the cognitive model could interpret the turn.
    assert 'event="PHONE_FOLLOWUP_FAST_PATH"' not in source
    assert 'event="NAVIGATION_FAST_PATH"' not in source
    assert 'event="NAVIGATION_CONFIRM_FAST_PATH"' not in source
    assert 'event="NAVIGATION_CANCEL_FAST_PATH"' not in source


@pytest.mark.asyncio
async def test_relationship_language_is_not_parsed_as_phone_state_machine(db=None):
    from conversation_engine.ai_core.loop import _phone_pending_followup

    class Collection:
        async def find_one(self, *args, **kwargs):
            return {
                "preparation_id": "prep_1",
                "owner_id": "owner",
                "counterparty": "la mia ragazza",
                "operation": "deliver_message",
                "selected_contact": {
                    "name": "la mia ragazza",
                    "number": "+393277631311",
                    "kind": "person",
                    "source": "user",
                    "confidence": 1.0,
                    "why": "Me l'hai detto tu.",
                    "contact_identity": "la mia ragazza",
                },
                "contact_candidates": [],
                "number_source": "user",
                "contact_identity": "la mia ragazza",
                "identity_conflicts": [
                    {"identity": "asia", "name": "Asia", "source": "user"}
                ],
            }

    class DB:
        def __getitem__(self, name):
            return Collection()

    # The mechanical helper must leave semantic relationship language to AI.
    assert await _phone_pending_followup(
        DB(),
        "owner",
        {"active_preparation_id": "prep_1"},
        "è giusto perché la mia ragazza si chiama Asia",
    ) == {}


@pytest.mark.asyncio
async def test_navigation_continuation_is_a_skill_with_execution_guard():
    from places.caps import continue_navigation

    pending = {
        "created_at": "2026-10-05T17:28:00+00:00",
        "options": [{
            "id": "google_maps",
            "label": "Google Maps",
            "url": "https://www.google.com/maps/dir/?api=1&destination=Roma",
        }],
    }

    # Patch module clock by using a freshly-created timestamp would make the
    # test date-sensitive. Here we verify the guard itself with an invalid
    # utterance before freshness matters.
    rejected = await continue_navigation(
        {},
        {
            "user_id": "owner",
            "user_message": "parliamo d'altro",
            "pending_navigation": pending,
        },
    )
    assert rejected.status == "error"
    assert rejected.payload["error"] == "USER_CONFIRMATION_REQUIRED"


def test_registry_exposes_navigation_continuation_as_skill():
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    tools = {row["capability"] for row in ToolRegistry(db=None).list_public()}
    assert "open_navigation" in tools
    assert "continue_navigation" in tools
