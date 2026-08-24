"""Profile photo storage — the user's own picture, nothing else.

Reuses `DocumentStorageProvider` rather than inventing a second media layer:
that abstraction is already user-scoped, content-hashed, idempotent and
designed to be swapped for S3/GCS without touching callers. A profile photo is
just another blob owned by one person.

The picture is chosen BY the user and never generated for them. That is the
whole distinction from the contextual card visuals: those describe a situation,
this is a face.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("ora.profile_media")

# Formats a browser and an iOS photo library both produce, and that we can
# serve back without transcoding. Deliberately a short allowlist: an upload
# surface that accepts "whatever" is an upload surface that accepts scripts.
ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
}

MAX_AVATAR_BYTES = 8 * 1024 * 1024  # 8 MB — a phone photo, not a RAW file


class InvalidAvatar(ValueError):
    """The upload is not something we will store. Message is user-safe."""


@dataclass
class StoredAvatar:
    key: str
    size: int
    content_type: str


def _sniff(content: bytes) -> Optional[str]:
    """Identify the format from the bytes themselves.

    The declared content type and the filename are both attacker-controlled;
    the magic number is what the file actually is. Anything we cannot identify
    as one of the allowed image formats is refused — including a valid image
    with a lying header, and a script wearing a .jpg name.
    """
    if len(content) < 12:
        return None
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    # HEIC/HEIF: ISO-BMFF box with an 'ftyp' brand.
    if content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"):
            return "image/heic"
    return None


def validate_avatar(*, content: bytes, declared_type: Optional[str]) -> str:
    """Return the trusted content type, or raise `InvalidAvatar`."""
    if not content:
        raise InvalidAvatar("Il file è vuoto.")
    if len(content) > MAX_AVATAR_BYTES:
        raise InvalidAvatar("L'immagine è troppo grande: il limite è 8 MB.")

    actual = _sniff(content)
    if actual is None or actual not in ALLOWED_IMAGE_TYPES:
        raise InvalidAvatar("Questo file non è un'immagine supportata (JPG, PNG, WebP o HEIC).")

    # A mismatch is not fatal — browsers mislabel HEIC constantly — but the
    # sniffed type is the one we trust and the one we serve back.
    if declared_type and declared_type.lower() != actual:
        logger.info("avatar content-type mismatch declared=%s actual=%s", declared_type, actual)
    return actual


class ProfileMediaService:
    """Store, read and remove one user's profile photo."""

    def __init__(self, db, storage=None):
        self.db = db
        if storage is None:
            from documents.storage import build_default_storage

            storage = build_default_storage()
        self.storage = storage

    async def put(self, *, user_id: str, content: bytes, declared_type: Optional[str]) -> StoredAvatar:
        content_type = validate_avatar(content=content, declared_type=declared_type)
        stored = await self.storage.put(
            user_id=user_id,
            content=content,
            original_filename=f"avatar.{ALLOWED_IMAGE_TYPES[content_type]}",
            mime_type=content_type,
        )

        previous = await self._current_key(user_id)
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "avatar_key": stored.key,
                "avatar_content_type": content_type,
                # `picture` stays the single field every surface already reads,
                # so the rail, settings and /me need no special case for
                # "uploaded" versus "from Google".
                "picture": f"/api/auth/avatar/{stored.key}",
            }},
        )

        # Only after the new one is durably recorded. Skipped when the bytes are
        # identical, because the content-hash key would be the same blob.
        if previous and previous != stored.key:
            await self._forget_blob(user_id, previous)

        return StoredAvatar(key=stored.key, size=stored.size, content_type=content_type)

    async def read(self, *, user_id: str, key: str) -> tuple[bytes, str]:
        """Read this user's own avatar. Ownership is structural: the storage
        provider resolves the path under the caller's own directory, so a key
        belonging to someone else simply does not exist here."""
        current = await self._current_key(user_id)
        if not current or current != key:
            raise FileNotFoundError("avatar not found")
        content = await self.storage.read(user_id=user_id, key=key)
        doc = await self.db.users.find_one({"user_id": user_id}, {"_id": 0, "avatar_content_type": 1})
        return content, (doc or {}).get("avatar_content_type") or "image/jpeg"

    async def remove(self, *, user_id: str) -> bool:
        key = await self._current_key(user_id)
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"avatar_key": None, "avatar_content_type": None, "picture": None}},
        )
        if key:
            await self._forget_blob(user_id, key)
        return bool(key)

    async def _current_key(self, user_id: str) -> Optional[str]:
        doc = await self.db.users.find_one({"user_id": user_id}, {"_id": 0, "avatar_key": 1})
        return (doc or {}).get("avatar_key")

    async def _forget_blob(self, user_id: str, key: str) -> None:
        try:
            await self.storage.delete(user_id=user_id, key=key)
        except Exception as exc:  # a leaked blob is better than a failed request
            logger.info("avatar blob delete soft-fail: %s", type(exc).__name__)


__all__ = [
    "ProfileMediaService",
    "InvalidAvatar",
    "validate_avatar",
    "ALLOWED_IMAGE_TYPES",
    "MAX_AVATAR_BYTES",
]
