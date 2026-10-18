"""Wardrobe pilot: real FastAPI contract, in-memory Mongo substitute, real AES/Pillow.

Never substitute a fabricated AI answer for tested wardrobe ownership.
"""
import importlib
import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from wardrobe.recommend import recommend
from wardrobe.service import (GarmentInput, PhotoCipher, WardrobeError, WardrobeService,
                              make_thumbnail, MAX_UPLOAD)

SECRET = "wardrobe-isolated-test-vault-key-secret-2026"


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length):
        return [dict(d) for d in self.docs[:length]]


class Collection:
    def __init__(self):
        self.docs = {}

    @staticmethod
    def match(doc, query):
        return all(doc.get(k) == v for k, v in query.items())

    async def find_one(self, query):
        return next((dict(d) for d in self.docs.values() if self.match(d, query)), None)

    def find(self, query):
        return Cursor([d for d in self.docs.values() if self.match(d, query)])

    async def count_documents(self, query):
        return len([d for d in self.docs.values() if self.match(d, query)])

    async def insert_one(self, record):
        assert record["_id"] not in self.docs
        self.docs[record["_id"]] = dict(record)
        return SimpleNamespace(inserted_id=record["_id"])

    async def update_one(self, query, update):
        for k, v in self.docs.items():
            if self.match(v, query):
                self.docs[k] = {**v, **update["$set"]}
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    async def delete_one(self, query):
        for k, v in list(self.docs.items()):
            if self.match(v, query):
                del self.docs[k]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class FakeDB:
    def __init__(self):
        self.wardrobe_items = Collection()


def item(item_id: str, category="top", formality="smart", color="blu", revision=0,
         status="available"):
    return {"id": item_id * 32, "name": f"Capo {category}", "category": category,
            "formality": formality, "color": color, "revision": revision,
            "status": status, "seasons": []}


@pytest.fixture
def wardrobe_http(monkeypatch):
    db = FakeDB()
    dependency = ModuleType("deps")

    async def auth(authorization: str | None = Header(None)):
        if authorization not in ("Bearer alice", "Bearer bob"):
            raise HTTPException(401, "Accesso richiesto")
        return {"user_id": authorization.removeprefix("Bearer ")}

    dependency.db = db
    dependency.get_current_user = auth
    monkeypatch.setitem(sys.modules, "deps", dependency)
    monkeypatch.setenv("TOKEN_VAULT_KEY", SECRET)
    spec = importlib.util.spec_from_file_location(
        "wardrobe_http_fixture", Path(__file__).resolve().parents[1] / "backend/wardrobe/router.py"
    )
    # router has a relative import, so resolve it as a member of the package.
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "wardrobe"
    spec.loader.exec_module(module)
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    with TestClient(app) as client:
        yield client, db


def headers(owner="alice"):
    return {"Authorization": f"Bearer {owner}"}


def image_bytes():
    buffer = io.BytesIO()
    pic = Image.new("RGB", (80, 80), (41, 72, 112))
    pic.save(buffer, "PNG", pnginfo=None)
    return buffer.getvalue()


def test_owner_auth_crud_revision_and_no_store(wardrobe_http):
    client, db = wardrobe_http
    base = "/api/wardrobe"
    assert client.get(base + "/items").status_code == 401
    assert client.put(base + "/items", json=item("a")).status_code == 401
    assert client.post(base + "/outfits", json={"occasion": "running"}).status_code == 401
    saved = client.put(base + "/items", headers=headers(), json=item("a"))
    assert saved.status_code == 200, saved.text
    assert saved.headers["cache-control"] == "private, no-store"
    assert saved.json()["item"]["revision"] == 1
    assert client.get(base + "/items", headers=headers("bob")).json()["items"] == []
    assert client.put(base + "/items", headers=headers(), json=item("a")).status_code == 409
    assert client.delete(base + "/items/" + "a" * 32 + "?revision=1", headers=headers("bob")).status_code == 404
    changed = item("a", revision=1, color="nero")
    assert client.put(base + "/items", headers=headers(), json=changed).json()["item"]["revision"] == 2
    assert client.delete(base + "/items/" + "a" * 32 + "?revision=1", headers=headers()).status_code == 409
    assert client.delete(base + "/items/" + "a" * 32 + "?revision=2", headers=headers()).json()["deleted"]
    assert db.wardrobe_items.docs == {}


def test_photos_are_small_encrypted_owner_bound_and_not_logged(wardrobe_http):
    client, db = wardrobe_http
    base = "/api/wardrobe"
    assert client.put(base + "/items", headers=headers(), json=item("b")).status_code == 200
    payload = image_bytes()
    bad = client.post(base + "/items/" + "b" * 32 + "/photo?revision=1",
                      headers={**headers(), "Content-Type": "image/svg+xml"}, content=b"<svg/>")
    assert bad.status_code == 415
    bad = client.post(base + "/items/" + "b" * 32 + "/photo?revision=1",
                      headers={**headers(), "Content-Type": "image/png"}, content=b"x" * (MAX_UPLOAD + 1))
    assert bad.status_code == 413
    photo_url = base + "/items/" + "b" * 32 + "/photo?revision=1"
    assert client.post(photo_url, headers={**headers("bob"), "Content-Type": "image/png"}, content=payload).status_code == 404
    stored = client.post(photo_url, headers={**headers(), "Content-Type": "image/png"}, content=payload)
    assert stored.status_code == 200, stored.text
    doc = db.wardrobe_items.docs["alice:" + "b" * 32]
    assert "photo_encrypted" in doc
    assert "data:image" not in repr(doc)
    assert payload not in repr(doc).encode()
    served = client.get(base + "/items", headers=headers()).json()["items"][0]
    assert served["photo"].startswith("data:image/jpeg;base64,")
    assert "photo_encrypted" not in served
    assert client.get(base + "/items", headers=headers("bob")).json()["items"] == []
    assert client.post(photo_url, headers={**headers(), "Content-Type": "image/png"}, content=payload).status_code == 409
    with pytest.raises(WardrobeError):
        PhotoCipher(SECRET).decrypt("bob", "b" * 32, doc["photo_encrypted"])
    thumb = make_thumbnail(payload)
    with Image.open(io.BytesIO(thumb)) as pic:
        assert pic.width == 80 and pic.format == "JPEG"
        assert not pic.info.get("exif")


def test_recommendation_never_invents_missing_items_and_filters_laundry(wardrobe_http):
    client, _ = wardrobe_http
    base = "/api/wardrobe"
    for code, cat, status in (("c", "top", "available"), ("d", "bottom", "available"), ("e", "shoes", "laundry")):
        assert client.put(base + "/items", headers=headers(), json=item(code, cat, status=status)).status_code == 200
    result = client.post(base + "/outfits", headers=headers(), json={"occasion": "chic_evening"})
    assert result.status_code == 200
    assert result.json()["outfits"] == [] and result.json()["missing"] == ["shoes"]
    assert client.put(base + "/items", headers=headers(), json=item("e", "shoes", revision=1)).status_code == 200
    finished = client.post(base + "/outfits", headers=headers(), json={"occasion": "chic_evening"}).json()
    assert finished["engine"] == "rules-v1"
    assert len(finished["outfits"]) == 1
    assert set(finished["outfits"][0]["item_ids"]) == {x * 32 for x in ("c", "d", "e")}
    assert client.post(base + "/outfits", headers=headers("bob"), json={"occasion": "chic_evening"}).json()["outfits"] == []
    assert client.post(base + "/outfits", headers=headers(), json={"occasion": "running"}).json()["missing"] == ["top", "bottom", "shoes"]


def test_validation_and_photo_bomb_limits():
    with pytest.raises(ValueError):
        GarmentInput(**{**item("a"), "name": "  "})
    with pytest.raises(ValueError):
        GarmentInput(**{**item("a"), "irrelevant_password": "oops"})
    with pytest.raises(WardrobeError):
        make_thumbnail(b"not really a photo")
    data = [
        {**item("a", "top"), "status": "laundry"},
        item("b", "bottom"), item("c", "shoes"),
    ]
    assert recommend(data, "chic_evening")["outfits"] == []
