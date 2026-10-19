"""Owner-scoped wardrobe inventory with encrypted, EXIF-free photo thumbnails.

No outside image service, external URL, image logs or LLM access in v1.
MongoDB stores one independent item per owner, never user-supplied identifiers
as the sole access check. Updates/deletes use optimistic revisions.
"""
from __future__ import annotations

import base64
import io
import os
import uuid
from datetime import datetime, timezone
from typing import Literal

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .recommend import recommend

MAX_ITEMS = 75
MAX_UPLOAD = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_THUMBNAIL = 160_000


class WardrobeError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class GarmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    revision: int = Field(default=0, ge=0)
    name: str = Field(min_length=2, max_length=80)
    category: Literal["top", "bottom", "shoes", "one_piece", "outerwear", "accessory"]
    color: str = Field(min_length=2, max_length=32)
    formality: Literal["sport", "casual", "smart", "formal"]
    seasons: list[Literal["spring", "summer", "fall", "winter"]] = Field(default_factory=list, max_length=4)
    status: Literal["available", "laundry", "unavailable"] = "available"

    @model_validator(mode="after")
    def clean_text(self):
        for field in ("name", "color"):
            value = getattr(self, field).strip()
            if len(value) < 2 or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError("Nome e colore devono essere leggibili.")
            setattr(self, field, value)
        self.seasons = sorted(set(self.seasons))
        return self


class OutfitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occasion: Literal["running", "casual_evening", "chic_evening", "club", "wedding"]
    temperature_c: float | None = Field(default=None, ge=-30, le=50)
    use_ai: bool = False
    style_note: str = Field(default="", max_length=200)


class PhotoCipher:
    def __init__(self, secret: str):
        if len(secret) < 32:
            raise WardrobeError("Archivio fotografie non configurato.", 503)
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"ora-wardrobe-v1",
                   info=b"wardrobe-photo-only").derive(secret.encode("utf-8"))
        self.aes = AESGCM(key)

    @classmethod
    def configured(cls):
        return cls(os.environ.get("TOKEN_VAULT_KEY", ""))

    def encrypt(self, owner: str, item_id: str, raw: bytes) -> str:
        nonce = os.urandom(12)
        aad = f"{owner}:{item_id}".encode("utf-8")
        return base64.b64encode(nonce + self.aes.encrypt(nonce, raw, aad)).decode("ascii")

    def decrypt(self, owner: str, item_id: str, payload: str) -> bytes:
        try:
            raw = base64.b64decode(payload, validate=True)
            return self.aes.decrypt(raw[:12], raw[12:], f"{owner}:{item_id}".encode("utf-8"))
        except Exception as exc:
            raise WardrobeError("La fotografia non è leggibile. Nessun dato è stato modificato.", 503) from exc


def make_thumbnail(raw: bytes) -> bytes:
    if not raw or len(raw) > MAX_UPLOAD:
        raise WardrobeError("La foto deve essere inferiore a 5 MB.", 413)
    try:
        with Image.open(io.BytesIO(raw), formats=["JPEG", "PNG", "WEBP"]) as opened:
            if opened.width * opened.height > MAX_PIXELS:
                raise WardrobeError("Immagine troppo grande: ritaglia il capo.", 413)
            image = ImageOps.exif_transpose(opened)
            image.load()
            image.thumbnail((480, 480), Image.Resampling.LANCZOS)
            if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                rgba = image.convert("RGBA")
                white = Image.new("RGB", rgba.size, (255, 255, 255))
                white.paste(rgba, mask=rgba.getchannel("A"))
                image = white
            else:
                image = image.convert("RGB")
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=78, optimize=True)
            photo = out.getvalue()
            if len(photo) > MAX_THUMBNAIL:
                raise WardrobeError("La miniatura non rientra nel limite. Ritaglia il capo.", 413)
            return photo
    except WardrobeError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise WardrobeError("Carica una foto JPEG, PNG o WebP valida.", 422) from exc


class WardrobeService:
    def __init__(self, db, cipher: PhotoCipher):
        self.db = db
        self.col = db.wardrobe_items
        self.cipher = cipher

    @staticmethod
    def _key(owner: str, item_id: str) -> str:
        return f"{owner}:{item_id}"

    async def _load(self, owner: str, item_id: str):
        return await self.col.find_one({"_id": self._key(owner, item_id), "user_id": owner})

    def _public(self, owner: str, doc: dict) -> dict:
        result = {k: v for k, v in doc.items() if k not in {"_id", "user_id", "photo_encrypted"}}
        if doc.get("photo_encrypted"):
            image = self.cipher.decrypt(owner, doc["id"], doc["photo_encrypted"])
            result["photo"] = "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")
        else:
            result["photo"] = None
        return result

    async def list_items(self, owner: str) -> list[dict]:
        docs = await self.col.find({"user_id": owner}).to_list(length=MAX_ITEMS + 1)
        return [self._public(owner, doc) for doc in sorted(docs, key=lambda d: (d["name"].casefold(), d["id"]))]

    async def save(self, owner: str, body: GarmentInput) -> dict:
        existing = await self._load(owner, body.id)
        if (existing["revision"] if existing else 0) != body.revision:
            raise WardrobeError("Il capo è stato modificato. Aggiorna la lista e riprova.", 409)
        now = datetime.now(timezone.utc).isoformat()
        data = body.model_dump(exclude={"revision"})
        if not existing:
            if await self.col.count_documents({"user_id": owner}) >= MAX_ITEMS:
                raise WardrobeError("Limite di 75 capi raggiunto per questa versione.", 409)
            record = {"_id": self._key(owner, body.id), "user_id": owner,
                      **data, "revision": 1, "created_at": now, "updated_at": now}
            try:
                await self.col.insert_one(record)
            except Exception as exc:
                if getattr(exc, "code", None) == 11000:
                    raise WardrobeError("Capo già presente: aggiorna la lista.", 409) from None
                raise
            return self._public(owner, record)
        updated = {**data, "revision": body.revision + 1, "updated_at": now}
        result = await self.col.update_one(
            {"_id": existing["_id"], "user_id": owner, "revision": body.revision},
            {"$set": updated},
        )
        if result.matched_count != 1:
            raise WardrobeError("Il capo è cambiato durante il salvataggio.", 409)
        return self._public(owner, {**existing, **updated})

    async def save_photo(self, owner: str, item_id: str, revision: int, thumbnail: bytes) -> dict:
        existing = await self._load(owner, item_id)
        if not existing:
            raise WardrobeError("Capo non trovato.", 404)
        if existing["revision"] != revision:
            raise WardrobeError("Il capo è stato modificato. Aggiorna e riprova.", 409)
        if not thumbnail or len(thumbnail) > MAX_THUMBNAIL:
            raise WardrobeError("Miniatura troppo grande.", 413)
        updated = {"photo_encrypted": self.cipher.encrypt(owner, item_id, thumbnail),
                   "revision": revision + 1, "updated_at": datetime.now(timezone.utc).isoformat()}
        result = await self.col.update_one(
            {"_id": existing["_id"], "user_id": owner, "revision": revision}, {"$set": updated})
        if result.matched_count != 1:
            raise WardrobeError("Fotografia non salvata: capo modificato.", 409)
        return self._public(owner, {**existing, **updated})

    async def delete(self, owner: str, item_id: str, revision: int) -> None:
        existing = await self._load(owner, item_id)
        if not existing:
            raise WardrobeError("Capo non trovato.", 404)
        if existing["revision"] != revision:
            raise WardrobeError("Il capo è stato modificato. Aggiorna e riprova.", 409)
        result = await self.col.delete_one({"_id": existing["_id"], "user_id": owner, "revision": revision})
        if result.deleted_count != 1:
            raise WardrobeError("Capo modificato durante l'eliminazione.", 409)

    async def list_metadata(self, owner: str) -> list[dict]:
        """Only user-owned catalog metadata, never encrypted photo bytes or data URIs.

        This is the sole wardrobe read usable by the AI stylist and conversational
        capability. Listing clothing never implicitly sends photographs to a model.
        """
        docs = await self.col.find({"user_id": owner}).to_list(length=MAX_ITEMS + 1)
        return [
            {k: v for k, v in doc.items()
             if k not in {"_id", "user_id", "photo_encrypted"}}
            for doc in sorted(docs, key=lambda d: (d["name"].casefold(), d["id"]))
        ]

    async def outfits(self, owner: str, body: OutfitInput) -> dict:
        from .stylist import advise
        items = await self.list_metadata(owner)
        return await advise(
            self.db, owner, items, body.occasion,
            temperature_c=body.temperature_c,
            note=body.style_note, use_ai=body.use_ai,
        )
