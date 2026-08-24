"""Contextual visual lifecycle — request, generate once, reuse forever.

    eligible card
        → stable visual_key (semantic, never the clock)
        → already have it?  →  reuse, zero cost
        → otherwise         →  record `queued`, return immediately
        → background        →  generate · validate · store · `ready`

**Nothing here ever runs during a Home render.** `ensure` performs one indexed
lookup and, at most, one small insert; the provider call happens on a
background task that Home does not await. A page that waits for an image
generation is a page that is broken by the image generation.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from visuals.providers import ImageProviderManager, NoImageProviderAvailable
from visuals.style import VISUAL_ASPECT, VISUAL_STYLE_VERSION, build_descriptor, visual_key

logger = logging.getLogger("ora.visuals")

COLLECTION = "life_visuals"

# One image is worth generating a few times at most. Past this the card keeps
# its fallback rather than burning budget on a provider that keeps refusing.
MAX_ATTEMPTS = 3
# Bounded concurrency: a burst of new cards must not open twenty provider calls.
_semaphore = asyncio.Semaphore(2)
# Best-effort in-process tasks, mirroring the V2.9.4 accelerator pattern:
# losing one costs a later retry, never the record.
_inflight: set[str] = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _descriptor_hash(subject: str) -> str:
    """Identity of the *meaning*, not the words that produced it. Stored so a
    semantic revision is detectable without keeping the raw text around."""
    return hashlib.sha256(subject.encode()).hexdigest()[:16]


class VisualService:
    def __init__(self, db, storage=None, providers: Optional[ImageProviderManager] = None):
        self.db = db
        self.col = db[COLLECTION]
        self._storage = storage
        self.providers = providers or ImageProviderManager()

    @property
    def storage(self):
        if self._storage is None:
            from documents.storage import build_default_storage

            self._storage = build_default_storage()
        return self._storage

    async def ensure_indexes(self) -> None:
        await self.col.create_index([("user_id", 1), ("visual_key", 1)], unique=True)
        await self.col.create_index([("user_id", 1), ("status", 1)])
        await self.col.create_index([("user_id", 1), ("entity_ref", 1)])

    # --- read path (called during Home build — must stay cheap) -------------

    async def ensure(
        self,
        *,
        user_id: str,
        entity_ref: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        schedule: bool = True,
    ) -> dict[str, Any]:
        """Return the public visual state for one card, scheduling generation
        if this meaning has never been drawn before."""
        descriptor = build_descriptor(title=title, summary=summary)
        key = visual_key(entity_ref=entity_ref, descriptor=descriptor)

        existing = await self.col.find_one(
            {"user_id": user_id, "visual_key": key}, {"_id": 0},
        )
        if existing:
            # Same meaning, same picture — no provider call, no cost.
            return self._public(existing)

        record = {
            "visual_key": key,
            "user_id": user_id,
            "entity_ref": entity_ref,
            "descriptor_hash": _descriptor_hash(descriptor.subject),
            "style_version": VISUAL_STYLE_VERSION,
            "status": "queued",
            "provider": None,
            "storage_key": None,
            "mime_type": None,
            "attempts": 0,
            "created_at": _now(),
            "updated_at": _now(),
        }
        try:
            await self.col.insert_one(dict(record))
        except Exception:
            # Lost a race with another request for the same card; the winner's
            # record is the one that matters.
            existing = await self.col.find_one({"user_id": user_id, "visual_key": key}, {"_id": 0})
            return self._public(existing or record)

        if schedule:
            self._schedule(user_id=user_id, key=key, prompt=descriptor.prompt())
        return self._public(record)

    async def for_entity(self, *, user_id: str, entity_ref: str) -> Optional[dict[str, Any]]:
        """A ready visual already owned by this entity, if any.

        This is what lets one situation's picture appear in Home, in its future
        row and later in other surfaces without generating it five times: the
        image belongs to the thing, not to the place it is shown.

        Scoped to the CURRENT style version. Without that filter a style bump
        would be cosmetic only: the old picture stays `ready` under its old key,
        this lookup keeps finding it, and the new look never reaches the screen
        — which is precisely what happened when the style moved from
        photographic to stylised.
        """
        doc = await self.col.find_one(
            {
                "user_id": user_id,
                "entity_ref": entity_ref,
                "status": "ready",
                "style_version": VISUAL_STYLE_VERSION,
            },
            {"_id": 0},
            sort=[("updated_at", -1)],
        )
        return self._public(doc) if doc else None

    # --- write path (background only) ---------------------------------------

    def _schedule(self, *, user_id: str, key: str, prompt: str) -> None:
        token = f"{user_id}:{key}"
        if token in _inflight:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop (sync context / tests) — a later pass picks it up
        _inflight.add(token)
        loop.create_task(self._generate(user_id=user_id, key=key, prompt=prompt, token=token))

    async def _generate(self, *, user_id: str, key: str, prompt: str, token: str) -> None:
        try:
            async with _semaphore:
                await self.col.update_one(
                    {"user_id": user_id, "visual_key": key},
                    {"$set": {"status": "generating", "updated_at": _now()}, "$inc": {"attempts": 1}},
                )
                try:
                    result = await self.providers.generate(prompt=prompt, aspect=VISUAL_ASPECT)
                except NoImageProviderAvailable as exc:
                    await self._fail(user_id, key, "no_provider", str(exc)[:300])
                    return
                except Exception as exc:
                    await self._fail(user_id, key, type(exc).__name__, str(exc)[:300])
                    return

                if not self._looks_like_image(result.content):
                    await self._fail(user_id, key, "invalid_image", "provider returned non-image bytes")
                    return

                stored = await self.storage.put(
                    user_id=user_id,
                    content=result.content,
                    original_filename=f"{key}.png",
                    mime_type=result.mime_type,
                )
                # Persist AFTER the bytes are durable: a record claiming `ready`
                # with nothing behind it would render a broken card forever.
                await self.col.update_one(
                    {"user_id": user_id, "visual_key": key},
                    {"$set": {
                        "status": "ready",
                        "provider": result.provider,
                        "model": result.model,
                        "storage_key": stored.key,
                        "mime_type": result.mime_type,
                        "error_kind": None,
                        "updated_at": _now(),
                    }},
                )
                logger.info("visual ready key=%s provider=%s", key, result.provider)
        finally:
            _inflight.discard(token)

    async def _fail(self, user_id: str, key: str, kind: str, detail: str) -> None:
        doc = await self.col.find_one({"user_id": user_id, "visual_key": key}, {"_id": 0, "attempts": 1})
        attempts = int((doc or {}).get("attempts") or 0)
        await self.col.update_one(
            {"user_id": user_id, "visual_key": key},
            {"$set": {
                "status": "failed" if attempts >= MAX_ATTEMPTS else "missing",
                "error_kind": kind,
                # Kept for the operator; contains provider text, never user data.
                "error_detail": detail,
                "updated_at": _now(),
            }},
        )
        logger.info("visual generation failed key=%s kind=%s attempts=%s", key, kind, attempts)

    @staticmethod
    def _looks_like_image(content: bytes) -> bool:
        """Refuse anything that is not actually an image, whatever the provider
        claimed. A card is a place bytes get rendered; it is not a place to
        trust a content-type header."""
        if len(content) < 64:
            return False
        return (
            content[:8] == b"\x89PNG\r\n\x1a\n"
            or content[:3] == b"\xff\xd8\xff"
            or (content[:4] == b"RIFF" and content[8:12] == b"WEBP")
        )

    async def read_bytes(self, *, user_id: str, key: str) -> tuple[bytes, str]:
        doc = await self.col.find_one(
            {"user_id": user_id, "visual_key": key, "status": "ready"},
            {"_id": 0, "storage_key": 1, "mime_type": 1},
        )
        if not doc or not doc.get("storage_key"):
            raise FileNotFoundError("visual not ready")
        content = await self.storage.read(user_id=user_id, key=doc["storage_key"])
        return content, doc.get("mime_type") or "image/png"

    @staticmethod
    def _public(doc: dict[str, Any]) -> dict[str, Any]:
        """What the client is allowed to see: a status and, when ready, a URL.

        No prompt, no descriptor, no provider name, no error text — a card is
        not a place to explain an inference stack.
        """
        status = doc.get("status") or "missing"
        return {
            "visual_key": doc.get("visual_key"),
            "status": status,
            "url": f"/api/visuals/{doc.get('visual_key')}" if status == "ready" else None,
        }


__all__ = ["VisualService", "COLLECTION", "MAX_ATTEMPTS"]
