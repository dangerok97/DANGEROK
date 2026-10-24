"""The kitchen in conversation: same tools for the app chat, WhatsApp and Siri.

"Salva questa ricetta <link>", "cosa cucino stasera?", "aggiungi il latte alla
spesa". Saving to the person's own recipe book and shopping list is reversible
and theirs; nothing is bought, sent or shared.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Any

from conversation_engine.ai_core.models import Observation

UI = [{"kind": "ora_screen", "path": "/cucina", "label": "Apri Cucina in ORA"}]


def _obs(name: str, status: str, payload: dict) -> Observation:
    return Observation(kind="tool", name=name, status=status,
                       payload={**payload, "grounding": "PERSONAL_CONTEXT", "memory_eligible": False})


def _owner(runtime):
    owner = str(runtime.get("user_id") or "")
    return owner, runtime.get("db")


async def save_recipe(arguments: dict[str, Any], runtime: dict[str, Any]) -> Observation:
    from .importer import allow, from_link, from_text
    from .parser import URL_PATTERN
    from .service import RecipeError, RecipeService, RecipeWrite

    name = "save_recipe"
    owner, db = _owner(runtime)
    if not owner or db is None:
        return _obs(name, "error", {"status": "NOT_AUTHENTICATED"})
    source = str(arguments.get("source") or "").strip()[:12000]
    if not source:
        return _obs(name, "partial", {"status": "MISSING_SOURCE", "reason": "Serve il link o il testo della ricetta."})
    if not allow(owner):
        return _obs(name, "partial", {"status": "RATE_LIMITED", "reason": "Troppe importazioni nell'ultima ora."})
    try:
        found = await (from_link(source) if URL_PATTERN.fullmatch(source) else from_text(source))
        draft = found["draft"]
        if not draft.get("source_url") and not draft.get("source_text"):
            draft["source_text"] = source
        item, created = await RecipeService(db).create(owner, RecipeWrite(**{**draft, "revision": 0}))
    except (RecipeError, ValueError) as exc:
        return _obs(name, "partial", {"status": "NOT_SAVED", "reason": str(exc)[:200]})
    return _obs(name, "ok", {
        "status": "saved" if created else "already_saved",
        "title": item["title"], "ingredients": len(item["ingredients"]), "steps": len(item["steps"]),
        "quality": found.get("quality"), "notes": list(found.get("warnings") or [])[:3],
        "ui_actions": UI,
    })


async def read_recipes(arguments: dict[str, Any], runtime: dict[str, Any]) -> Observation:
    from .service import RecipeService

    name = "read_my_recipes"
    owner, db = _owner(runtime)
    if not owner or db is None:
        return _obs(name, "error", {"status": "NOT_AUTHENTICATED"})
    items = await RecipeService(db).list(owner)
    if not items:
        return _obs(name, "partial", {"status": "NO_RECIPES",
                                      "reason": "Nel ricettario non ci sono ancora ricette salvate.",
                                      "ui_actions": UI})
    query = str(arguments.get("query") or "").casefold().strip()
    picked = [r for r in items if not query or query in (r["title"] + " " + " ".join(r.get("tags") or [])
                                                         + " " + " ".join(r.get("ingredients") or [])).casefold()]
    picked = picked or items
    return _obs(name, "ok", {
        "status": "ok", "count": len(items),
        "recipes": [{
            "title": r["title"], "tags": r.get("tags") or [], "minutes": r.get("total_minutes"),
            "servings": r.get("servings"), "favorite": r.get("favorite", False),
            "cooked_before": r.get("status") == "cooked",
            "ingredients": (r.get("ingredients") or [])[:25],
        } for r in picked[:30]],
        "ui_actions": UI,
    })


def _monday(today: date) -> str:
    return (today - timedelta(days=today.weekday())).isoformat()


async def add_to_shopping_list(arguments: dict[str, Any], runtime: dict[str, Any]) -> Observation:
    name = "add_to_shopping_list"
    owner, db = _owner(runtime)
    if not owner or db is None:
        return _obs(name, "error", {"status": "NOT_AUTHENTICATED"})
    raw = arguments.get("items") or []
    items = [str(x).strip()[:180] for x in (raw if isinstance(raw, list) else [raw]) if str(x).strip()][:30]
    if not items:
        return _obs(name, "partial", {"status": "MISSING_ITEMS", "reason": "Dimmi cosa aggiungere."})
    from cooking_planner.router import _category

    week = _monday(datetime.now(timezone.utc).date())
    key = {"_id": f"{owner}:{week}", "user_id": owner, "week_start": week}
    doc = await db.ora_shopping_lists.find_one({"user_id": owner, "week_start": week}) or {
        **key, "manual_items": [], "checked": {}}
    present = {str(i.get("name", "")).casefold() for i in doc.get("manual_items", [])}
    added = []
    for item in items:
        if item.casefold() in present:
            continue
        iid = hashlib.sha256(f"{owner}|{week}|manual|{item.casefold()}".encode()).hexdigest()[:32]
        doc.setdefault("manual_items", []).append(
            {"id": iid, "name": item, "category": _category(item), "quantity": "", "checked": False})
        present.add(item.casefold())
        added.append(item)
    await db.ora_shopping_lists.replace_one({"_id": doc["_id"], "user_id": owner}, doc, upsert=True)
    return _obs(name, "ok", {"status": "ok", "added": added,
                             "already_there": [i for i in items if i not in added], "week_start": week,
                             "ui_actions": [{"kind": "ora_screen", "path": "/cucina-piano",
                                             "label": "Apri la lista della spesa"}]})
