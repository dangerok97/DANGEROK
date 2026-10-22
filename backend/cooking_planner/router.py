"""Owner-scoped weekly meal plans and generated shopping lists for ORA Cucina.

Ingredient quantities are deliberately preserved as written. The service does not
guess unit conversions or merge ambiguous quantities; users can tick items while
shopping, and checked state is retained when the same ingredient key remains.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from deps import db, get_current_user

router = APIRouter(prefix="/cooking", tags=["cooking"])


def no_cache(response: Response):
    response.headers["Cache-Control"] = "private, no-store"


router.dependencies.append(Depends(no_cache))


class MealSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: int = Field(ge=0, le=6)
    meal: Literal["breakfast", "lunch", "dinner"]
    recipe_id: str = Field(min_length=32, max_length=32, pattern=r"^[a-f0-9]{32}$")
    servings: int = Field(default=2, ge=1, le=30)


class PlanWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week_start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    revision: int = Field(default=0, ge=0)
    household_size: int = Field(default=2, ge=1, le=30)
    budget_eur: float | None = Field(default=None, ge=0, le=100000)
    preferences: list[str] = Field(default_factory=list, max_length=30)
    slots: list[MealSlot] = Field(default_factory=list, max_length=21)

    @field_validator("week_start")
    @classmethod
    def valid_date(cls, value: str):
        from datetime import date
        parsed = date.fromisoformat(value)
        if parsed.weekday() != 0:
            raise ValueError("week_start deve essere il lunedì.")
        return value

    @field_validator("preferences")
    @classmethod
    def clean_preferences(cls, values):
        result = list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if any(len(v) > 80 for v in result):
            raise ValueError("Preferenza troppo lunga.")
        return result


class TickWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checked: bool


class ShoppingItemWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=180)
    category: str = Field(default="Altro", max_length=50)
    quantity: str = Field(default="", max_length=100)


def _plan_public(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in ("_id", "user_id")}


def _item_id(owner: str, week: str, recipe_id: str, index: int, line: str) -> str:
    seed = f"{owner}|{week}|{recipe_id}|{index}|{line.casefold().strip()}"
    return hashlib.sha256(seed.encode()).hexdigest()[:32]


def _category(line: str) -> str:
    s = line.casefold()
    rules = [
        ("Frutta e verdura", ("pomodor", "zucchin", "carot", "cipoll", "aglio", "patat", "insalat", "limon", "mela", "banana", "verdura", "spinac")),
        ("Carne e pesce", ("pollo", "manzo", "maiale", "tacchin", "salmone", "tonno", "pesce", "gamber", "prosciutto")),
        ("Latticini e uova", ("latte", "burro", "uova", "uovo", "formaggio", "parmigiano", "mozzarella", "panna", "yogurt", "ricotta")),
        ("Pasta, riso e cereali", ("pasta", "riso", "farina", "pane", "cous cous", "orzo", "avena", "spaghetti", "penne")),
        ("Dispensa e condimenti", ("olio", "sale", "pepe", "zucchero", "aceto", "passata", "pelati", "brodo", "spezie")),
    ]
    for category, words in rules:
        if any(word in s for word in words):
            return category
    return "Altro"


async def _get_plan(owner: str, week: str):
    return await db.ora_meal_plans.find_one({"user_id": owner, "week_start": week})


@router.get("/plan")
async def get_plan(week_start: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"), user=Depends(get_current_user)):
    doc = await _get_plan(user["user_id"], week_start)
    return {"plan": _plan_public(doc) if doc else None}


@router.put("/plan")
async def put_plan(body: PlanWrite, user=Depends(get_current_user)):
    owner = user["user_id"]
    # Every recipe reference must belong to this user.
    recipe_ids = list({slot.recipe_id for slot in body.slots})
    if recipe_ids:
        found = await db.ora_recipes.find({"user_id": owner, "id": {"$in": recipe_ids}}).to_list(length=250)
        owned = {r["id"] for r in found}
        missing = sorted(set(recipe_ids) - owned)
        if missing:
            raise HTTPException(422, detail={"message": "Una o più ricette non appartengono al tuo archivio.", "missing_recipe_ids": missing})
    old = await _get_plan(owner, body.week_start)
    revision = old.get("revision", 0) if old else 0
    if revision != body.revision:
        raise HTTPException(409, "Piano modificato altrove. Ricarica prima di salvare.")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": f"{owner}:{body.week_start}", "user_id": owner,
        "week_start": body.week_start, "revision": revision + 1,
        "household_size": body.household_size, "budget_eur": body.budget_eur,
        "preferences": body.preferences,
        "slots": [slot.model_dump() for slot in body.slots],
        "created_at": old.get("created_at", now) if old else now, "updated_at": now,
    }
    if old:
        result = await db.ora_meal_plans.replace_one({"_id": doc["_id"], "user_id": owner, "revision": revision}, doc)
        if result.modified_count != 1:
            raise HTTPException(409, "Piano modificato nel frattempo. Ricarica prima di salvare.")
    else:
        await db.ora_meal_plans.insert_one(doc)
    return {"plan": _plan_public(doc)}


@router.get("/shopping-list")
async def get_shopping_list(week_start: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"), user=Depends(get_current_user)):
    owner = user["user_id"]
    plan = await _get_plan(owner, week_start)
    if not plan:
        return {"week_start": week_start, "items": [], "message": "Aggiungi le ricette al piano settimanale per generare la lista."}
    recipe_ids = list({slot["recipe_id"] for slot in plan["slots"]})
    recipes = await db.ora_recipes.find({"user_id": owner, "id": {"$in": recipe_ids}}).to_list(length=250)
    by_id = {r["id"]: r for r in recipes}
    existing = await db.ora_shopping_lists.find_one({"user_id": owner, "week_start": week_start})
    checked = {item["id"]: item.get("checked", False) for item in (existing or {}).get("items", [])}
    items = []
    for slot in plan["slots"]:
        recipe = by_id.get(slot["recipe_id"])
        if not recipe:
            continue
        for index, line in enumerate(recipe.get("ingredients", [])):
            iid = _item_id(owner, week_start, recipe["id"], index, line)
            items.append({
                "id": iid, "name": line, "category": _category(line),
                "recipe_id": recipe["id"], "recipe_title": recipe["title"],
                "servings": slot.get("servings", plan.get("household_size", 2)),
                "checked": checked.get(iid, False), "kind": "recipe",
            })
    manual = (existing or {}).get("manual_items", [])
    items.extend({**item, "kind": "manual", "recipe_id": None, "recipe_title": None,
                  "servings": None, "checked": item.get("checked", False)} for item in manual)
    items.sort(key=lambda item: (item["checked"], item["category"].casefold(), item["name"].casefold()))
    return {"week_start": week_start, "plan_revision": plan["revision"], "items": items,
            "note": "Le quantità sono riportate come scritte nelle ricette: ORA non somma unità ambigue né sottrae scorte non registrate."}


@router.put("/shopping-list/{item_id}")
async def tick_shopping_item(item_id: str, body: TickWrite, week_start: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"), user=Depends(get_current_user)):
    owner = user["user_id"]
    if not re.fullmatch(r"[a-f0-9]{32}", item_id):
        raise HTTPException(422, "Identificativo articolo non valido.")
    plan = await _get_plan(owner, week_start)
    if not plan:
        raise HTTPException(404, "Piano settimanale non trovato.")
    current = await get_shopping_list(week_start, user)
    if not any(item["id"] == item_id for item in current["items"]):
        raise HTTPException(404, "Articolo non trovato nella lista.")
    col = db.ora_shopping_lists
    doc = await col.find_one({"user_id": owner, "week_start": week_start}) or {
        "_id": f"{owner}:{week_start}", "user_id": owner, "week_start": week_start, "manual_items": [], "checked": {}
    }
    doc.setdefault("checked", {})[item_id] = body.checked
    # Preserve only per-item checked overrides; the list itself is always regenerated from the plan.
    doc["items"] = [{"id": key, "checked": value} for key, value in doc["checked"].items()]
    await col.replace_one({"_id": doc["_id"], "user_id": owner}, doc, upsert=True)
    return {"id": item_id, "checked": body.checked}


@router.post("/shopping-list/manual")
async def add_manual_item(body: ShoppingItemWrite, week_start: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"), user=Depends(get_current_user)):
    owner = user["user_id"]
    doc = await db.ora_shopping_lists.find_one({"user_id": owner, "week_start": week_start}) or {
        "_id": f"{owner}:{week_start}", "user_id": owner, "week_start": week_start, "manual_items": [], "checked": {}
    }
    item_id = hashlib.sha256(f"{owner}|{week_start}|manual|{body.name.casefold()}|{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:32]
    doc.setdefault("manual_items", []).append({"id": item_id, **body.model_dump(), "checked": False})
    await db.ora_shopping_lists.replace_one({"_id": doc["_id"], "user_id": owner}, doc, upsert=True)
    return {"item": doc["manual_items"][-1]}
