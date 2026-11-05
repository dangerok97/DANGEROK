"""A bill read in the mail is settled by the bank movement that pays it."""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from financial import settled

OWNER = "usr_settled_v1"
NOW = datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)


def bill(id_, what, due, amount, who=None):
    return {"owner_id": OWNER, "id": id_, "what": what, "kind": "commitment", "direction": "outgoing",
            "status": "known", "due_at": due, "money": {"amount": amount, "currency": "EUR"}, "counterparty": who}


def move(id_, amount, booked, desc="", reality="real"):
    return {"owner_id": OWNER, "id": id_, "amount": -amount, "currency": "EUR", "direction": "outgoing",
            "booked_at": booked, "raw_description": desc, "provenance": {"provider_reality": reality, "status": "booked"}}


def test_match_rules():
    b = bill("b1", "Bolletta luce", "2026-11-10", 84.5, "Enel")
    assert settled.match(b, [move("m1", 84.5, "2026-11-02")], set())["id"] == "m1"
    assert settled.match(b, [move("m1", 84.6, "2026-11-02")], set()) is None            # not to the cent
    assert settled.match(b, [move("m1", 84.5, "2026-09-01")], set()) is None            # too early
    assert settled.match(b, [move("m1", 84.5, "2026-11-02")], {"m1"}) is None           # already used
    near = settled.match(b, [move("far", 84.5, "2026-10-05"), move("near", 84.5, "2026-11-09")], set())
    assert near["id"] == "near"
    small = bill("b2", "Abbonamento", "2026-11-10", 2.5, "Spotify")
    assert settled.match(small, [move("c", 2.5, "2026-11-08", "BAR CENTRALE")], set()) is None
    assert settled.match(small, [move("s", 2.5, "2026-11-08", "SPOTIFY AB")], set())["id"] == "s"


@pytest.mark.asyncio
async def test_settled_bills_leave_the_deadlines():
    from zoneinfo import ZoneInfo
    from opportunities.deadlines import upcoming
    db = AsyncMongoMockClient().settled_v1
    await db.financial_facts.insert_many([bill("b1", "Bolletta luce", "2026-11-07", 84.5),
                                          bill("b2", "Bolletta gas", "2026-11-08", 40.0)])
    await db.financial_observations.insert_many([move("m1", 84.5, "2026-11-03"),
                                                 move("t1", 40.0, "2026-11-03", reality="simulated")])
    found = await settled.settle(db, OWNER, now=NOW)
    assert [f["ref"] for f in found] == ["financial:b1"]
    assert await settled.settle(db, OWNER, now=NOW) == []          # once
    rows = await upcoming(db, OWNER, NOW.astimezone(ZoneInfo("Europe/Rome")))
    assert [r["title"] for r in rows] == ["Bolletta gas (€40)"]     # a test bank row never settles a real bill
