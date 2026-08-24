"""Contextual visual pipeline — everything around the vendor call.

A stub provider stands in for the real one so the mechanics that cost money can
be proven for free: that the same meaning is generated once, that Home never
waits, that a failing vendor degrades instead of breaking, and that the chain
falls through to a second provider rather than depending on one.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

from visuals.providers import ImageProviderManager, ImageResult, NoImageProviderAvailable
from visuals.style import ORA_CONTEXTUAL_VISUAL_STYLE_V1, SEMANTIC_DIRECTIVE
from visuals.service import VisualService

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128

pytestmark = pytest.mark.asyncio


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client, client[os.environ.get("DB_NAME", "ora_test")]


class StubProvider:
    """Always succeeds, and counts how often it was actually asked."""

    def __init__(self, name="stub", content=PNG):
        self.name = name
        self.calls = 0
        self._content = content
        self.last_prompt = None

    def configured(self) -> bool:
        return True

    async def generate(self, *, prompt: str, aspect: str) -> ImageResult:
        self.calls += 1
        self.last_prompt = prompt
        return ImageResult(
            content=self._content, mime_type="image/png",
            provider=self.name, model=f"{self.name}-model",
        )


class BrokenProvider:
    def __init__(self, name="broken", reason="quota"):
        self.name = name
        self.calls = 0
        self._reason = reason

    def configured(self) -> bool:
        return True

    async def generate(self, *, prompt: str, aspect: str) -> ImageResult:
        self.calls += 1
        raise RuntimeError(self._reason)


class UnconfiguredProvider:
    name = "absent"

    def configured(self) -> bool:
        return False

    async def generate(self, *, prompt: str, aspect: str) -> ImageResult:  # pragma: no cover
        raise AssertionError("an unconfigured provider must never be called")


async def _wait_for(col, user_id, statuses, tries=60):
    for _ in range(tries):
        doc = await col.find_one({"user_id": user_id}, {"_id": 0})
        if doc and doc.get("status") in statuses:
            return doc
        await asyncio.sleep(0.05)
    return await col.find_one({"user_id": user_id}, {"_id": 0})


async def test_same_meaning_generates_once_and_is_reused():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    stub = StubProvider()
    svc = VisualService(db, providers=ImageProviderManager([stub]))
    await svc.ensure_indexes()
    try:
        first = await svc.ensure(
            user_id=user, entity_ref="situation:s1",
            title="Una piccola mostra", summary="definire il luogo",
        )
        # Home never waits on the provider: the call returns before generation.
        assert first["status"] in ("queued", "generating")
        assert first["url"] is None

        doc = await _wait_for(db.life_visuals, user, {"ready"})
        assert doc["status"] == "ready", doc
        assert stub.calls == 1

        again = await svc.ensure(
            user_id=user, entity_ref="situation:s1",
            title="Una piccola mostra", summary="definire il luogo",
        )
        assert again["visual_key"] == first["visual_key"]
        assert again["status"] == "ready"
        assert again["url"] == f"/api/visuals/{first['visual_key']}"
        assert stub.calls == 1, "a refresh must never regenerate"
        assert await db.life_visuals.count_documents({"user_id": user}) == 1
    finally:
        await db.life_visuals.delete_many({"user_id": user})
        client.close()


async def test_entity_visual_is_shared_across_surfaces():
    """One meaning, one picture — a future row reuses the hero's image."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    stub = StubProvider()
    svc = VisualService(db, providers=ImageProviderManager([stub]))
    try:
        await svc.ensure(user_id=user, entity_ref="situation:s9", title="Qualcosa")
        await _wait_for(db.life_visuals, user, {"ready"})
        shared = await svc.for_entity(user_id=user, entity_ref="situation:s9")
        assert shared and shared["status"] == "ready"
        assert stub.calls == 1
    finally:
        await db.life_visuals.delete_many({"user_id": user})
        client.close()


async def test_a_material_change_earns_a_new_image():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    svc = VisualService(db, providers=ImageProviderManager([StubProvider()]))
    try:
        a = await svc.ensure(user_id=user, entity_ref="situation:s2", title="Prima cosa")
        await _wait_for(db.life_visuals, user, {"ready"})
        b = await svc.ensure(
            user_id=user, entity_ref="situation:s2", title="Una cosa del tutto diversa",
        )
        assert a["visual_key"] != b["visual_key"]
    finally:
        await db.life_visuals.delete_many({"user_id": user})
        client.close()


async def test_chain_falls_through_to_the_next_provider():
    broken, working = BrokenProvider(), StubProvider(name="second")
    result = await ImageProviderManager([broken, working]).generate(prompt="p", aspect="4:3")
    assert result.provider == "second"
    assert broken.calls == 1 and working.calls == 1


async def test_unconfigured_providers_are_never_called():
    mgr = ImageProviderManager([UnconfiguredProvider(), StubProvider(name="real")])
    result = await mgr.generate(prompt="p", aspect="4:3")
    assert result.provider == "real"
    assert mgr.available() == ["real"]


async def test_no_provider_reports_exactly_what_is_missing():
    mgr = ImageProviderManager([UnconfiguredProvider(), BrokenProvider(reason="Billing hard limit")])
    with pytest.raises(NoImageProviderAvailable) as e:
        await mgr.generate(prompt="p", aspect="4:3")
    assert "not configured" in e.value.reasons["absent"]
    assert "Billing hard limit" in e.value.reasons["broken"]


async def test_provider_failure_leaves_home_usable():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    svc = VisualService(db, providers=ImageProviderManager([BrokenProvider()]))
    try:
        state = await svc.ensure(user_id=user, entity_ref="situation:s3", title="X")
        assert state["status"] in ("queued", "generating")
        doc = await _wait_for(db.life_visuals, user, {"missing", "failed"})
        # No URL is ever published for an image that does not exist.
        assert doc["status"] in ("missing", "failed")
        assert not doc.get("storage_key")
        assert VisualService._public(doc)["url"] is None
    finally:
        await db.life_visuals.delete_many({"user_id": user})
        client.close()


async def test_non_image_bytes_are_refused():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    liar = StubProvider(content=b"<?php system($_GET[0]); ?>" + b"\x00" * 128)
    svc = VisualService(db, providers=ImageProviderManager([liar]))
    try:
        await svc.ensure(user_id=user, entity_ref="situation:s4", title="X")
        doc = await _wait_for(db.life_visuals, user, {"missing", "failed"})
        assert doc.get("error_kind") == "invalid_image"
        assert not doc.get("storage_key")
    finally:
        await db.life_visuals.delete_many({"user_id": user})
        client.close()


async def test_prompt_carries_the_style_and_no_identifiers():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    stub = StubProvider()
    svc = VisualService(db, providers=ImageProviderManager([stub]))
    try:
        await svc.ensure(
            user_id=user, entity_ref="situation:s5",
            title="Cena con Marco Bianchi",
            summary="al ristorante, via Roma 12, 80 euro, scrivi a marco@example.com",
        )
        await _wait_for(db.life_visuals, user, {"ready"})
        prompt = stub.last_prompt or ""
        # Asserted against the constant, not a phrase: the wording of the
        # style is allowed to evolve, its presence is not.
        assert ORA_CONTEXTUAL_VISUAL_STYLE_V1 in prompt, "style lock must always travel"
        assert SEMANTIC_DIRECTIVE in prompt, "the card's concept must stay legible"
        for secret in ("Marco Bianchi", "via Roma", "marco@example.com", "80"):
            assert secret not in prompt, f"{secret} reached the provider"
    finally:
        await db.life_visuals.delete_many({"user_id": user})
        client.close()


async def test_client_never_learns_the_provider():
    doc = {
        "visual_key": "vis_x", "status": "ready", "provider": "gemini",
        "model": "secret-model", "error_detail": "billing",
    }
    assert set(VisualService._public(doc)) == {"visual_key", "status", "url"}


async def test_entity_reuse_does_not_serve_a_stale_style():
    """A style bump must actually reach the screen.

    The old picture stays `ready` under its old key forever; if entity reuse
    ignored the style version it would keep being served and the new look would
    never appear — exactly the regression this guards.
    """
    from visuals import style as style_mod

    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    svc = VisualService(db, providers=ImageProviderManager([StubProvider()]))
    try:
        await svc.ensure(user_id=user, entity_ref="situation:s7", title="Qualcosa")
        await _wait_for(db.life_visuals, user, {"ready"})
        assert await svc.for_entity(user_id=user, entity_ref="situation:s7")

        # Simulate the look changing under an existing image.
        await db.life_visuals.update_one(
            {"user_id": user}, {"$set": {"style_version": "an_older_style"}},
        )
        assert await svc.for_entity(user_id=user, entity_ref="situation:s7") is None,             "a visual from a previous style must not be reused"
    finally:
        await db.life_visuals.delete_many({"user_id": user})
        client.close()
