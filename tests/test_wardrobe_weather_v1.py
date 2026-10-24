"""Looks for today's weather: a jacket when it is cold, everyday and work occasions."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from wardrobe import recommend as rec
from wardrobe.service import OutfitInput, PhotoCipher, WardrobeService

SECRET = "wardrobe-isolated-test-vault-key-secret-2026"


def item(i, category, formality="casual", seasons=(), status="available", color="blu"):
    return {"id": f"{i:032x}", "name": f"capo {i}", "category": category, "color": color,
            "formality": formality, "seasons": list(seasons), "status": status}


BASE = [item(1, "top"), item(2, "bottom", color="nero"), item(3, "shoes", color="bianco")]


def test_cold_adds_the_best_owned_jacket_to_every_look():
    wardrobe = BASE + [item(4, "outerwear", seasons=["summer"]), item(5, "outerwear", seasons=["winter"])]
    out = rec.recommend(wardrobe, "everyday", 6)
    assert out["outfits"]
    assert all(f"{5:032x}" in look["item_ids"] for look in out["outfits"])


def test_warm_or_unknown_weather_adds_no_jacket():
    wardrobe = BASE + [item(5, "outerwear", seasons=["winter"])]
    for temperature in (24, None):
        out = rec.recommend(wardrobe, "everyday", temperature)
        assert all(f"{5:032x}" not in look["item_ids"] for look in out["outfits"])


def test_cold_without_a_jacket_says_so():
    out = rec.recommend(BASE, "everyday", 4)
    assert out["outfits"] and out["layer_missing"] is True


def test_new_occasions_are_accepted_end_to_end():
    for occasion in ("everyday", "work"):
        OutfitInput(occasion=occasion)
        assert occasion in rec.OCCASIONS
    from wardrobe.stylist import OCCASION_NAME
    assert {"everyday", "work"} <= set(OCCASION_NAME)
    work = rec.recommend([item(1, "top", "smart"), item(2, "bottom", "smart"), item(3, "shoes", "formal")], "work")
    assert work["outfits"]


@pytest.mark.asyncio
async def test_outfits_read_todays_weather_when_none_is_given(monkeypatch):
    from types import SimpleNamespace
    service = WardrobeService(SimpleNamespace(wardrobe_items=None), PhotoCipher(SECRET))
    seen = {}

    async def metadata(owner):
        return BASE

    async def weather(owner):
        return {"temperature_c": 5.0, "condition": "rain", "label": "Pioggia", "place": "Milano"}

    async def advise(db, owner, items, occasion, *, temperature_c=None, note="", use_ai=True, feedback=None):
        seen.update(temperature=temperature_c, note=note)
        return rec.recommend(items, occasion, temperature_c)

    async def no_feedback(db, owner):
        return []

    monkeypatch.setattr(service, "list_metadata", metadata)
    monkeypatch.setattr(service, "_weather_now", weather)
    monkeypatch.setattr("wardrobe.stylist.advise", advise)
    monkeypatch.setattr("wardrobe.preferences.load_feedback", no_feedback)
    out = await service.outfits("u1", OutfitInput(occasion="everyday"))
    assert seen["temperature"] == 5.0 and "piove" in seen["note"]
    assert out["weather"]["place"] == "Milano" and out["layer_missing"] is True

    seen.clear()
    out = await service.outfits("u1", OutfitInput(occasion="everyday", temperature_c=22))
    assert seen["temperature"] == 22 and "weather" not in out
