"""Owner-isolated, optimistic-locking recipe library for ORA Cucina."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pymongo.errors import DuplicateKeyError

from .parser import canonical_url, source_fingerprint

MAX_RECIPES = 250
ID_RE = re.compile(r"^[a-f0-9]{32}$")


class RecipeError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class SourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=12000)


class RecipeWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    revision: int = Field(default=0, ge=0)
    title: str = Field(min_length=1, max_length=140)
    source_url: str = Field(default="", max_length=2048)
    source_text: str = Field(default="", max_length=12000)
    ingredients: list[str] = Field(default_factory=list, max_length=60)
    steps: list[str] = Field(default_factory=list, max_length=40)
    tags: list[str] = Field(default_factory=list, max_length=12)
    servings: int | None = Field(default=None, ge=1, le=99)
    favorite: bool = False
    status: Literal["to_try", "cooked"] = "to_try"

    @field_validator("ingredients", "steps", "tags")
    @classmethod
    def clean_list(cls, value: list[str], info):
        cap = {"ingredients": 250, "steps": 800, "tags": 40}[info.field_name]
        result = [item.strip() for item in value]
        if any(not item or len(item) > cap or any(ord(c) < 32 and c not in "\t" for c in item)
               for item in result):
            raise ValueError("Riga vuota o troppo lunga nella ricetta.")
        return result

    @model_validator(mode="after")
    def validate_recipe(self):
        if any(ord(c) < 32 for c in self.title):
            raise ValueError("Il titolo contiene caratteri non validi.")
        if self.source_url:
            self.source_url = canonical_url(self.source_url)
        if not self.source_url and not self.source_text.strip():
            raise ValueError("Conserva la fonte: incolla un testo o un link.")
        self.tags = list(dict.fromkeys(self.tags))
        return self


def _public(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in ("_id", "user_id", "source_key")}


class RecipeService:
    def __init__(self, db):
        self.col = db.ora_recipes

    @staticmethod
    def record_id(owner: str, body: RecipeWrite) -> str:
        source_key = source_fingerprint(body.source_url, body.source_text)
        return hashlib.sha256((owner + ":recipes:" + source_key).encode("utf-8")).hexdigest()[:32]

    async def list(self, owner: str) -> list[dict]:
        docs = await self.col.find({"user_id": owner}).sort("updated_at", -1).limit(MAX_RECIPES).to_list(length=MAX_RECIPES)
        return [_public(doc) for doc in docs]

    async def create(self, owner: str, body: RecipeWrite) -> tuple[dict, bool]:
        if body.revision != 0:
            raise RecipeError("Una nuova ricetta deve partire dalla revisione zero.", 422)
        recipe_id = self.record_id(owner, body)
        mongo_id = owner + ":" + recipe_id
        old = await self.col.find_one({"_id": mongo_id, "user_id": owner})
        if old:
            return _public(old), False
        if await self.col.count_documents({"user_id": owner}) >= MAX_RECIPES:
            raise RecipeError("Limite di 250 ricette raggiunto.", 409)
        now = datetime.now(timezone.utc).isoformat()
        record = {"_id": mongo_id, "user_id": owner, "id": recipe_id,
                  "source_key": source_fingerprint(body.source_url, body.source_text),
                  **body.model_dump(exclude={"revision"}),
                  "revision": 1, "created_at": now, "updated_at": now}
        try:
            await self.col.insert_one(record)
        except DuplicateKeyError:
            old = await self.col.find_one({"_id": mongo_id, "user_id": owner})
            if old:
                return _public(old), False
            raise
        return _public(record), True

    async def update(self, owner: str, recipe_id: str, body: RecipeWrite) -> dict:
        if not ID_RE.fullmatch(recipe_id) or body.revision < 1:
            raise RecipeError("Identificativo o revisione non validi.", 422)
        mongo_id = owner + ":" + recipe_id
        old = await self.col.find_one({"_id": mongo_id, "user_id": owner})
        if not old:
            raise RecipeError("Ricetta non trovata.", 404)
        if old["revision"] != body.revision:
            raise RecipeError("Questa ricetta è stata modificata altrove. Ricarica la lista.", 409)
        update = {**body.model_dump(exclude={"revision"}), "revision": body.revision + 1,
                  "updated_at": datetime.now(timezone.utc).isoformat()}
        result = await self.col.update_one({"_id": mongo_id, "user_id": owner,
                                            "revision": body.revision}, {"$set": update})
        if result.matched_count != 1:
            raise RecipeError("Ricetta modificata nel frattempo. Ricarica la lista.", 409)
        return _public({**old, **update})

    async def delete(self, owner: str, recipe_id: str, revision: int) -> None:
        if not ID_RE.fullmatch(recipe_id) or revision < 1:
            raise RecipeError("Identificativo o revisione non validi.", 422)
        result = await self.col.delete_one({"_id": owner + ":" + recipe_id,
                                            "user_id": owner, "revision": revision})
        if result.deleted_count != 1:
            raise RecipeError("Ricetta non trovata o già modificata. Ricarica la lista.", 409)
