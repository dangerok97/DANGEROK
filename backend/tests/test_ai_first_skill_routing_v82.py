"""V82: conversation belongs to AI; code exposes skills and validates effects."""

from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_cognitive_prompt_declares_ai_first_skill_routing():
    from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT

    prompt = COGNITIVE_SYSTEM_PROMPT.lower()
    assert "ai owns the conversation" in prompt
    assert "ora's available skills" in prompt
    assert "must not require magic phrases" in prompt
    assert "active_skill_state" in prompt


def test_phone_input_hint_contains_no_semantic_rejection_router():
    source = (ROOT / "conversation_engine" / "ai_core" / "loop.py").read_text(
        encoding="utf-8"
    )
    helper = source.split("async def _phone_input_hint", 1)[1].split(
        "def _phone_action_requested", 1
    )[0]
    assert "number_is_right" not in helper
    assert "sbagliat" not in helper
    assert "_phone_followup_fast_path" not in source


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
async def test_relationship_language_is_not_parsed_as_phone_state_machine():
    from test_post_call_application_v315 import FintoDb
    from preparation.contacts import ContactCandidate
    from preparation.preparation import MissionPreparation, remember
    from preparation.trust import identity_of
    from conversation_engine.ai_core.loop import _phone_input_hint

    db = FintoDb()
    prep = MissionPreparation(
        owner_id="owner",
        counterparty="la mia ragazza",
        operation="deliver_message",
        selected_contact=ContactCandidate(
            name="la mia ragazza",
            number="+393277631311",
            kind="person",
            source="user",
            confidence=1.0,
            why="Me l'hai detto tu.",
            contact_identity=identity_of("la mia ragazza"),
        ),
        contact_identity=identity_of("la mia ragazza"),
        identity_conflicts=[{
            "identity": identity_of("Asia"),
            "name": "Asia",
            "source": "user",
        }],
    )
    prep = await remember(db, prep)

    # The mechanical helper must leave semantic relationship language to AI.
    assert await _phone_input_hint(
        db,
        "owner",
        {"active_preparation_id": prep.preparation_id},
        "è giusto perché la mia ragazza si chiama Asia",
    ) == {}


@pytest.mark.asyncio
async def test_active_phone_skill_state_is_exposed_to_ai():
    from test_post_call_application_v315 import FintoDb
    from preparation.contacts import ContactCandidate
    from preparation.preparation import MissionPreparation, remember
    from preparation.trust import identity_of
    from conversation_engine.ai_core.loop import _active_phone_skill_context

    db = FintoDb()
    prep = MissionPreparation(
        owner_id="owner",
        user_request="Chiama la mia ragazza e dille che la amo",
        counterparty="la mia ragazza",
        operation="deliver_message",
        message_to_deliver="la amo",
        selected_contact=ContactCandidate(
            name="la mia ragazza",
            number="+393277631311",
            kind="person",
            source="user",
            confidence=1.0,
            why="Me l'hai detto tu.",
            contact_identity=identity_of("la mia ragazza"),
        ),
        contact_identity=identity_of("la mia ragazza"),
        identity_conflicts=[{
            "identity": identity_of("Asia"),
            "name": "Asia",
            "source": "user",
        }],
    )
    prep = await remember(db, prep)

    state = await _active_phone_skill_context(
        db, "owner", {"active_preparation_id": prep.preparation_id}
    )

    assert state["skill"] == "phone"
    assert state["capability"] == "prepare_a_phone_call"
    assert state["preparation_id"] == prep.preparation_id
    assert state["counterparty"] == "la mia ragazza"
    assert state["identity_conflicts"] == [{"name": "Asia"}]
    assert state["contact"]["number"] == "+393277631311"
    assert "magic phrases" in state["instruction"]


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
