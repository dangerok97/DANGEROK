"""Shared, versioned exploded models. No photographs or arbitrary executable recipes.

A recipe is actual separable geometry in illustrative units, not a list of icons.
Mongo owns the catalog and build leases; process memory is never its authority.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pymongo import ReturnDocument
from vision_seed_library import common_recipes, canonical_key, model_metadata

SCHEMA_VERSION = 1
SHAPES = ("shell", "board", "keypad", "cylinder", "spring", "cone", "bottle", "ring", "box")
MODELS = "vision_catalog_models"
VERSIONS = "vision_catalog_versions"
JOBS = "vision_build_jobs"
QUOTAS = "vision_catalog_quotas"


def now():
    return datetime.now(timezone.utc)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:28]


class GeometryPart(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    name: str = Field(min_length=1, max_length=70)
    function: str = Field(min_length=1, max_length=260)
    how_it_works: str = Field(min_length=1, max_length=380)
    shape: Literal["shell", "board", "keypad", "cylinder", "spring", "cone", "bottle", "ring", "box"]
    size: tuple[float, float, float]
    assembled: tuple[float, float, float]
    exploded: tuple[float, float, float]
    evidence: Literal["typical"] = "typical"

    @field_validator("size")
    @classmethod
    def valid_size(cls, value):
        if any(not 0.1 <= n <= 250 for n in value):
            raise ValueError("Geometry dimensions outside renderer budget")
        return value

    @field_validator("assembled", "exploded")
    @classmethod
    def bounded_transform(cls, value):
        if any(abs(n) > 500 for n in value):
            raise ValueError("Transform outside renderer budget")
        return value


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal[1] = 1
    canonical_key: str = Field(pattern=r"^[a-z][a-z_]{2,47}$")
    title: str = Field(min_length=2, max_length=70)
    evidence_level: Literal["illustrative"] = "illustrative"
    match_scope: Literal["family"] = "family"
    units: Literal["illustrative"] = "illustrative"
    parts: list[GeometryPart] = Field(min_length=2, max_length=12)
    limitations: str = Field(min_length=10, max_length=400)

    @model_validator(mode="after")
    def unique_and_separable(self):
        keys = [p.key for p in self.parts]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate part identifiers")
        if len({p.exploded for p in self.parts}) != len(self.parts):
            raise ValueError("Exploded parts need distinct positions")
        if all(p.assembled == p.exploded for p in self.parts):
            raise ValueError("A static assembly is not an exploded model")
        # Geometry can be checked automatically; physical truth cannot.
        return self


def part(key, name, function, how, shape, size, assembled, exploded):
    return dict(key=key, name=name, function=function, how_it_works=how,
                shape=shape, size=size, assembled=assembled, exploded=exploded,
                evidence="typical")


def seed(key, title, parts):
    return Manifest(canonical_key=key, title=title, parts=parts,
                    limitations="Schema educativo di una famiglia: proporzioni indicative, componenti principali tipici. Non verifica marca, revisione o interno dell'esemplare inquadrato.")


def seeds() -> list[Manifest]:
    """Original procedural recipes; no copied CAD, photographs or model claims."""
    return [
        seed("remote_control", "Telecomando a infrarossi", [
            part("front_shell", "Scocca frontale", "Protegge e sostiene i comandi.", "Le aperture lasciano passare i pulsanti. La forma mostrata è indicativa.", "shell", (38, 152, 4), (0, 0, 7), (-148, 0, 18)),
            part("keypad", "Membrana dei pulsanti", "Trasmette la pressione delle dita ai contatti.", "In molti telecomandi una membrana flessibile porta superfici conduttive sotto i tasti.", "keypad", (33, 141, 3), (0, 0, 3), (-98, 0, 10)),
            part("pcb", "Scheda elettronica", "Collega i comandi al circuito di controllo.", "Piste conduttive e componenti elaborano il pulsante premuto. Il circuito preciso dipende dal modello.", "board", (31, 137, 2), (0, 0, 0), (-48, 0, 4)),
            part("emitter", "Emettitore a infrarossi", "Invia un segnale luminoso al dispositivo controllato.", "Nei telecomandi IR un LED emette impulsi codificati. Non tutti i telecomandi usano solo infrarossi.", "cylinder", (5, 8, 5), (0, 70, 0), (0, 48, 4)),
            part("rear_shell", "Guscio posteriore", "Sostiene l'elettronica e il vano di alimentazione.", "Le due metà formano l'involucro. Incastri, viti e disposizione interna variano.", "shell", (38, 152, 8), (0, 0, -6), (43, 0, -4)),
            part("battery_a", "Prima pila", "Fornisce energia al circuito.", "È raffigurata una configurazione tipica a due pile, non verificata sul tuo telecomando.", "cylinder", (9, 37, 9), (-7, -43, -3), (87, -22, 12)),
            part("battery_b", "Seconda pila", "Completa l'alimentazione nella configurazione illustrata.", "Numero, formato e orientamento delle pile devono essere controllati sul dispositivo reale.", "cylinder", (9, 37, 9), (7, -43, -3), (108, -22, 12)),
            part("cover", "Sportello del vano pile", "Chiude il vano di alimentazione.", "Lo sportello trattiene e protegge il contenuto del vano senza essere una parte del circuito.", "shell", (33, 58, 2), (0, -43, -11), (154, -20, 8)),
        ]),
        seed("click_pen", "Penna a scatto", [
            part("barrel", "Corpo", "Permette di impugnare la penna e contiene la ricarica.", "È raffigurato un corpo cavo; forma e materiali dipendono dalla penna.", "cylinder", (11, 93, 11), (0, 0, 0), (-63, 0, 0)),
            part("refill", "Ricarica", "Contiene l'inchiostro e la punta scrivente.", "Una tipica ricarica a sfera porta l'inchiostro alla piccola sfera della punta.", "cylinder", (3, 117, 3), (0, -7, 0), (-25, 0, 5)),
            part("spring", "Molla", "Contribuisce al ritorno del meccanismo.", "La molla si comprime e restituisce energia elastica; la sua posizione varia fra modelli.", "spring", (6, 17, 6), (0, -45, 0), (9, -28, 0)),
            part("tip", "Puntale", "Guida e protegge l'uscita della punta.", "Un foro mantiene la punta in posizione mentre scrivi.", "cone", (11, 20, 11), (0, -55, 0), (41, -42, 0)),
            part("click", "Pulsante e meccanismo a scatto", "Alternano punta estratta e rientrata.", "Il meccanismo illustrato è semplificato: camme e fermi reali richiedono una verifica sul modello.", "cylinder", (9, 18, 9), (0, 54, 0), (56, 38, 0)),
        ]),
        seed("water_bottle", "Bottiglia con tappo", [
            part("body", "Corpo della bottiglia", "Contiene il liquido.", "Il collo restringe l'apertura. Lo schema rappresenta una bottiglia generica, senza identificarne materiale o capacità.", "bottle", (52, 144, 52), (0, 0, 0), (-42, -8, 0)),
            part("cap", "Tappo", "Chiude l'apertura.", "Nella variante illustrata il tappo si avvita al collo; esistono chiusure differenti.", "cylinder", (25, 15, 25), (0, 80, 0), (35, 51, 7)),
            part("ring", "Anello di prima apertura", "Può rendere evidente la prima apertura.", "È una parte tipica di alcune bottiglie commerciali, non di tutte le borracce o bottiglie.", "ring", (26, 4, 26), (0, 71, 0), (44, 11, 4)),
        ]),
        seed("computer_mouse", "Mouse ottico", [
            part("top", "Guscio superiore e pulsanti", "Trasmette i clic e protegge i componenti.", "Le zone flessibili dei pulsanti agiscono su interruttori. La suddivisione varia fra mouse.", "shell", (60, 98, 17), (0, 0, 11), (-93, 0, 18)),
            part("wheel", "Rotella", "Permette lo scorrimento.", "Un sistema di rilevamento misura la rotazione; il tipo di sensore dipende dal modello.", "ring", (14, 10, 14), (0, 25, 8), (-43, 21, 15)),
            part("board", "Scheda elettronica", "Raccoglie movimento e comandi.", "Il circuito elabora i segnali dei sensori e dei pulsanti. Il disegno delle piste è stilizzato.", "board", (43, 68, 3), (0, 0, 0), (9, 0, 4)),
            part("sensor", "Gruppo ottico", "Rileva lo spostamento sulla superficie.", "Nei mouse ottici l'illuminazione e un sensore osservano variazioni della superficie.", "box", (12, 15, 6), (0, 0, -5), (57, 21, 10)),
            part("base", "Base", "Sostiene i componenti e scorre sul piano.", "L'apertura inferiore consente al gruppo ottico di osservare la superficie. Alimentazione e collegamento non sono verificati qui.", "shell", (60, 98, 7), (0, 0, -9), (109, 0, 0)),
        ]),
        seed("flashlight", "Torcia portatile", [
            part("body", "Corpo", "Contiene e protegge le parti interne.", "È rappresentata una torcia cilindrica generica. Tenuta, materiale e forma non sono verificati.", "cylinder", (25, 90, 25), (0, 0, 0), (-79, 0, 0)),
            part("battery", "Batteria", "Fornisce energia.", "Il tipo di alimentazione dipende dalla torcia. Non aprire, forare o modificare le celle.", "cylinder", (17, 58, 17), (0, -6, 0), (-38, -8, 10)),
            part("led", "Gruppo luminoso", "Converte energia elettrica in luce.", "Lo schema mostra un gruppo LED tipico. Driver, dissipazione e prestazioni variano.", "board", (17, 5, 17), (0, 41, 0), (0, 27, 0)),
            part("reflector", "Riflettore", "Aiuta a dirigere la luce.", "Una superficie sagomata modifica il fascio; altre torce impiegano ottiche differenti.", "cone", (23, 18, 23), (0, 49, 0), (39, 24, 0)),
            part("lens", "Protezione frontale", "Protegge l'ottica.", "È una rappresentazione semplificata dell'elemento anteriore; non ne determina il materiale.", "ring", (25, 4, 25), (0, 61, 0), (78, 24, 0)),
            part("tail", "Chiusura posteriore", "Chiude il corpo della torcia.", "L'interruttore può trovarsi qui oppure sul corpo. Non è deducibile con certezza da questo schema.", "cylinder", (25, 9, 25), (0, -50, 0), (85, -41, 0)),
        ]),
    ] + [Manifest.model_validate(row["manifest"]) for row in common_recipes()]


class CatalogLimit(Exception):
    pass


class CatalogService:
    def __init__(self, db):
        self.db = db
        self._ready = False
        self._init_lock = asyncio.Lock()

    async def initialize(self):
        if self._ready:
            return
        async with self._init_lock:
            if self._ready:
                return
            await self.db[MODELS].create_index([("scope", 1), ("status", 1), ("canonical_key", 1)])
            await self.db[QUOTAS].create_index("expires_at", expireAfterSeconds=0)
            await self.db[JOBS].create_index([("scope", 1), ("state", 1)])
            for manifest in seeds():
                await self.install_seed(manifest)
            self._ready = True

    @staticmethod
    def private_scope(user_id):
        return "private:" + digest(user_id)

    @staticmethod
    def model_id(key, scope):
        return "vx_" + digest(scope + ":" + key)

    async def quota(self, subject, kind, limit, window_seconds):
        t = now()
        bucket = int(t.timestamp()) // window_seconds
        key = digest(f"{subject}|{kind}|{bucket}")
        record = await self.db[QUOTAS].find_one_and_update(
            {"_id": key},
            {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": t + timedelta(seconds=window_seconds * 2)}},
            upsert=True, return_document=ReturnDocument.AFTER,
        )
        if record["count"] > limit:
            raise CatalogLimit("Limite di analisi raggiunto. Riprova fra poco.")

    async def _store(self, manifest, scope, source, *, insert_only=False):
        body = manifest.model_dump(mode="json")
        model_id = self.model_id(manifest.canonical_key, scope)
        revision = "vxv_" + digest(model_id + json.dumps(body, sort_keys=True, separators=(",", ":")))
        await self.db[VERSIONS].update_one({"_id": revision}, {"$setOnInsert": {
            "model_id": model_id, "manifest": body, "scope": scope,
            "source_type": source, "created_at": now(),
        }}, upsert=True)
        # Neither reinitialisation nor a repeat generation can resurrect a retired model.
        await self.db[MODELS].update_one({"_id": model_id}, {"$setOnInsert": {
            "canonical_key": manifest.canonical_key, "title": manifest.title,
            "scope": scope, "status": "published", "evidence_level": "illustrative",
            "current_version": revision, "source_type": source, "created_at": now(),
        }}, upsert=True)
        return await self.read(model_id, scope=scope)

    async def install_seed(self, manifest):
        """Promote only a generated public head via CAS; keep old versions and tombstones."""
        stored = await self._store(manifest, "shared", "seed", insert_only=True)
        if not stored or stored["source_type"] != "generated":
            return
        body = manifest.model_dump(mode="json")
        revision = "vxv_" + digest(stored["model_id"] + json.dumps(body, sort_keys=True, separators=(",", ":")))
        await self.db[MODELS].update_one({
            "_id": stored["model_id"], "scope": "shared", "status": "published",
            "source_type": "generated", "current_version": stored["version_id"],
        }, {"$set": {"current_version": revision, "source_type": "seed",
                     "title": manifest.title, "updated_at": now()}})

    async def read(self, model_id, *, scope):
        head = await self.db[MODELS].find_one({"_id": model_id, "scope": scope, "status": "published"})
        if not head:
            return None
        version = await self.db[VERSIONS].find_one({"_id": head["current_version"], "model_id": model_id, "scope": scope})
        if not version:
            return None
        # Old or corrupt data must still satisfy the current renderer contract.
        manifest = Manifest.model_validate(version["manifest"]).model_dump(mode="json")
        return {"model_id": model_id, "version_id": version["_id"], "manifest": manifest,
                "source_type": version["source_type"], "shared": scope == "shared",
                "sources": model_metadata(manifest["canonical_key"])["sources"] if version["source_type"] == "seed" else []}

    async def find(self, key, user_id):
        key = canonical_key(key)
        for scope in (self.private_scope(user_id), "shared"):
            model = await self.read(self.model_id(key, scope), scope=scope)
            if model:
                return model
        return None

    async def list_models(self, user_id):
        await self.initialize()
        rows = await self.db[MODELS].find({
            "scope": {"$in": ["shared", self.private_scope(user_id)]}, "status": "published",
        }, {"_id": 1, "title": 1, "canonical_key": 1, "current_version": 1,
            "source_type": 1, "scope": 1}).sort([("source_type", -1), ("canonical_key", 1)]).limit(500).to_list(500)
        return [{"model_id": r["_id"], "title": r["title"], "canonical_key": r["canonical_key"],
                 "version_id": r["current_version"], "source_type": r["source_type"],
                 "shared": r["scope"] == "shared", "category": model_metadata(r["canonical_key"])["category"],
                 "aliases": model_metadata(r["canonical_key"])["aliases"]} for r in rows]

    async def resolve(self, *, key: str, title: str, user_id: str,
                      generator: Callable[[], Awaitable[dict]] | None = None,
                      contribute=False):
        await self.initialize()
        key = canonical_key(key)
        if not re.fullmatch(r"[a-z][a-z_]{2,47}", key):
            return {"status": "unknown", "reason": "Identificazione non sufficientemente precisa."}
        found = await self.find(key, user_id)
        if found:
            return {"status": "family", "cache_hit": True, "generation_used": False, **found}
        if generator is None:
            return {"status": "unknown", "reason": "Oggetto non ancora presente nel catalogo."}
        # Generated recipes are generic shared knowledge. Legacy client flags do not control this.
        # Do not republish previously-private records; existing owner isolation remains intact.
        scope = "shared"
        model_id = self.model_id(key, scope)
        # Tombstones forbid implicit republication after moderation.
        if await self.db[MODELS].find_one({"_id": model_id, "status": {"$ne": "published"}}):
            return {"status": "unknown", "reason": "Questo schema è in revisione."}
        job_id = "vxj_" + digest(model_id)
        t = now()
        await self.db[JOBS].update_one({"_id": job_id}, {"$setOnInsert": {
            "scope": scope, "model_id": model_id, "canonical_key": key,
            "state": "queued", "retry_after": t, "attempts": 0, "created_at": t,
        }}, upsert=True)
        token = uuid.uuid4().hex
        claimed = await self.db[JOBS].find_one_and_update({"_id": job_id, "$or": [
            {"state": {"$in": ["queued", "failed"]}, "retry_after": {"$lte": t}},
            {"state": "building", "lease_until": {"$lte": t}},
        ]}, {"$set": {"state": "building", "lease_token": token,
                       "lease_until": t + timedelta(seconds=45), "updated_at": t},
              "$inc": {"attempts": 1}}, return_document=ReturnDocument.AFTER)
        if not claimed:
            # The winner may have published between our first read and lease claim.
            found = await self.find(key, user_id)
            if found:
                return {"status": "family", "cache_hit": True, "generation_used": False, **found}
            return {"status": "building", "job_id": job_id, "retry_after_seconds": 4}
        try:
            await self.quota(user_id, "generation-day", 8, 86400)
            await self.quota("global", "generation-day", 60, 86400)
            raw = await asyncio.wait_for(generator(), timeout=24)
            candidate = Manifest.model_validate(raw)
            if candidate.canonical_key != key:
                raise ValueError("Generated identity mismatch")
            # Acquire a publication fence while the original lease is still valid.
            fenced = await self.db[JOBS].find_one_and_update({
                "_id": job_id, "state": "building", "lease_token": token,
                "lease_until": {"$gt": now()},
            }, {"$set": {"lease_until": now() + timedelta(seconds=20)}}, return_document=ReturnDocument.AFTER)
            if not fenced:
                return {"status": "building", "job_id": job_id, "retry_after_seconds": 4}
            stored = await self._store(candidate, scope, "generated")
            if not stored:
                raise ValueError("Model was withheld")
            await self.db[JOBS].update_one({"_id": job_id, "lease_token": token}, {
                "$set": {"state": "ready", "version_id": stored["version_id"], "updated_at": now()},
                "$unset": {"lease_token": "", "lease_until": ""},
            })
            return {"status": "family", "cache_hit": False, "generation_used": True, **stored}
        except BaseException as exc:
            await self.db[JOBS].update_one({"_id": job_id, "lease_token": token}, {
                "$set": {"state": "failed", "retry_after": now() + timedelta(seconds=30),
                         "error": "Ricostruzione non disponibile o non valida.", "updated_at": now()},
                "$unset": {"lease_token": "", "lease_until": ""},
            })
            if isinstance(exc, (asyncio.CancelledError, CatalogLimit)):
                raise
            return {"status": "unknown", "reason": "Non riesco ancora a costruire uno schema affidabile di questo oggetto."}

    async def job_result(self, job_id, user_id):
        row = await self.db[JOBS].find_one({"_id": job_id,
            "scope": {"$in": ["shared", self.private_scope(user_id)]}})
        if not row:
            return None
        model = await self.read(row["model_id"], scope=row["scope"])
        if model:
            return {"status": "family", "cache_hit": True, "generation_used": False, **model}
        if row["state"] == "building" and row.get("lease_until"):
            deadline = row["lease_until"]
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            if deadline < now():
                return {"status": "unknown", "reason": "Analisi interrotta: inquadra di nuovo per riprenderla."}
        if row["state"] == "failed":
            return {"status": "unknown", "reason": row["error"]}
        return {"status": "building", "job_id": job_id, "retry_after_seconds": 4}
