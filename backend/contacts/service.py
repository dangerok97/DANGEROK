from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from preparation.contacts import _clean_number

logger = logging.getLogger("ora.contacts")

CONTACTS = "contacts"
STATE = "contacts_device_state"
CONNECTOR_ID = "contacts_device"
CAPABILITY_ID = "contacts.read"
MAX_CONTACTS = 1500
MAX_NUMBERS = 3
MAX_ALIASES = 4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_contact_id(owner_id: str, native_id: str, name: str, phones: List[str]) -> str:
    raw = "|".join([owner_id, native_id.strip(), name.strip().lower(), *(phones[:1])])
    return "contact_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _clean_contact(owner_id: str, raw: Dict[str, Any]) -> Dict[str, Any] | None:
    name = " ".join(str(raw.get("name") or "").split())[:160]
    organization = " ".join(str(raw.get("organization") or "").split())[:160]
    aliases = [
        " ".join(str(a).split())[:120]
        for a in (raw.get("aliases") or [])[:MAX_ALIASES]
        if str(a).strip()
    ]
    phones: List[str] = []
    for value in list(raw.get("phones") or [])[:MAX_NUMBERS]:
        cleaned = _clean_number(str(value or ""))
        if cleaned and cleaned not in phones:
            phones.append(cleaned)
    if not phones or not (name or organization):
        return None
    native_id = str(raw.get("id") or "")[:120]
    contact_id = _stable_contact_id(owner_id, native_id, name or organization, phones)
    return {
        "id": contact_id,
        "user_id": owner_id,
        "name": name or organization,
        "organization": organization,
        "aliases": aliases,
        "phone": phones[0],
        "phones": phones,
        "kind": str(raw.get("kind") or "person")[:24],
        "source": "device",
        "updated_at": _now_iso(),
    }


async def sync_device_contacts(
    db,
    owner_id: str,
    *,
    contacts: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    cleaned: List[Dict[str, Any]] = []
    seen_ids = set()
    for raw in list(contacts or [])[:MAX_CONTACTS]:
        if not isinstance(raw, dict):
            continue
        item = _clean_contact(owner_id, raw)
        if item is not None and item["id"] not in seen_ids:
            seen_ids.add(item["id"])
            cleaned.append(item)

    # The request is a complete snapshot. Replacing owner-scoped rows makes
    # deletions/revocations truthful instead of leaving old phone numbers alive.
    await db[CONTACTS].delete_many({"user_id": owner_id})
    if cleaned:
        await db[CONTACTS].insert_many(cleaned)

    now = _now_iso()
    await db[STATE].update_one(
        {"user_id": owner_id},
        {"$set": {
            "user_id": owner_id,
            "status": "connected",
            "synced_at": now,
            "contact_count": len(cleaned),
        }},
        upsert=True,
    )
    await db.connector_instances.update_one(
        {"user_id": owner_id, "connector_id": CONNECTOR_ID},
        {"$set": {
            "id": f"{CONNECTOR_ID}:{owner_id}",
            "user_id": owner_id,
            "connector_id": CONNECTOR_ID,
            "status": "connected",
            "updated_at": now,
            "last_sync_at": now,
        }},
        upsert=True,
    )

    from permissions.service import PermissionService
    await PermissionService(db).grant(
        user_id=owner_id,
        capability_id=CAPABILITY_ID,
        connector_id=CONNECTOR_ID,
        purpose_id="name_resolution",
        scopes=["read_selected_fields"],
        actor_type="user",
    )
    return {"status": "connected", "synced_at": now, "contact_count": len(cleaned)}


async def revoke_device_contacts(db, owner_id: str) -> Dict[str, Any]:
    await db[CONTACTS].delete_many({"user_id": owner_id})
    now = _now_iso()
    await db[STATE].update_one(
        {"user_id": owner_id},
        {"$set": {
            "user_id": owner_id,
            "status": "disconnected",
            "synced_at": now,
            "contact_count": 0,
        }},
        upsert=True,
    )
    await db.connector_instances.update_one(
        {"user_id": owner_id, "connector_id": CONNECTOR_ID},
        {"$set": {"status": "disconnected", "updated_at": now}},
    )
    try:
        from permissions.service import PermissionService
        await PermissionService(db).revoke(
            user_id=owner_id,
            capability_id=CAPABILITY_ID,
            connector_id=CONNECTOR_ID,
            reason="device_contacts_revoked",
            actor_type="user",
        )
    except Exception as exc:
        logger.info("contacts permission revoke soft-fail: %s", type(exc).__name__)
    return {"status": "disconnected", "synced_at": now, "contact_count": 0}


async def device_contacts_state(db, owner_id: str) -> Dict[str, Any]:
    row = await db[STATE].find_one({"user_id": owner_id}, {"_id": 0})
    if row:
        return row
    return {"user_id": owner_id, "status": "disconnected", "synced_at": "", "contact_count": 0}


async def ensure_indexes(db) -> None:
    try:
        await db[CONTACTS].create_index([("user_id", 1), ("id", 1)], unique=True)
        await db[CONTACTS].create_index([("user_id", 1), ("name", 1)])
        await db[STATE].create_index("user_id", unique=True)
    except Exception:
        logger.exception("contacts indexes unavailable (non-fatal)")
