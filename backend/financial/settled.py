"""
A bill read in the mail, then seen paid on the bank account.

Since bills with a due date became deadlines (31/10), ORA reminds them in the
morning brief, the evening before and in the reviews — and had no way to know
one was already paid, so it would keep reminding until the date passed. The
bank account is connected: when an outgoing movement of exactly the bill's
amount is booked between 40 days before and 10 days after its due date, the
bill is settled by that movement. Code, not judgement:

* the amount must match to the cent, in the same currency;
* a small amount (under 5 €) also needs the bill's counterparty in the bank
  line, because 2,50 € alone matches a coffee;
* one movement settles one bill, and the nearest date wins;
* the link is written on the bill (`settled_by`), never a new fact, and is
  shown to the person in the morning brief («Ho visto che hai pagato …»).

Test bank rows never settle a real bill.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.financial.settled")

BEFORE_DAYS = 40
AFTER_DAYS = 10
SMALL_AMOUNT = 5.0


def _when(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return datetime.fromisoformat(text).replace(hour=12, tzinfo=timezone.utc)
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _words(text: Any) -> set:
    return {w for w in re.findall(r"[a-zà-ù0-9]{3,}", str(text or "").casefold())
            if w not in {"spa", "srl", "s.p.a", "the", "per", "con", "del", "della", "pagamento", "addebito"}}


def match(bill: Dict[str, Any], movements: List[Dict[str, Any]], used: set) -> Optional[Dict[str, Any]]:
    """The bank movement that pays this bill, or None. Pure."""
    money = bill.get("money") or {}
    amount = money.get("amount")
    due = _when(bill.get("due_at"))
    if amount is None or due is None or float(amount) <= 0:
        return None
    currency = str(money.get("currency") or "EUR").upper()
    who = _words(bill.get("counterparty")) or set()
    best, best_gap = None, None
    for m in movements:
        if m.get("id") in used or str(m.get("direction") or "") != "outgoing":
            continue
        if str(m.get("currency") or "EUR").upper() != currency:
            continue
        if round(abs(float(m.get("amount") or 0)), 2) != round(float(amount), 2):
            continue
        booked = _when(m.get("booked_at"))
        if booked is None or not (due - timedelta(days=BEFORE_DAYS) <= booked <= due + timedelta(days=AFTER_DAYS)):
            continue
        if float(amount) < SMALL_AMOUNT:
            line = _words(m.get("raw_description")) | _words(m.get("counterparty"))
            if not who or not (who & line):
                continue
        gap = abs((booked - due).total_seconds())
        if best_gap is None or gap < best_gap:
            best, best_gap = m, gap
    return best


async def settle(db, owner: str, *, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Self-check: link the bills paid since the last pass. Never raises."""
    now = now or datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    try:
        bills = await db.financial_facts.find(
            {"owner_id": owner, "status": "known", "kind": "commitment", "direction": {"$ne": "incoming"},
             "due_at": {"$nin": [None, ""]}, "settled_by": {"$exists": False}, "money.amount": {"$ne": None}},
            {"_id": 0, "id": 1, "what": 1, "due_at": 1, "money": 1, "counterparty": 1},
        ).limit(100).to_list(100)
        bills = [b for b in bills if (_when(b.get("due_at")) or now) >= now - timedelta(days=60)]
        if not bills:
            return out
        movements = await db.financial_observations.find(
            {"owner_id": owner, "direction": "outgoing",
             "booked_at": {"$gte": (now - timedelta(days=120)).date().isoformat()},
             "provenance.provider_reality": {"$ne": "simulated"}, "provenance.status": {"$ne": "pending"}},
            {"_id": 0, "id": 1, "amount": 1, "currency": 1, "direction": 1, "booked_at": 1,
             "raw_description": 1, "counterparty": 1},
        ).limit(1000).to_list(1000)
        used = {str(r.get("settled_by", {}).get("observation_id"))
                async for r in db.financial_facts.find({"owner_id": owner, "settled_by": {"$exists": True}},
                                                       {"_id": 0, "settled_by": 1})}
        for bill in sorted(bills, key=lambda b: str(b.get("due_at"))):
            paid = match(bill, movements, used)
            if paid is None:
                continue
            used.add(paid["id"])
            await db.financial_facts.update_one(
                {"owner_id": owner, "id": bill["id"], "settled_by": {"$exists": False}},
                {"$set": {"settled_by": {"observation_id": paid["id"], "booked_at": paid.get("booked_at"),
                                         "at": now.isoformat(), "how": "importo uguale sul conto"}}})
            out.append({"code": "bill_settled", "ref": f"financial:{bill['id']}", "repaired": True,
                        "what": str(bill.get("what") or "")[:80]})
    except Exception as exc:
        logger.info("bill settling deferred: %s", type(exc).__name__)
    return out
