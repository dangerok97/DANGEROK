"""V2.4.3 — generic revealable-card contract (schema + API normalize)."""
from __future__ import annotations

import pytest

from life_os.generative_models import GenerativeObject
from life_os.generative_schema import (
    GenerativeValidationError,
    normalize_content_blocks_for_display,
    normalize_reveal_card_item,
    validate_generative_spec,
)


def test_normalize_title_only_card_becomes_static_front():
    """Live QA shape: title set, empty front/back → front=title, not revealable."""
    card = normalize_reveal_card_item(
        {
            "type": "card",
            "title": "Esempio pratico: La spesa al supermercato",
            "front": "",
            "back": "",
        }
    )
    assert card["front"] == "Esempio pratico: La spesa al supermercato"
    assert card["back"] == ""
    assert card["revealable"] is False


def test_normalize_compat_aliases_question_answer():
    card = normalize_reveal_card_item({"question": "Q?", "answer": "A!"})
    assert card["front"] == "Q?"
    assert card["back"] == "A!"
    assert card["revealable"] is True


def test_validate_card_deck_rejects_empty_back():
    with pytest.raises(GenerativeValidationError) as ei:
        validate_generative_spec(
            {
                "title": "Deck",
                "purpose": "t",
                "content": {
                    "blocks": [
                        {
                            "type": "card_deck",
                            "items": [{"front": "Only front", "back": ""}],
                        }
                    ]
                },
            }
        )
    assert "BAD_CARD" in str(ei.value)


def test_validate_card_deck_rejects_empty_front_after_normalize():
    with pytest.raises(GenerativeValidationError):
        validate_generative_spec(
            {
                "title": "Deck",
                "purpose": "t",
                "content": {
                    "blocks": [{"type": "card_deck", "items": [{"front": "", "back": "A"}]}]
                },
            }
        )


def test_validate_card_deck_accepts_canonical_front_back():
    spec = validate_generative_spec(
        {
            "title": "Deck",
            "purpose": "t",
            "content": {
                "blocks": [
                    {
                        "type": "card_deck",
                        "items": [
                            {"front": "Front 1", "back": "Back 1"},
                            {"question": "Front 2", "reveal": "Back 2"},
                        ],
                    }
                ]
            },
        }
    )
    items = spec["content"]["blocks"][0]["items"]
    assert items[0]["front"] == "Front 1" and items[0]["back"] == "Back 1"
    assert items[1]["front"] == "Front 2" and items[1]["back"] == "Back 2"
    assert all(i["revealable"] for i in items)


def test_validate_single_card_title_only_ok_as_static():
    spec = validate_generative_spec(
        {
            "title": "Obj",
            "purpose": "t",
            "content": {
                "blocks": [
                    {
                        "type": "card",
                        "title": "Esempio pratico",
                        "front": "",
                        "back": "",
                    }
                ]
            },
        }
    )
    card = spec["content"]["blocks"][0]
    assert card["type"] == "card"
    assert card["front"] == "Esempio pratico"
    assert card["back"] == ""
    assert card["revealable"] is False
    assert "title" not in card


def test_display_normalize_live_object_shape():
    content = normalize_content_blocks_for_display(
        {
            "blocks": [
                {"type": "heading", "text": "Giorno 1"},
                {
                    "type": "card",
                    "title": "Esempio pratico: La spesa al supermercato",
                    "front": "",
                    "back": "",
                },
            ]
        }
    )
    card = content["blocks"][1]
    assert card["front"].startswith("Esempio pratico")
    assert card["revealable"] is False


def test_public_payload_normalizes_persisted_legacy_card():
    obj = GenerativeObject(
        user_id="u1",
        title="Live",
        content={
            "blocks": [
                {
                    "type": "card",
                    "title": "Legacy title only",
                    "front": "",
                    "back": "",
                }
            ]
        },
    )
    pub = obj.public()
    card = pub["content"]["blocks"][0]
    assert card["front"] == "Legacy title only"
    assert card["revealable"] is False


def test_no_study_flashcard_branch_in_schema_module():
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "life_os" / "generative_schema.py"
    text = src.read_text(encoding="utf-8").lower()
    for banned in ("flashcard", "esame", "quiz_grade", "study_mode"):
        assert banned not in text
