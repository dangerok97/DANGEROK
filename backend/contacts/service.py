"""Minimal, permission-bound device contact index for ORA.

Only fields needed to resolve a person/business to a callable contact are
stored. No email addresses, postal addresses, notes, birthdays or photos.
Revoking device contact access deletes the server-side index.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List


COLLECTION = "contacts"
CONNECTOR_ID = "contacts_device"
CAPABILITY = "contacts.read"
PURPOSE = "name_resolution"
MAX_CONTACTS = 2000
MAX_PHONES = 4
MAX_ALIASES = 6


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _contact_id(owner_id: str, device_contact_id: str) -> str:
    raw = f"{owner_id}|{device_contact_id}".encode("utf-8")
    return "contact_" + hashlib.sha256(raw).hexdigest()[:24]


class DeviceContactsService:
    def __init__(self, db):
        self.db = db
        self.col = db[COLLECTION]

    async def ensure_indexes(self) -> None:
        await self.col.create_index([("user_id", 1), ("id", 1)], unique=True)
        await self.col.create_index([("user_id", 1), ("name", 1)])

    async def sync_snapshot(
        self,
        owner_id: str,
        *,
        permission: str,
        contacts: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        state = str(permission or "").strip().lower()
        if state not in ("granted", "limited"):
            await self._disable(owner_id, reason=f"device_contacts_{state or 'disabled'}")
            return {
                "ok": True,
                "permission": state or "disabled",
                "stored": 0,
                "deleted": True,
            }

        await self._grant(owner_id, state)
        await self.ensure_indexes()

        from preparation.contacts import _clean_number

        kept: List[str] = []
        stored = 0
        for raw in list(contacts or [])[:MAX_CONTACTS]:
            if not isinstance(raw, dict):
                continue
            device_id = str(raw.get("device_contact_id") or "").strip()
            if not device_id:
                continue
            name = " ".join(str(raw.get("name") or "").split())[:160]
            organization = " ".join(str(raw.get("organization") or "").split())[:160]
            aliases = []
            for value in raw.get("aliases") or []:
                alias = " ".join(str(value or "").split())[:120]
                if alias and alias not in aliases:
                    aliases.append(alias)
                if len(aliases) >= MAX_ALIASES:
                    break
            phones = []
            for value in raw.get("phones") or []:
                candidate = value.get("number") if isinstance(value, dict) else value
                number = _clean_number(str(candidate or ""))
                if number and number not in phones:
                    phones.append(number)
                if len(phones) >= MAX_PHONES:
                    break
            if not phones or not (name or organization):
                continue

            cid = _contact_id(owner_id, device_id)
            kept.append(cid)
            await self.col.update_one(
                {"user_id": owner_id, "id": cid},
                {"$set": {
                    "id": cid,
                    "user_id": owner_id,
                    "name": name or organization,
                    "organization": organization,
                    "aliases": aliases,
                    "phones": phones,
                    "phone": phones[0],
                    "kind": "business" if organization and not name else "person",
                    "source": "device_address_book",
                    "permission_scope": state,
                    "synced_at": _now_iso(),
                }},
                upsert=True,
            )
            stored += 1

        query: Dict[str, Any] = {"user_id": owner_id}
        if kept:
            query["id"] = {"$nin": kept}
        removed = await self.col.delete_many(query)
        return {
            "ok": True,
            "permission": state,
            "stored": stored,
            "removed": int(getattr(removed, "deleted_count", 0) or 0),
            "truncated": len(contacts or []) > MAX_CONTACTS,
        }

    async def status(self, owner_id: str) -> Dict[str, Any]:
        permitted = False
        try:
            from permissions.service import PermissionService
            permitted = bool(await PermissionService(self.db).check_access(
                user_id=owner_id,
                capability_id=CAPABILITY,
                connector_id=CONNECTOR_ID,
            ))
        except Exception:
            permitted = False
        count = await self.col.count_documents({"user_id": owner_id}) if permitted else 0
        return {"ok": True, "permitted": permitted, "contacts": int(count)}

    async def _grant(self, owner_id: str, state: str) -> None:
        from permissions.service import PermissionService
        await PermissionService(self.db).grant(
            user_id=owner_id,
            capability_id=CAPABILITY,
            connector_id=CONNECTOR_ID,
            purpose_id=PURPOSE,
            scopes=["device_address_book", state],
            actor_type="user",
        )

    async def _disable(self, owner_id: str, *, reason: str) -> None:
        try:
            from permissions.service import PermissionService
            await PermissionService(self.db).revoke(
                user_id=owner_id,
                capability_id=CAPABILITY,
                connector_id=CONNECTOR_ID,
                reason=reason[:120],
                actor_type="user",
            )
        finally:
            await self.col.delete_many({"user_id": owner_id})
