from pathlib import Path

from context_graph.models import is_recognized_ref
from places.models import Coordinates, LifePlace


ROOT = Path(__file__).resolve().parents[1]


def test_life_place_exposes_one_canonical_ref_without_coordinates():
    place = LifePlace(
        id="plc_home_1",
        user_id="alice",
        label="Casa",
        role="home",
        role_confirmed_by_user=True,
        locality="Tarquinia",
        coordinates=Coordinates(latitude=42.249, longitude=11.756),
    )

    payload = place.for_ai()

    assert payload["ref"] == "place:plc_home_1"
    assert payload["place_id"] == "plc_home_1"
    assert payload["name"] == "Casa"
    assert payload["locality"] == "Tarquinia"
    assert payload["reachable"] is True
    serialized = str(payload)
    assert "latitude" not in serialized.lower()
    assert "longitude" not in serialized.lower()
    assert "42.249" not in serialized
    assert "11.756" not in serialized


def test_place_ref_is_a_first_class_canonical_context_ref():
    assert is_recognized_ref("place:plc_home_1") is True


def test_ai_core_contract_links_situations_to_exact_resolved_place_ref():
    prompt = (
        ROOT / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")

    assert "copy the exact returned `place:<id>` ref" in prompt
    assert "situation_update.linked_object_refs" in prompt
    assert "never substitute the person's current device location" in prompt
    assert "Preserve that ref on later Situation updates" in prompt
    assert "These tools return a canonical `ref` shaped like `place:<id>`" in prompt
