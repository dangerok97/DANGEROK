from cooking_planner.router import MealSlot, PlanWrite, _category, _item_id


def test_plan_requires_monday():
    try:
        PlanWrite(week_start="2026-10-22")
    except Exception as exc:
        assert "lunedì" in str(exc)
    else:
        raise AssertionError("Thursday must not be accepted as week start")


def test_plan_slot_references_recipe_and_limits_servings():
    slot = MealSlot(day=0, meal="dinner", recipe_id="a" * 32, servings=4)
    assert slot.day == 0
    assert slot.servings == 4


def test_category_is_italian_and_conservative():
    assert _category("200 g di mozzarella") == "Latticini e uova"
    assert _category("2 zucchine") == "Frutta e verdura"
    assert _category("una manciata di ingredienti speciali") == "Altro"


def test_shopping_item_id_is_stable_for_same_source_line():
    a = _item_id("owner", "2026-10-19", "a" * 32, 0, "200 g di pasta")
    b = _item_id("owner", "2026-10-19", "a" * 32, 0, "200 g di pasta")
    c = _item_id("other", "2026-10-19", "a" * 32, 0, "200 g di pasta")
    assert a == b
    assert a != c


def test_plan_accepts_monday_and_deduplicates_preferences():
    plan = PlanWrite(week_start="2026-10-19", preferences=["Italiana", "Italiana", "Rapida"])
    assert plan.preferences == ["Italiana", "Rapida"]
