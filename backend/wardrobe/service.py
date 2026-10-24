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
import hmac
from datetime import datetime, timezone
from typing import Literal

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .recommend import recommend

MAX_ITEMS = 75
RAINY = {"rain", "drizzle", "showers", "thunderstorm", "snow"}
MAX_UPLOAD = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_THUMBNAIL = 160_000
MAX_SOURCE = 650_000
IMAGE_SOURCE_EDGE = 1200


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
    occasion: Literal["running", "everyday", "work", "casual_evening", "chic_evening", "club", "wedding"]
    temperature_c: float | None = Field(default=None, ge=-30, le=50)
    use_ai: bool = False
    style_note: str = Field(default="", max_length=200)
    # Read today's weather where the person is when no temperature was given.
    use_weather: bool = True


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


def make_source_photo(raw: bytes) -> bytes:
    """Keep a bounded EXIF-free, user-supplied reference view (not the raw upload).

    New front/back uploads retain a 1200px optimized reference for future
    segmentation. Old garments only have the previous 480px normalized JPEG;
    never label that missing original as full resolution.
    """
    if not raw or len(raw) > MAX_UPLOAD:
        raise WardrobeError("La foto deve essere inferiore a 5 MB.", 413)
    try:
        with Image.open(io.BytesIO(raw), formats=["JPEG", "PNG", "WEBP"]) as opened:
            if opened.width * opened.height > MAX_PIXELS:
                raise WardrobeError("Immagine troppo grande: ritaglia il capo.", 413)
            oriented = ImageOps.exif_transpose(opened)
            oriented.load()
            oriented.thumbnail((IMAGE_SOURCE_EDGE, IMAGE_SOURCE_EDGE), Image.Resampling.LANCZOS)
            if oriented.mode in ("RGBA", "LA") or "transparency" in opened.info:
                rgba = oriented.convert("RGBA")
                white = Image.new("RGB", rgba.size, (255, 255, 255))
                white.paste(rgba, mask=rgba.getchannel("A"))
                oriented = white
            else:
                oriented = oriented.convert("RGB")
            for quality in (84, 74, 62):
                buff = io.BytesIO()
                oriented.save(buff, format="JPEG", quality=quality, optimize=True)
                if buff.tell() <= MAX_SOURCE:
                    return buff.getvalue()
            raise WardrobeError("La foto richiede un ritaglio più stretto.", 413)
    except WardrobeError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise WardrobeError("Carica una foto JPEG, PNG o WebP valida.", 422) from exc


def combine_wardrobe_views(front: bytes, back: bytes | None) -> bytes:
    """One explicit AI request for both views of the same stored garment.

    Creates an ephemeral two-pane image: orientation labels are outside the
    garment regions so the AI can distinguish front from back without confusing
    the views with two separate items. Nothing is stored.
    """
    if not back:
        return front
    with Image.open(io.BytesIO(front)) as f, Image.open(io.BytesIO(back)) as b:
        first = f.convert("RGB")
        second = b.convert("RGB")
        first.thumbnail((460, 460), Image.Resampling.LANCZOS)
        second.thumbnail((460, 460), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (960, 506), (247, 248, 250))
        canvas.paste(first, ((480 - first.width)//2, 40 + (460-first.height)//2))
        canvas.paste(second, (480 + (480-second.width)//2, 40 + (460-second.height)//2))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(canvas)
        draw.text((12, 12), "FRONTE", fill=(20, 20, 25))
        draw.text((493, 12), "RETRO", fill=(20, 20, 25))
        draw.line([(479, 0), (479, 506)], fill=(155, 159, 166), width=2)
        buff = io.BytesIO()
        canvas.save(buff, format="JPEG", quality=82, optimize=True)
        return buff.getvalue()


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
        result = {k: v for k, v in doc.items() if k not in {
            "_id", "user_id", "photo_encrypted", "photo_back_encrypted",
            "front_source_encrypted", "back_source_encrypted", "visual_photo_sha256",
        }}
        for name, stored, scope in (
            ("photo", "photo_encrypted", doc["id"]),
            ("back_photo", "photo_back_encrypted", f"{doc['id']}:back"),
        ):
            payload = doc.get(stored)
            result[name] = (
                "data:image/jpeg;base64," + base64.b64encode(
                    self.cipher.decrypt(owner, scope, payload)
                ).decode("ascii")
                if payload else None
            )
        result["has_back"] = bool(doc.get("photo_back_encrypted"))
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
        if existing.get("category") != body.category or existing.get("color") != body.color:
            # Do not trust old visual descriptions after an item is reclassified.
            updated["visual_profile"] = None
            updated["visual_photo_sha256"] = None
        result = await self.col.update_one(
            {"_id": existing["_id"], "user_id": owner, "revision": body.revision},
            {"$set": updated},
        )
        if result.matched_count != 1:
            raise WardrobeError("Il capo è cambiato durante il salvataggio.", 409)
        if any(existing.get(field) != data.get(field) for field in (
            "name", "category", "color", "formality")):
            # Feedback on an old shirt/shoe identity is not a preference for a
            # replaced or recategorized garment with the same item ID.
            from .preferences import delete_item_feedback
            await delete_item_feedback(self.db, owner, body.id)
        return self._public(owner, {**existing, **updated})

    async def save_photo(self, owner: str, item_id: str, revision: int, thumbnail: bytes,
                         source: bytes | None = None) -> dict:
        existing = await self._load(owner, item_id)
        if not existing:
            raise WardrobeError("Capo non trovato.", 404)
        if existing["revision"] != revision:
            raise WardrobeError("Il capo è stato modificato. Aggiorna e riprova.", 409)
        if not thumbnail or len(thumbnail) > MAX_THUMBNAIL:
            raise WardrobeError("Miniatura troppo grande.", 413)
        if source is not None and (not source or len(source) > MAX_SOURCE):
            raise WardrobeError("Foto di riferimento troppo grande.", 413)
        updated = {"photo_encrypted": self.cipher.encrypt(owner, item_id, thumbnail),
                   "visual_profile": None, "visual_photo_sha256": None,
                   "front_source_encrypted": (
                       self.cipher.encrypt(owner, f"{item_id}:source-front", source)
                       if source else None),
                   "revision": revision + 1, "updated_at": datetime.now(timezone.utc).isoformat()}
        result = await self.col.update_one(
            {"_id": existing["_id"], "user_id": owner, "revision": revision}, {"$set": updated})
        if result.matched_count != 1:
            raise WardrobeError("Fotografia non salvata: capo modificato.", 409)
        if existing.get("photo_encrypted"):
            # Replacing the visual identity also invalidates learnt approval
            # of its prior photographed appearance, never other owners' likes.
            from .preferences import delete_item_feedback
            await delete_item_feedback(self.db, owner, item_id)
        return self._public(owner, {**existing, **updated})

    async def save_back_photo(self, owner: str, item_id: str, revision: int,
                              thumbnail: bytes, source: bytes | None = None) -> dict:
        """Back is a second encrypted view of the SAME immutable garment ID.

        The exact owner and revision fence prevent mixing back photos between
        accounts/tabs. A back view requires a stored front view.
        """
        existing = await self._load(owner, item_id)
        if not existing:
            raise WardrobeError("Capo non trovato.", 404)
        if existing["revision"] != revision:
            raise WardrobeError("Capo cambiato: aggiorna e riprova.", 409)
        if not existing.get("photo_encrypted"):
            raise WardrobeError("Carica prima la fotografia del fronte.", 409)
        if not thumbnail or len(thumbnail) > MAX_THUMBNAIL:
            raise WardrobeError("Miniatura retro troppo grande.", 413)
        if source is not None and (not source or len(source) > MAX_SOURCE):
            raise WardrobeError("Foto retro troppo grande.", 413)
        changes = {
            "photo_back_encrypted": self.cipher.encrypt(owner, f"{item_id}:back", thumbnail),
            "back_source_encrypted": (
                self.cipher.encrypt(owner, f"{item_id}:source-back", source)
                if source else None),
            "visual_profile": None, "visual_photo_sha256": None,
            "revision": revision + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        result = await self.col.update_one(
            {"_id": existing["_id"], "user_id": owner, "revision": revision},
            {"$set": changes})
        if result.matched_count != 1:
            raise WardrobeError("Retro modificato da un altro dispositivo.", 409)
        from .preferences import delete_item_feedback
        await delete_item_feedback(self.db, owner, item_id)
        return self._public(owner, {**existing, **changes})

    async def delete_back_photo(self, owner: str, item_id: str, revision: int) -> dict:
        existing = await self._load(owner, item_id)
        if not existing:
            raise WardrobeError("Capo non trovato.", 404)
        if existing["revision"] != revision:
            raise WardrobeError("Capo cambiato: aggiorna e riprova.", 409)
        if not existing.get("photo_back_encrypted"):
            raise WardrobeError("Questo capo non ha una foto retro.", 404)
        changes = {
            "photo_back_encrypted": None, "back_source_encrypted": None,
            "visual_profile": None, "visual_photo_sha256": None,
            "revision": revision + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        result = await self.col.update_one(
            {"_id": existing["_id"], "user_id": owner, "revision": revision},
            {"$set": changes})
        if result.matched_count != 1:
            raise WardrobeError("Il retro è cambiato durante la rimozione.", 409)
        from .preferences import delete_item_feedback
        await delete_item_feedback(self.db, owner, item_id)
        return self._public(owner, {**existing, **changes})

    async def delete(self, owner: str, item_id: str, revision: int) -> None:
        existing = await self._load(owner, item_id)
        if not existing:
            raise WardrobeError("Capo non trovato.", 404)
        if existing["revision"] != revision:
            raise WardrobeError("Il capo è stato modificato. Aggiorna e riprova.", 409)
        result = await self.col.delete_one({"_id": existing["_id"], "user_id": owner, "revision": revision})
        if result.deleted_count != 1:
            raise WardrobeError("Capo modificato durante l'eliminazione.", 409)
        from .preferences import delete_item_feedback
        await delete_item_feedback(self.db, owner, item_id)

    async def list_metadata(self, owner: str) -> list[dict]:
        """Only user-owned catalog metadata, never encrypted photo bytes or data URIs.

        This is the sole wardrobe read usable by the AI stylist and conversational
        capability. Listing clothing never implicitly sends photographs to a model.
        """
        docs = await self.col.find({"user_id": owner}).to_list(length=MAX_ITEMS + 1)
        return [
            {k: v for k, v in doc.items()
             if k not in {
                 "_id", "user_id", "photo_encrypted", "photo_back_encrypted",
                 "front_source_encrypted", "back_source_encrypted",
                 "visual_photo_sha256"}}
            for doc in sorted(docs, key=lambda d: (d["name"].casefold(), d["id"]))
        ]

    async def _weather_now(self, owner: str) -> dict | None:
        """The temperature where the person is now, or nothing — never a guess."""
        try:
            import weather as meteo
            from home.service import HomeService

            point = await HomeService(self.db)._where_they_are(owner)
            if point is None:
                return None
            lat, lon, place = point
            now = await meteo.now_at(lat=lat, lon=lon, place=place)
        except Exception:
            return None
        if not now.get("available") or now.get("temperature_c") is None:
            return None
        return {
            "temperature_c": float(now["temperature_c"]),
            "condition": str(now.get("condition") or ""),
            "label": str(now.get("condition_label") or now.get("label") or ""),
            "place": str(now.get("place") or ""),
        }

    async def outfits(self, owner: str, body: OutfitInput) -> dict:
        from .stylist import advise
        from .preferences import load_feedback
        from .recommend import LAYER_BELOW_C
        items = await self.list_metadata(owner)
        feedback = await load_feedback(self.db, owner)
        temperature = body.temperature_c
        weather = None
        if temperature is None and body.use_weather:
            weather = await self._weather_now(owner)
            if weather:
                temperature = weather["temperature_c"]
        note = body.style_note
        if weather and weather["condition"] in RAINY:
            note = (note + " Oggi piove.").strip()[:200]
        result = await advise(
            self.db, owner, items, body.occasion,
            temperature_c=temperature,
            note=note, use_ai=body.use_ai,
            feedback=feedback,
        )
        if weather:
            result["weather"] = weather
        if temperature is not None and temperature <= LAYER_BELOW_C and not any(
            i.get("category") == "outerwear" and i.get("status") == "available" for i in items
        ):
            result["layer_missing"] = True
        return result

    async def record_outfit_feedback(self, owner: str, body) -> dict:
        from .preferences import record_feedback
        items = await self.list_metadata(owner)
        return await record_feedback(self.db, owner, items, body)


    async def analyze_saved_photo(self, owner: str, item_id: str, revision: int) -> dict:
        """Explicit foreground scan of one encrypted photo, returning no DB mutation."""
        from .appearance import describe_appearance, photo_signature
        from .classify import enforce_owner_quota

        current = await self._load(owner, item_id)
        if current is None:
            raise WardrobeError("Capo non trovato.", 404)
        if current["revision"] != revision:
            raise WardrobeError("Capo cambiato: aggiorna la lista prima dell'analisi.", 409)
        if not current.get("photo_encrypted"):
            raise WardrobeError("Aggiungi prima una foto del capo.", 409)
        await enforce_owner_quota(self.db, owner)
        front = self.cipher.decrypt(owner, item_id, current["photo_encrypted"])
        back = (self.cipher.decrypt(owner, f"{item_id}:back", current["photo_back_encrypted"])
                if current.get("photo_back_encrypted") else None)
        photo = combine_wardrobe_views(front, back)
        output = await describe_appearance(photo)
        if output["recognized"]:
            if not back and isinstance(output.get("draft"), dict):
                # Never present hallucinated "back" details as visually observed
                # when the owner has uploaded only the front.
                output["draft"]["back_graphic"] = "uncertain"
                output["draft"]["back_style"] = "uncertain"
            return {**output, "revision": revision, "photo_sha256": photo_signature(photo),
                    "views_analyzed": 2 if back else 1}
        return {**output, "revision": revision}

    async def confirm_appearance(self, owner: str, item_id: str, body) -> dict:
        """Store only user-approved enum attributes for the exact current photo."""
        from .appearance import photo_signature

        current = await self._load(owner, item_id)
        if current is None:
            raise WardrobeError("Capo non trovato.", 404)
        if current["revision"] != body.revision:
            raise WardrobeError("La foto o il capo sono cambiati. Ripeti l'analisi.", 409)
        if not current.get("photo_encrypted"):
            raise WardrobeError("Fotografia non disponibile.", 409)
        if not current.get("photo_back_encrypted") and (
            body.back_graphic != "uncertain" or body.back_style != "uncertain"
        ):
            raise WardrobeError(
                "Senza una foto del retro non posso confermarne i dettagli visivi.", 422)
        front = self.cipher.decrypt(owner, item_id, current["photo_encrypted"])
        back = (self.cipher.decrypt(owner, f"{item_id}:back", current["photo_back_encrypted"])
                if current.get("photo_back_encrypted") else None)
        photo = combine_wardrobe_views(front, back)
        if not hmac.compare_digest(body.photo_sha256, photo_signature(photo)):
            raise WardrobeError("La foto è cambiata. Analizza di nuovo.", 409)

        profile = body.model_dump(exclude={"revision", "photo_sha256"})
        profile["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        changes = {
            "visual_profile": profile, "visual_photo_sha256": body.photo_sha256,
            "revision": body.revision + 1, "updated_at": profile["reviewed_at"],
        }
        result = await self.col.update_one(
            {"_id": current["_id"], "user_id": owner, "revision": body.revision},
            {"$set": changes},
        )
        if result.matched_count != 1:
            raise WardrobeError("Capo modificato durante la conferma.", 409)
        return self._public(owner, {**current, **changes})

    async def clear_appearance(self, owner: str, item_id: str, revision: int) -> dict:
        current = await self._load(owner, item_id)
        if current is None:
            raise WardrobeError("Capo non trovato.", 404)
        if current["revision"] != revision:
            raise WardrobeError("Capo cambiato; aggiorna e riprova.", 409)
        changes = {"visual_profile": None, "visual_photo_sha256": None,
                   "revision": revision + 1,
                   "updated_at": datetime.now(timezone.utc).isoformat()}
        result = await self.col.update_one(
            {"_id": current["_id"], "user_id": owner, "revision": revision},
            {"$set": changes},
        )
        if result.matched_count != 1:
            raise WardrobeError("Il capo è cambiato durante la modifica.", 409)
        return self._public(owner, {**current, **changes})
