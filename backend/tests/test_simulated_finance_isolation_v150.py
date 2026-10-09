"""v150 — sandbox numbers never influence real bank reasoning or projections."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from financial.models import FinancialFact, Money, Provenance
from financial.observation import BankObservation, ObservationStore
from financial.reality import (
    account_sources, is_simulated_observation, simulated_fact_ids,
)


def obs(owner, ref, amount, *, simulated: bool, booked_at=None, label="SEPA 001"):
    return BankObservation(
        owner_id=owner,
        account_ref=("mock_account" if simulated else "bank_real"),
        transaction_ref=ref,
        booked_at=booked_at or datetime.now(timezone.utc).isoformat(),
        amount=amount,
        direction="incoming" if amount > 0 else "outgoing",
        raw_description=label,
        provenance={
            "provider_reality": "simulated" if simulated else "real",
            "institution": "Mock ASPSP" if simulated else "Banca reale",
        },
    )


@pytest.mark.asyncio
async def test_simulated_movement_cannot_create_a_real_fact_or_memory(monkeypatch):
    from financial import movements, reasoning

    db = AsyncMongoMockClient().v150_no_promotion
    simulated = obs("owner", "tx_fake_income", 2500, simulated=True)
    read = AsyncMock(side_effect=AssertionError("fake transaction must not trigger model"))
    monkeypatch.setattr(reasoning, "read_a_movement", read)

    result = await movements.look_at_a_movement(db, simulated)
    assert result["outcome"] == "simulated_observation"
    assert result["persisted_as_real_fact"] is False
    assert await db.financial_observations.count_documents({"owner_id": "owner"}) == 1
    assert await db.financial_facts.count_documents({"owner_id": "owner"}) == 0
    assert await db.memories.count_documents({"user_id": "owner"}) == 0
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_autonomous_batch_skips_demo_without_invoking_ai(monkeypatch):
    from financial.batching import read_what_is_new
    from financial import movements

    db = AsyncMongoMockClient().v150_batched
    store = ObservationStore(db)
    for ref, amount in [("tx1", -760), ("tx2", -14.99)]:
        await store.record(obs("owner", ref, amount, simulated=True))
    think = AsyncMock(side_effect=AssertionError("never reason over demo"))
    monkeypatch.setattr(movements, "look_at_a_movement", think)

    result = await read_what_is_new(db, "owner")
    assert result["simulati_esclusi"] == 2
    assert result["chiamate"] == 0
    assert result["interpretati"] == 0
    rows = await db.financial_observations.find({"owner_id": "owner"}).to_list(5)
    assert {r.get("look_outcome") for r in rows} == {"simulated"}
    think.assert_not_awaited()


@pytest.mark.asyncio
async def test_month_sum_counts_real_only_even_with_demo_in_same_account_view():
    from financial.observed import this_month

    db = AsyncMongoMockClient().v150_month
    store = ObservationStore(db)
    for item in [
        obs("owner", "real_salary", 2000, simulated=False),
        obs("owner", "real_bill", -100, simulated=False),
        obs("owner", "mock_salary", 3000, simulated=True),
        obs("owner", "mock_bill", -760, simulated=True),
    ]:
        await store.record(item)
    result = await this_month(db, "owner")
    assert result["entrate_osservate"] == "€2.000"
    assert result["uscite_osservate"] == "€100"
    assert result["differenza_parziale"] == "€1.900"
    assert result["quanti_movimenti"] == 2
    assert result["dati_di_prova_esclusi"] == 2

    demo_only = await this_month(db, "only_demo")
    assert demo_only == {}
    await store.record(obs("only_demo", "mock_only", -9999, simulated=True))
    demo_only = await this_month(db, "only_demo")
    assert "uscite_osservate" not in demo_only
    assert demo_only["dati_di_prova_esclusi"] == 1


@pytest.mark.asyncio
async def test_same_description_on_mock_and_real_never_creates_one_pattern():
    from financial.observed import what_was_seen

    db = AsyncMongoMockClient().v150_patterns
    store = ObservationStore(db)
    now = datetime.now(timezone.utc)
    for item in [
        obs("owner", "mock1", -14.99, simulated=True, label="SEPA ADDEBITO",
            booked_at=(now-timedelta(days=60)).isoformat()),
        obs("owner", "mock2", -14.99, simulated=True, label="SEPA ADDEBITO",
            booked_at=(now-timedelta(days=30)).isoformat()),
        obs("owner", "real1", -14.99, simulated=False, label="SEPA ADDEBITO"),
    ]:
        await store.record(item)
    result = await what_was_seen(db, "owner")
    recurring = result["ricorrenti_in_uscita"]
    assert len(recurring) == 1 and recurring[0]["simulato"] is True
    assert recurring[0]["quante_volte"] == 2
    singles = result["movimenti_singoli"]
    assert len(singles) == 1 and singles[0]["simulato"] is False


@pytest.mark.asyncio
async def test_old_governed_demo_fact_not_in_real_horizon_or_known_finances(monkeypatch):
    from financial import durable, knowledge, horizon
    from financial.store import FinancialStore
    from financial import observed

    db = AsyncMongoMockClient().v150_memory
    store = ObservationStore(db)
    await store.record(obs("owner", "mock_recurring", -760, simulated=True))
    await store.record(obs("owner", "real_recurring", -100, simulated=False))
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    demo = FinancialFact(
        id="memory_demo", owner_id="owner", kind="commitment",
        what="Pagamenti di prova", money=Money(amount=760, currency="EUR"),
        direction="outgoing", cadence="recurring", due_at=due,
        provenance=[Provenance(source="inferred", how_directly="test")],
        source_refs=["mock_recurring"],
    )
    real = FinancialFact(
        id="memory_real", owner_id="owner", kind="commitment",
        what="Pagamento reale", money=Money(amount=100, currency="EUR"),
        direction="outgoing", cadence="recurring", due_at=due,
        provenance=[Provenance(source="inferred", how_directly="bank")],
        source_refs=["real_recurring"],
    )
    governed = AsyncMock(return_value=[demo, real])
    monkeypatch.setattr(durable, "governed_facts", governed)
    monkeypatch.setattr(knowledge, "governed_facts", governed)
    monkeypatch.setattr(FinancialStore, "known", AsyncMock(return_value=[]))
    monkeypatch.setattr(durable, "needs_your_word", AsyncMock(return_value=[]))
    monkeypatch.setattr(knowledge, "needs_your_word", AsyncMock(return_value=[]))
    monkeypatch.setattr(observed, "the_bank_right_now", AsyncMock(return_value={}))
    monkeypatch.setattr(observed, "what_was_seen", AsyncMock(return_value={}))
    monkeypatch.setattr(observed, "this_month", AsyncMock(return_value={}))

    calendar = await horizon.what_is_coming(db, "owner")
    assert [x.id for x in calendar.outgoing] == ["memory_real"]
    assert calendar.known_outgoing_total() == 100

    view = await knowledge.what_ora_knows(db, "owner")
    assert [x["cosa"] for x in view["so"]] == ["Pagamento reale"]
    assert [x["cosa"] for x in view["dati_di_prova"]] == ["Pagamenti di prova"]


@pytest.mark.asyncio
async def test_historical_demo_match_is_owner_scoped_and_unknown_is_not_fake():
    db = AsyncMongoMockClient().v150_scope
    store = ObservationStore(db)
    await store.record(obs("other", "shared_tx", -500, simulated=True))
    fact = FinancialFact(
        id="fact_owner", owner_id="owner", kind="commitment",
        what="Spesa senza controprova", money=Money(amount=500, currency="EUR"),
        direction="outgoing", cadence="recurring",
        provenance=[Provenance(source="bank")], source_refs=["shared_tx"],
    )
    assert await simulated_fact_ids(db, "owner", [fact]) == set()

    await store.record(obs("owner", "shared_tx", -500, simulated=False))
    await store.record(obs("owner", "fake_tx", -500, simulated=True))
    mixed = fact.model_copy(deep=True)
    mixed.id = "mixed"
    mixed.source_refs = ["shared_tx", "fake_tx"]
    assert await simulated_fact_ids(db, "owner", [fact, mixed]) == set()
    demo = fact.model_copy(deep=True)
    demo.id = "demo"
    demo.source_refs = ["fake_tx"]
    assert await simulated_fact_ids(db, "owner", [demo]) == {"demo"}
