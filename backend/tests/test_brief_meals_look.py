"""8/11: the morning brief says what is planned at the table and what to wear."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from test_phone_identity_conflict import db  # noqa: F401  (fixture)
from brief.morning import _look, _meals

ROME = ZoneInfo("Europe/Rome")
SUNDAY = datetime(2026, 11, 8, 8, 0, tzinfo=ROME)


@pytest.mark.asyncio
async def test_today_meals_come_from_the_plan(db):  # noqa: F811
    for row in ({"user_id": "o", "id": "r1", "title": "Carbonara", "total_minutes": 25},
                {"user_id": "o", "id": "r2", "title": "Cacio e pepe"},
                {"user_id": "x", "id": "r3", "title": "Di un altro"}):
        await db.ora_recipes.insert_one(row)
    await db.ora_meal_plans.insert_one({"_id": "o:2026-11-02", "user_id": "o", "week_start": "2026-11-02", "slots": [
        {"day": 6, "meal": "dinner", "recipe_id": "r1", "servings": 2},
        {"day": 6, "meal": "lunch", "recipe_id": "r2", "servings": 2},
        {"day": 6, "meal": "breakfast", "recipe_id": "r3", "servings": 2},
        {"day": 0, "meal": "dinner", "recipe_id": "r2", "servings": 2},
    ]})
    assert await _meals(db, "o", SUNDAY) == ["Pranzo: Cacio e pepe", "Cena: Carbonara (25 min)"]
    assert await _meals(db, "nessuno", SUNDAY) == []


@pytest.mark.asyncio
async def test_a_look_for_the_weather_from_owned_clothes(db):  # noqa: F811
    def g(i, name, cat, color, form="casual", seasons=("fall", "winter"), status="available"):
        return {"user_id": "o", "id": i, "name": name, "category": cat, "color": color, "formality": form,
                "seasons": list(seasons), "status": status}
    for row in (g("a", "Maglione blu", "top", "blu"), g("b", "Jeans", "bottom", "blu"),
                g("c", "Sneakers bianche", "shoes", "bianco"), g("d", "Giacca di lana", "outerwear", "marrone"),
                g("e", "Felpa nera", "top", "nero", status="laundry")):
        await db.wardrobe_items.insert_one(row)
    lines = await _look(db, "o", {"today": {"min_c": 9, "max_c": 15}})
    assert lines and "Giacca di lana".casefold() in lines[0].casefold()
    assert "Felpa" not in lines[0]
    assert await _look(db, "o", None) == []
