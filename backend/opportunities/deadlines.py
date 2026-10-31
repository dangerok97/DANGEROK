"""
Deadlines the person already has, read where they live.

Audit 26/10/2026: a plan step "consegna entro venerdì" and an open decision
with a deadline were shown in Home, but no review ever saw the date: the
snapshot carried only Home titles. Nothing could notice that Friday had
become tomorrow.

This reads open decisions with a deadline and the open steps (and target
dates) of active plans, bounded, as facts: what, which day, how far away.
What any of it means stays with the review.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List

HORIZON_DAYS = 7
MAX_ROWS = 12
OPEN_ITEM = ("not_started", "in_progress")


def _when(value: Any, tz) -> tuple[datetime | None, bool]:
    """(instant, date_only). A bare date is the end of that local day."""
    text = str(value or "").strip()
    if not text:
        return None, False
    if len(text) == 10:
        try:
            day = date.fromisoformat(text)
        except ValueError:
            return None, False
        return datetime.combine(day, time(23, 59), tzinfo=tz), True
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None, False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=tz)
    # Our own code writes a date-only deadline as T12:00 UTC.
    date_only = moment.utcoffset() == timedelta(0) and (moment.hour, moment.minute) == (12, 0)
    if date_only:
        moment = datetime.combine(moment.date(), time(23, 59), tzinfo=tz)
    return moment, date_only


async def upcoming(db, user_id: str, now: datetime, *, days: int = HORIZON_DAYS) -> List[Dict[str, Any]]:
    """Open deadlines from now (or overdue since yesterday) to `days` ahead."""
    tz = now.tzinfo
    start, end = now - timedelta(days=1), now + timedelta(days=days)
    out: List[Dict[str, Any]] = []
    linked_items: set[str] = set()

    rows = await db.decisions.find(
        {"user_id": user_id, "status": "open", "deadline": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "title": 1, "deadline": 1, "action_state": 1, "metadata": 1},
    ).limit(200).to_list(200)
    for row in rows:
        if str((row.get("action_state") or {}).get("status") or "") in ("completed", "dismissed"):
            continue
        due, date_only = _when(row.get("deadline"), tz)
        if due is None or not start <= due <= end:
            continue
        item_id = str((row.get("metadata") or {}).get("plan_item_id") or "")
        if item_id:
            linked_items.add(item_id)
        out.append({"ref": f"decision:{row.get('id')}", "title": str(row.get("title") or "")[:120],
                    "kind": "decision", "due": due, "date_only": date_only})

    plans = await db.life_os_plans.find(
        {"user_id": user_id, "status": "active"},
        {"_id": 0, "id": 1, "title": 1, "target_date": 1, "items": 1},
    ).limit(30).to_list(30)
    for plan in plans:
        for item in plan.get("items") or []:
            if item.get("status") not in OPEN_ITEM or str(item.get("id")) in linked_items:
                continue
            due, date_only = _when(item.get("due_date"), tz)
            if due is None or not start <= due <= end:
                continue
            out.append({"ref": f"plan_item:{plan.get('id')}:{item.get('id')}",
                        "title": str(item.get("title") or "")[:120],
                        "plan": str(plan.get("title") or "")[:80],
                        "kind": "plan_step", "due": due, "date_only": date_only})
        due, date_only = _when(plan.get("target_date"), tz)
        if due is not None and start <= due <= end:
            out.append({"ref": f"plan:{plan.get('id')}", "title": str(plan.get("title") or "")[:120],
                        "kind": "plan_target", "due": due, "date_only": date_only})

    # Bills and payments read from mail and documents (financial/): they had a
    # due date in financial_facts and never reached the deadlines, so neither
    # the morning brief nor the self-check ever said «scade la bolletta».
    try:
        facts = await db.financial_facts.find(
            {"owner_id": user_id, "status": "known", "kind": "commitment", "direction": {"$ne": "incoming"},
             "due_at": {"$nin": [None, ""]}},
            {"_id": 0, "id": 1, "what": 1, "due_at": 1, "money": 1, "counterparty": 1},
        ).limit(100).to_list(100)
    except Exception:
        facts = []
    seen_bills: set = set()
    for f in facts:
        due, date_only = _when(f.get("due_at"), tz)
        if due is None or not start <= due <= end:
            continue
        title = " ".join(str(f.get("what") or "Pagamento").split())[:90]
        money = f.get("money") or {}
        if money.get("amount") is not None and str(money.get("currency") or "EUR").upper() == "EUR":
            title += f" (€{float(money['amount']):.2f})".replace(".", ",").replace(",00)", ")")
        key = (title.casefold(), due.date())
        if key in seen_bills:
            continue
        seen_bills.add(key)
        out.append({"ref": f"financial:{f.get('id')}", "title": title[:120], "kind": "bill",
                    "due": due, "date_only": date_only})

    out.sort(key=lambda r: r["due"])
    return out[:MAX_ROWS]


def as_facts(rows: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """The snapshot shape: dates as local text, distance as a number."""
    facts = []
    for r in rows:
        due = r["due"].astimezone(now.tzinfo)
        facts.append({
            "ref": r["ref"], "title": r["title"], "kind": r["kind"],
            **({"plan": r["plan"]} if r.get("plan") else {}),
            "due_local": due.date().isoformat() if r["date_only"] else due.isoformat(timespec="minutes"),
            "date_only": r["date_only"],
            "days_left": (due.date() - now.date()).days,
            "overdue": due < now,
        })
    return facts
