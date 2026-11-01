"""Two card payments with the same notice name are two payments, not a dispute (owner, 02/11)."""
import pytest
from mongomock_motor import AsyncMongoMockClient

from financial.models import FinancialFact, Money, Provenance
from financial.store import FinancialStore

OWNER = "usr_card_v1"


def payment(amount, ref, when, **kw):
    return FinancialFact(owner_id=OWNER, kind=kw.pop("kind", "event"), what="Pagamento con carta di credito ING",
                         money=Money(amount=amount, currency="EUR"), direction="outgoing",
                         occurred_at=when, provenance=[Provenance(source="email", source_ref=ref)], **kw)


@pytest.mark.asyncio
async def test_two_card_payments_are_two_payments():
    store = FinancialStore(AsyncMongoMockClient().card_v1)
    a = await store.remember(payment(10.29, "msg1", "2026-11-01T12:10:00+01:00"))
    b = await store.remember(payment(3.70, "msg2", "2026-11-01T18:40:00+01:00"))
    assert a["outcome"] == "kept" and b["outcome"] == "kept"
    assert await store.disagreements(OWNER) == []
    # Same amount, another day: still two coffees, not one seen twice.
    c = await store.remember(payment(3.70, "msg3", "2026-11-02T08:00:00+01:00"))
    assert c["outcome"] == "kept"


@pytest.mark.asyncio
async def test_the_same_message_read_again_can_still_disagree_and_rent_still_does():
    store = FinancialStore(AsyncMongoMockClient().card_v2)
    rent = dict(kind="commitment", cadence="recurring")
    await store.remember(FinancialFact(owner_id=OWNER, what="Affitto", money=Money(amount=700, currency="EUR"),
                                       direction="outgoing", provenance=[Provenance(source="email", source_ref="r1")], **rent))
    out = await store.remember(FinancialFact(owner_id=OWNER, what="Affitto", money=Money(amount=760, currency="EUR"),
                                             direction="outgoing", provenance=[Provenance(source="email", source_ref="r2")], **rent))
    assert out["outcome"] == "disputed"
    assert len(await store.disagreements(OWNER)) == 1


@pytest.mark.asyncio
async def test_old_wrong_disputes_heal_and_leave_home():
    db = AsyncMongoMockClient().card_v3
    for f in (payment(10.29, "m1", "2026-11-01T12:10:00+01:00"), payment(3.70, "m2", "2026-11-01T18:40:00+01:00")):
        row = f.model_dump(); row["status"] = "disputed"
        await db.financial_facts.insert_one(row)
    assert await FinancialStore(db).disagreements(OWNER) == []
    assert await db.financial_facts.count_documents({"status": "disputed"}) == 0
