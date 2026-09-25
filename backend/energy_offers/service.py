"""Durable, bounded offer monitoring attached to uploaded utility bills."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ReturnDocument

from energy_offers.bill import parse_bill
from energy_offers.portal import fetch_offers

logger = logging.getLogger("ora.energy_offers")
MONITORS = "energy_offer_monitors"
CATALOG = "energy_offer_catalog"
CHECK_EVERY = timedelta(days=7)
RETRY_AFTER = timedelta(hours=12)
CATALOG_FRESH_FOR = timedelta(hours=20)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


class EnergyOfferService:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        await self.db[MONITORS].create_index(
            [("user_id", 1), ("commodity", 1), ("supply_key", 1)], unique=True
        )
        await self.db[MONITORS].create_index([("enabled", 1), ("next_check_at", 1)])
        await self.db[CATALOG].create_index("commodity", unique=True)

    async def register_bill(self, user_id: str, document: dict[str, Any]) -> bool:
        profile = parse_bill(document.get("extracted_text") or "", document_id=document.get("id") or "")
        if not profile or document.get("deleted") or document.get("archived"):
            return False
        if document.get("ocr_used"):
            profile["comparison_ready"] = False
            profile["needs_confirmation"] = True
        user = await self.db.users.find_one({"user_id": user_id}, {"preferences.energy_offer_monitoring": 1})
        if (user or {}).get("preferences", {}).get("energy_offer_monitoring") is False:
            return False
        identity = {"user_id": user_id, "commodity": profile["commodity"], "supply_key": profile["supply_key"]}
        previous = await self.db[MONITORS].find_one(identity, {"_id": 0, "document_id": 1})
        await self.db[MONITORS].update_one(
            identity,
            {"$set": {**profile, "user_id": user_id, "enabled": True,
                      "next_check_at": _iso(_now()), "updated_at": _iso(_now())},
             "$setOnInsert": {"created_at": _iso(_now())}},
            upsert=True,
        )
        return previous is None or previous.get("document_id") != profile["document_id"]

    async def _catalog(self, commodity: str, now: datetime) -> dict[str, Any]:
        cached = await self.db[CATALOG].find_one({"commodity": commodity}, {"_id": 0})
        if cached and cached.get("fetched_at", "") >= _iso(now - CATALOG_FRESH_FOR):
            return cached
        url, offers = await fetch_offers(commodity)
        if not offers:
            raise ValueError("official_export_has_no_usable_offers")
        catalog = {"commodity": commodity, "source_url": url,
                   "fetched_at": _iso(now), "offers": offers}
        await self.db[CATALOG].update_one({"commodity": commodity}, {"$set": catalog}, upsert=True)
        return catalog

    @staticmethod
    def compare(profile: dict[str, Any], offers: list[dict]) -> list[dict]:
        annual = profile["annual_consumption"]
        power = profile.get("power_kw")
        baseline = None
        if profile.get("comparison_ready"):
            current = next((offer for offer in offers if offer["code"].upper() == profile["current_offer_code"]), None)
            if current and current.get("unit_price") is not None and (not current["power_year"] or power is not None):
                baseline = annual * current["unit_price"] + current["fixed_year"] + (power or 0) * current["power_year"]
        candidates = []
        for offer in offers:
            if offer["code"].upper() == (profile.get("current_offer_code") or ""):
                continue
            if offer.get("unit_price") is None or annual is None:
                candidates.append({"code": offer["code"], "name": offer["name"],
                                   "seller": offer["seller"], "url": offer["url"],
                                   "valid_until": offer.get("valid_until"),
                                   "estimated_seller_year": None, "current_seller_year": None,
                                   "potential_saving_year": None,
                                   "comparison_basis": "consumption_missing" if annual is None else "price_not_comparable"})
                continue
            if offer.get("power_year") and power is None:
                continue
            estimated = annual * offer["unit_price"] + offer["fixed_year"] + (power or 0) * offer["power_year"]
            if estimated <= 0:
                continue
            saving = round(baseline - estimated, 2) if baseline is not None else None
            candidates.append({
                "code": offer["code"], "name": offer["name"], "seller": offer["seller"],
                "url": offer["url"], "valid_until": offer.get("valid_until"),
                "estimated_seller_year": round(estimated, 2),
                "current_seller_year": round(baseline, 2) if baseline is not None else None,
                "potential_saving_year": saving,
                "comparison_basis": "seller_components_only" if baseline is not None else "current_terms_missing",
            })
        candidates.sort(key=lambda item: (item["estimated_seller_year"] is None,
                                          item["estimated_seller_year"] or 0, item["code"]))
        if baseline is not None:
            # Small differences are fragile against tariff details and OCR error.
            candidates = [c for c in candidates if c["potential_saving_year"] >= max(50, baseline * .05)]
        return candidates[:3]

    async def run_due(self, *, now: datetime | None = None) -> dict[str, int]:
        moment = now or _now()
        row = await self.db[MONITORS].find_one_and_update(
            {"enabled": True, "next_check_at": {"$lte": _iso(moment)},
             "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lte": _iso(moment)}},
                     {"lease_until": None}]},
            {"$set": {"lease_until": _iso(moment + timedelta(minutes=15))}},
            return_document=ReturnDocument.AFTER,
        )
        if not row:
            return {"checked": 0, "failed": 0, "changed": 0}
        identity = {"_id": row["_id"]}
        try:
            doc = await self.db.documents.find_one(
                {"user_id": row["user_id"], "id": row["document_id"],
                 "deleted": {"$ne": True}, "archived": {"$ne": True}},
                {"_id": 0, "id": 1},
            )
            user = await self.db.users.find_one({"user_id": row["user_id"]}, {"preferences.energy_offer_monitoring": 1})
            if not doc or (user or {}).get("preferences", {}).get("energy_offer_monitoring") is False:
                await self.db[MONITORS].update_one(identity, {"$set": {"enabled": False, "lease_until": None}})
                return {"checked": 0, "failed": 0, "changed": 0}
            catalog = await self._catalog(row["commodity"], moment)
            candidates = self.compare(row, catalog["offers"])
            old = [(c["code"], c.get("potential_saving_year")) for c in row.get("candidates") or []]
            new = [(c["code"], c.get("potential_saving_year")) for c in candidates]
            changed = old != new and bool(candidates)
            await self.db[MONITORS].update_one(identity, {"$set": {
                "candidates": candidates, "source_url": catalog["source_url"],
                "source_fetched_at": catalog["fetched_at"], "last_checked_at": _iso(moment),
                "next_check_at": _iso(moment + CHECK_EVERY), "lease_until": None,
                "last_error": None,
            }})
            if changed:
                from opportunities.discovery import OpportunityDiscovery
                await OpportunityDiscovery(self.db).note(
                    row["user_id"], source="energy_offers", kind="offer_catalog_changed",
                    entity_ref=f"energy_offer:{row['commodity']}:{row['supply_key']}",
                    entity_kind="energy_offer",
                    after=",".join(f"{c['code']}:{c.get('potential_saving_year')}" for c in candidates),
                )
            return {"checked": 1, "failed": 0, "changed": int(changed)}
        except Exception as exc:
            logger.info("energy offer check failed: %s", type(exc).__name__)
            await self.db[MONITORS].update_one(identity, {"$set": {
                "next_check_at": _iso(moment + RETRY_AFTER), "lease_until": None,
                "last_error": type(exc).__name__,
            }})
            return {"checked": 0, "failed": 1, "changed": 0}

    async def status(self, user_id: str) -> list[dict[str, Any]]:
        rows = await self.db[MONITORS].find(
            {"user_id": user_id}, {"_id": 0, "supply_key": 0, "lease_until": 0}
        ).to_list(30)
        return rows

    async def set_enabled(self, user_id: str, enabled: bool) -> None:
        await self.db.users.update_one(
            {"user_id": user_id}, {"$set": {"preferences.energy_offer_monitoring": enabled}}
        )
        await self.db[MONITORS].update_many(
            {"user_id": user_id}, {"$set": {"enabled": enabled,
                                            "next_check_at": _iso(_now()) if enabled else None}}
        )
