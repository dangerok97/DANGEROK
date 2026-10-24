"""Durable owner-scoped captures with idempotent creates and revision fences."""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone

from .models import (
    AddManualRoom, CreateHouseScan, HouseCapture, MAX_CAPTURE_BYTES, MAX_ROOMS, UpdateHouseScan,
)

SUMMARY_FIELDS = (
    "id", "title", "capture_id", "source", "captured_at", "created_at", "updated_at",
    "revision", "room_count", "wall_count", "verified_wall_count",
)


class HouseScanError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


async def ensure_indexes(db) -> None:
    """Additive and idempotent; the unique index also fences concurrent uploads."""
    await db.house_scans.create_index(
        [("user_id", 1), ("capture_id", 1)], unique=True, name="house_scan_owner_capture",
    )
    await db.house_scans.create_index("id", unique=True, name="house_scan_id")
    await db.house_scans.create_index(
        [("user_id", 1), ("updated_at", -1), ("id", -1)], name="house_scan_owner_updated",
    )


def _summary(record: dict) -> dict:
    return {key: record[key] for key in SUMMARY_FIELDS}


def _public(record: dict) -> dict:
    return copy.deepcopy({
        **_summary(record),
        "capture": record["capture"],
        "room_labels": record["room_labels"],
        "wall_measurements": record["wall_measurements"],
        "provenance": record["provenance"],
    })


class HouseScanService:
    def __init__(self, db):
        self.db = db
        self.col = db.house_scans
        self._ready = False

    async def ensure_ready(self):
        if not self._ready:
            await ensure_indexes(self.db)
            self._ready = True

    async def _load(self, owner: str, scan_id: str) -> dict:
        record = await self.col.find_one({"user_id": owner, "id": scan_id})
        if record is None:
            raise HouseScanError("Planimetria non trovata.", 404)
        return record

    async def list_scans(self, owner: str, *, limit: int = 50, offset: int = 0) -> dict:
        if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
            raise HouseScanError("Intervallo dell'elenco non valido.", 422)
        projection = {key: 1 for key in SUMMARY_FIELDS}
        projection["_id"] = 0
        cursor = self.col.find({"user_id": owner}, projection)
        records = await cursor.sort([("updated_at", -1), ("id", -1)]).skip(offset).to_list(length=limit + 1)
        has_more = len(records) > limit
        return {"scans": [_summary(record) for record in records[:limit]],
                "has_more": has_more, "next_offset": offset + limit if has_more else None}

    async def get(self, owner: str, scan_id: str) -> dict:
        return _public(await self._load(owner, scan_id))

    @staticmethod
    def _retry(existing: dict, digest: str) -> tuple[dict, bool]:
        if existing["capture_sha256"] != digest:
            raise HouseScanError(
                "Questo identificativo appartiene a una scansione diversa. Ripeti la scansione con un nuovo identificativo.",
                409,
            )
        # A retried upload must not undo a later room rename or verification.
        return _public(existing), False

    async def create(self, owner: str, body: CreateHouseScan) -> tuple[dict, bool]:
        capture = body.capture.model_dump(mode="json", exclude_none=True)
        canonical = json.dumps(capture, sort_keys=True, ensure_ascii=False,
                               allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(canonical) > MAX_CAPTURE_BYTES:
            raise HouseScanError("La scansione supera il limite di 2 MB.", 413)
        digest = hashlib.sha256(canonical).hexdigest()
        await self.ensure_ready()
        key = {"user_id": owner, "capture_id": body.capture.capture_id}
        existing = await self.col.find_one(key)
        if existing is not None:
            return self._retry(existing, digest)
        now = datetime.now(timezone.utc).isoformat()
        scan_id = uuid.uuid4().hex
        record = {
            "_id": scan_id, "id": scan_id, **key, "title": body.title,
            "source": capture["source"], "captured_at": capture["captured_at"],
            "created_at": now, "updated_at": now, "revision": 1,
            "room_count": len(capture["rooms"]),
            "wall_count": sum(len(room["walls"]) for room in capture["rooms"]),
            "verified_wall_count": 0,
            "capture": capture, "capture_sha256": digest,
            "room_labels": [], "wall_measurements": [],
            "provenance": {
                "source_attestation": "client_reported",
                "geometry_units": "metres",
                "transform_order": "column_major",
                "original_measurements": "scan_estimates",
            },
        }
        try:
            await self.col.insert_one(record)
        except Exception as exc:
            if getattr(exc, "code", None) != 11000:
                raise
            # The other request may have committed between our read and insert.
            existing = await self.col.find_one(key)
            if existing is None:
                raise HouseScanError("Salvataggio in conflitto. Riprova.", 409) from None
            return self._retry(existing, digest)
        return _public(record), True

    async def update(self, owner: str, scan_id: str, body: UpdateHouseScan) -> dict:
        current = await self._load(owner, scan_id)
        if current["revision"] != body.revision:
            raise HouseScanError("La planimetria è cambiata. Aggiorna e riprova.", 409)
        rooms = {room["id"]: room for room in current["capture"]["rooms"]}
        walls = {(room["id"], wall["id"]) for room in rooms.values() for wall in room["walls"]}
        # Validate every reference before writing any change.
        if any(label.room_id not in rooms for label in body.room_labels):
            raise HouseScanError("Una delle stanze indicate non appartiene alla planimetria.", 422)
        if any((item.room_id, item.wall_id) not in walls for item in body.wall_measurements):
            raise HouseScanError("Una delle pareti indicate non appartiene alla stanza.", 422)
        labels = {item["room_id"]: copy.deepcopy(item) for item in current["room_labels"]}
        measurements = {(item["room_id"], item["wall_id"]): copy.deepcopy(item)
                        for item in current["wall_measurements"]}
        now = datetime.now(timezone.utc).isoformat()
        for label in body.room_labels:
            if label.name == rooms[label.room_id]["name"]:
                labels.pop(label.room_id, None)
            else:
                labels[label.room_id] = label.model_dump()
        for measurement in body.wall_measurements:
            key = (measurement.room_id, measurement.wall_id)
            if measurement.length_m is None:
                measurements.pop(key, None)
            else:
                measurements[key] = {**measurement.model_dump(), "verified_at": now,
                                     "source": "user_verified"}
        changes = {
            "title": body.title if body.title is not None else current["title"],
            "room_labels": [labels[key] for key in sorted(labels)],
            "wall_measurements": [measurements[key] for key in sorted(measurements)],
            "verified_wall_count": len(measurements),
            "revision": body.revision + 1, "updated_at": now,
        }
        result = await self.col.update_one(
            {"user_id": owner, "id": scan_id, "revision": body.revision}, {"$set": changes},
        )
        if result.matched_count != 1:
            raise HouseScanError("La planimetria è cambiata durante il salvataggio. Aggiorna e riprova.", 409)
        return _public({**current, **changes})

    async def delete(self, owner: str, scan_id: str, revision: int) -> None:
        current = await self._load(owner, scan_id)
        if current["revision"] != revision:
            raise HouseScanError("La planimetria è cambiata. Aggiorna prima di eliminarla.", 409)
        result = await self.col.delete_one({"user_id": owner, "id": scan_id, "revision": revision})
        if result.deleted_count != 1:
            raise HouseScanError("La planimetria è cambiata durante l'eliminazione.", 409)

    # --- Rooms measured by hand -------------------------------------------

    @staticmethod
    def _digest(capture: dict) -> str:
        canonical = json.dumps(capture, sort_keys=True, ensure_ascii=False,
                               allow_nan=False, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    async def add_manual_room(self, owner: str, body: AddManualRoom) -> tuple[dict, bool]:
        from .manual import build_room

        room = build_room(body.room)
        now = datetime.now(timezone.utc).isoformat()
        if body.scan_id is None:
            capture = HouseCapture.model_validate({
                "schema_version": 1, "capture_id": "manual-" + uuid.uuid4().hex,
                "source": "manual", "captured_at": now, "rooms": [room],
            }).model_dump(mode="json", exclude_none=True)
            await self.ensure_ready()
            scan_id = uuid.uuid4().hex
            record = {
                "_id": scan_id, "id": scan_id, "user_id": owner,
                "capture_id": capture["capture_id"], "title": body.title,
                "source": "manual", "captured_at": capture["captured_at"],
                "created_at": now, "updated_at": now, "revision": 1,
                "room_count": 1, "wall_count": len(room["walls"]),
                "verified_wall_count": 0,
                "capture": capture, "capture_sha256": self._digest(capture),
                "room_labels": [], "wall_measurements": [],
                "provenance": {
                    "source_attestation": "user_entered",
                    "geometry_units": "metres",
                    "transform_order": "column_major",
                    "original_measurements": "user_entered",
                },
            }
            await self.col.insert_one(record)
            return _public(record), True

        current = await self._load(owner, body.scan_id)
        if current.get("source") != "manual":
            raise HouseScanError("A un rilievo LiDAR non si aggiungono stanze a mano: crea una nuova pianta.", 409)
        if current["revision"] != body.revision:
            raise HouseScanError("La planimetria è cambiata. Aggiorna e riprova.", 409)
        rooms = list(current["capture"]["rooms"])
        if len(rooms) >= MAX_ROOMS:
            raise HouseScanError(f"Una pianta può avere al massimo {MAX_ROOMS} stanze.", 422)
        capture = HouseCapture.model_validate({**current["capture"], "rooms": [*rooms, room]}).model_dump(
            mode="json", exclude_none=True)
        changes = {
            "capture": capture, "capture_sha256": self._digest(capture),
            "room_count": len(capture["rooms"]),
            "wall_count": sum(len(r["walls"]) for r in capture["rooms"]),
            "revision": body.revision + 1, "updated_at": now,
        }
        result = await self.col.update_one(
            {"user_id": owner, "id": body.scan_id, "revision": body.revision}, {"$set": changes},
        )
        if result.matched_count != 1:
            raise HouseScanError("La planimetria è cambiata durante il salvataggio. Aggiorna e riprova.", 409)
        return _public({**current, **changes}), False

    async def remove_manual_room(self, owner: str, scan_id: str, room_id: str, revision: int) -> dict:
        current = await self._load(owner, scan_id)
        if current.get("source") != "manual":
            raise HouseScanError("Le stanze di un rilievo LiDAR non si tolgono una per una.", 409)
        if current["revision"] != revision:
            raise HouseScanError("La planimetria è cambiata. Aggiorna e riprova.", 409)
        rooms = [r for r in current["capture"]["rooms"] if r["id"] != room_id]
        if len(rooms) == len(current["capture"]["rooms"]):
            raise HouseScanError("Stanza non trovata in questa pianta.", 404)
        if not rooms:
            raise HouseScanError("È l'unica stanza: elimina la pianta intera.", 409)
        capture = {**current["capture"], "rooms": rooms}
        measurements = [m for m in current["wall_measurements"] if m["room_id"] != room_id]
        changes = {
            "capture": capture, "capture_sha256": self._digest(capture),
            "room_count": len(rooms),
            "wall_count": sum(len(r["walls"]) for r in rooms),
            "room_labels": [l for l in current["room_labels"] if l["room_id"] != room_id],
            "wall_measurements": measurements,
            "verified_wall_count": len(measurements),
            "revision": revision + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        result = await self.col.update_one(
            {"user_id": owner, "id": scan_id, "revision": revision}, {"$set": changes},
        )
        if result.matched_count != 1:
            raise HouseScanError("La planimetria è cambiata durante il salvataggio. Aggiorna e riprova.", 409)
        return _public({**current, **changes})
