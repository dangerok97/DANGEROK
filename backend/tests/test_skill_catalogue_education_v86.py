"""V86: AI knows ORA has skills and knows how to navigate the catalogue."""


def test_prompt_knows_skills_exist_but_forbids_fake_results():
    from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT

    prompt = COGNITIVE_SYSTEM_PROMPT.lower()
    assert "you do have capabilities that can search" in prompt
    assert "a capability is not a result" in prompt
    assert "use the skill now" in prompt
    assert "you have no search engine" not in prompt


def test_public_skill_catalogue_exposes_semantic_tags():
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    catalogue = ToolRegistry(db=None).list_public()
    by_name = {row["capability"]: row for row in catalogue}

    assert "prepare_a_phone_call" in by_name
    assert "phone" in by_name["prepare_a_phone_call"]["tags"]

    assert "get_weather_forecast" in by_name
    assert "weather" in by_name["get_weather_forecast"]["tags"]

    assert "cancel_calendar_event" in by_name
    assert "calendar" in by_name["cancel_calendar_event"]["tags"]

    for row in catalogue:
        assert "tags" in row
        assert isinstance(row["tags"], list)


def test_tags_describe_skills_but_do_not_route_messages_in_code():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    capability = (
        root / "conversation_engine" / "ai_core" / "tools" / "capability.py"
    ).read_text(encoding="utf-8")

    assert '"tags": [str(tag)' in capability
    assert "re.match" not in capability
    assert "re.search" not in capability
