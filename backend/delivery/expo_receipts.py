"""Durable Expo push receipt verification, separate from a device-delivery claim.

Expo tickets prove API acceptance only; Expo receipts can verify handoff to
APNs/FCM, never whether the phone displayed a notification. Store no tokens,
message bodies, source facts, or other personal content in this audit ledger.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import uuid

from pymongo import ReturnDocument

logger = logging.getLogger("ora.delivery.expo_receipts")

COLLECTION = "expo_push_receipts"
RECEIPTS_ENDPOINT = "https://exp.host/--/api/v2/push/getReceipts"
FIRST_CHECK_MINUTES = 15
LEASE_SECONDS = 90
MAX_BATCH = 20
LIFETIME_HOURS = 24
RETENTION_HOURS = 72


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(owner_id: str, plan_id: str, ticket_id: str) -> str:
    digest = hashlib.sha256(
        f"{owner_id}|{plan_id}|{ticket_id}".encode("utf-8")
    ).hexdigest()[:28]
    return "epr_" + digest


class ExpoReceiptAudit:
    def __init__(self, db, *, timeout: float = 10):
        self.db = db
        self.timeout = timeout

    async def ensure_indexes(self) -> None:
        collection = self.db[COLLECTION]
        await collection.create_index("id", unique=True)
        await collection.create_index([("state", 1), ("next_check_at", 1)])
        await collection.create_index([("owner_id", 1), ("plan_id", 1)])
        await collection.create_index("expires_at", expireAfterSeconds=0)

    async def track(
        self, owner_id: str, plan_id: str, tickets: list[dict],
        *, now: Optional[datetime] = None,
    ) -> int:
        """Record successful Expo tickets before their 15-minute receipt check."""
        if not owner_id or not plan_id:
            return 0
        moment = now or _now()
        created = 0
        for ticket in tickets[:MAX_BATCH]:
            ticket_id = str(ticket.get("ticket_id") or "")
            endpoint_id = str(ticket.get("endpoint_id") or "")
            if not (1 <= len(ticket_id) <= 200 and endpoint_id.startswith("pep_")
                    and len(endpoint_id) <= 80):
                continue
            doc = {
                "id": _key(owner_id, plan_id, ticket_id),
                "owner_id": owner_id, "plan_id": plan_id,
                "endpoint_id": endpoint_id,
                "ticket_id": ticket_id,  # Expo-generated opaque receipt ID.
                "state": "pending",
                "accepted_at": moment.isoformat(),
                "next_check_at": (
                    moment + timedelta(minutes=FIRST_CHECK_MINUTES)
                ).isoformat(),
                "lease_until": "", "lease_token": "",
                "checks": 0, "error_code": "",
                "expires_at": moment + timedelta(hours=RETENTION_HOURS),
            }
            result = await self.db[COLLECTION].update_one(
                {"id": doc["id"]}, {"$setOnInsert": doc}, upsert=True
            )
            created += int(bool(result.upserted_id))
        return created

    async def _post_receipts(self, ids: list[str]) -> dict:
        """Only permitted external read: one bounded Expo receipts API call."""
        import httpx

        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=False
        ) as client:
            response = await client.post(
                RECEIPTS_ENDPOINT,
                json={"ids": ids},
                headers={"accept": "application/json",
                         "content-type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        if (not isinstance(data, dict) or not isinstance(data.get("data"), dict)
                or data.get("errors")):
            raise ValueError("INVALID_EXPO_RECEIPTS_RESPONSE")
        return data["data"]

    async def _claim(self, *, now: datetime) -> Optional[dict]:
        moment = now.isoformat()
        token = uuid.uuid4().hex
        return await self.db[COLLECTION].find_one_and_update(
            {
                "state": "pending",
                "next_check_at": {"$lte": moment},
                "$or": [
                    {"lease_until": {"$exists": False}},
                    {"lease_until": {"$lte": moment}},
                ],
            },
            {"$set": {
                "lease_token": token,
                "lease_until": (
                    now + timedelta(seconds=LEASE_SECONDS)
                ).isoformat(),
            }},
            sort=[("next_check_at", 1), ("id", 1)],
            return_document=ReturnDocument.AFTER,
        )

    async def _finish(
        self, row: dict, *, now: datetime, state: str,
        error_code: str = "",
    ) -> bool:
        query = {
            "_id": row["_id"],
            "owner_id": row["owner_id"],
            "state": "pending", "lease_token": row["lease_token"],
        }
        changes: dict[str, Any] = {
            "state": state, "last_checked_at": now.isoformat(),
            "error_code": error_code[:64],
            "lease_until": "", "lease_token": "",
        }
        if state == "pending":
            attempts = min(5, int(row.get("checks") or 0))
            minutes = min(60, 5 * (2 ** attempts))
            changes["next_check_at"] = (
                now + timedelta(minutes=minutes)
            ).isoformat()
        else:
            changes["next_check_at"] = None
        result = await self.db[COLLECTION].update_one(
            query, {"$set": changes, "$inc": {"checks": 1}}
        )
        return bool(result.modified_count)

    async def run_due(
        self, *, now: Optional[datetime] = None, limit: int = MAX_BATCH,
    ) -> dict[str, int]:
        moment = now or _now()
        outcome = {
            "claimed": 0, "handoff_confirmed": 0,
            "rejected": 0, "unconfirmed": 0, "retrying": 0,
        }
        items = []
        for _ in range(max(1, min(int(limit or 1), MAX_BATCH))):
            claimed = await self._claim(now=moment)
            if claimed is None:
                break
            items.append(claimed)
        if not items:
            return outcome
        outcome["claimed"] = len(items)

        response = {}
        failed = False
        try:
            response = await self._post_receipts([item["ticket_id"] for item in items])
        except Exception as exc:
            failed = True
            logger.info("expo receipt audit retry reason=%s", type(exc).__name__)

        for row in items:
            expired = (
                moment - datetime.fromisoformat(row["accepted_at"])
            ) >= timedelta(hours=LIFETIME_HOURS)
            receipt = response.get(row["ticket_id"])
            if not isinstance(receipt, dict) or receipt.get("status") not in ("ok", "error"):
                state = "unconfirmed" if expired else "pending"
                reason = "receipts_unavailable" if failed else "receipt_pending"
            elif receipt["status"] == "ok":
                state, reason = "handoff_confirmed", ""
            else:
                state = "rejected"
                detail = receipt.get("details")
                reason = str(
                    (detail.get("error") if isinstance(detail, dict) else None)
                    or "provider_rejected"
                )[:64]

            acknowledged = await self._finish(
                row, now=moment, state=state, error_code=reason,
            )
            if not acknowledged:
                continue
            if state == "handoff_confirmed":
                outcome["handoff_confirmed"] += 1
            elif state == "rejected":
                outcome["rejected"] += 1
                if reason == "DeviceNotRegistered":
                    # A phone may have been moved to a new account since this
                    # ticket was created. Check both owner and endpoint id.
                    await self.db.push_endpoints.update_one(
                        {"id": row["endpoint_id"], "owner_id": row["owner_id"],
                         "status": "active"},
                        {"$set": {
                            "status": "disabled",
                            "disabled_reason": "DeviceNotRegistered",
                            "updated_at": moment.isoformat(),
                        }},
                    )
            elif state == "unconfirmed":
                outcome["unconfirmed"] += 1
            else:
                outcome["retrying"] += 1
        return outcome
