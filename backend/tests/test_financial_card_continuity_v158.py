"""A source correction must reach the saved fact and the actual Home response."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from financial.models import FinancialFact, Horizon, Money, Provenance
from financial.store import FinancialStore


def card_fact(**changes):
    values = dict(
        id="old_card", owner_id="owner", kind="commitment",
        what="Carta di credito", money=Money(amount=None), direction="outgoing",
        cadence="recurring", recurrence="ogni mese", due_at="2026-10-10",
        created_at="2026-10-08T12:00:00+00:00",
        provenance=[Provenance(source="email", source_ref="owned_message")],
        source_refs=["mail:owned_message"],
    )
    values.update(changes)
    return FinancialFact(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize("details", [
    {"what": "Addebito mensile Mastercard Gold", "counterparty": "ING"},
    {"due_at": "2026-10-10T14:25:28+02:00"},
    {"kind": "event", "occurred_at": "2026-10-10"},
])
async def test_same_source_retains_semantic_corrections_without_a_second_charge(details):
    db = AsyncMongoMockClient().financial_v158_meaning
    store = FinancialStore(db)
    old = card_fact()
    await store.remember(old)
    corrected = old.model_copy(deep=True, update={
        "id": "corrected_card", "created_at": "2026-10-11T15:00:00+00:00", **details,
    })
    outcome = await store.remember(corrected)
    assert outcome["outcome"] == "superseded"
    active = await store.known("owner")
    assert len(active) == 1
    assert active[0].id == "corrected_card"
    assert active[0].created_at == old.created_at
    for field, value in details.items():
        assert getattr(active[0], field) == value
    assert (await store.get("owner", old.id)).status == "superseded"
    assert (await store.remember(corrected.model_copy(update={"id": "retry"})))["outcome"] == "already_known"
    assert await store.get("another-owner", old.id) is None


@pytest.mark.asyncio
async def test_legacy_prefixed_source_and_shorter_specific_name_are_corrected_once():
    db = AsyncMongoMockClient().financial_v158_legacy
    store = FinancialStore(db)
    old = card_fact(
        what="Qualcosa di economico", money=Money(amount=0.99, currency="EUR"),
        provenance=[Provenance(source="email", source_ref="mail:owned_message")],
    )
    await store.remember(old)
    other = old.model_copy(deep=True, update={"id": "other_card", "owner_id": "another-owner"})
    await store.remember(other)
    corrected = old.model_copy(deep=True, update={
        "id": "icloud", "what": "iCloud+",
        "provenance": [Provenance(source="email", source_ref="owned_message")],
    })
    outcome = await store.remember(corrected)
    assert outcome["outcome"] == "superseded"
    assert [f.what for f in await store.known("owner")] == ["iCloud+"]
    assert [f.what for f in await store.known("another-owner")] == ["Qualcosa di economico"]


@pytest.mark.asyncio
async def test_a_less_precise_reread_keeps_the_known_amount_and_exact_time():
    db = AsyncMongoMockClient().financial_v158_no_downgrade
    store = FinancialStore(db)
    old = card_fact(
        due_at="2026-10-10T14:25:28+02:00",
        money=Money(amount=0.99, currency="EUR"),
    )
    await store.remember(old)
    for less_precise in (
        {"due_at": "2026-10-10"}, {"money": Money(amount=None)},
    ):
        result = await store.remember(old.model_copy(update={"id": "weaker", **less_precise}))
        assert result["outcome"] == "already_known"
        active = (await store.known("owner"))[0]
        assert active.money.amount == 0.99
        assert active.due_at == old.due_at


@pytest.mark.asyncio
@pytest.mark.parametrize("money", [
    Money(amount=25.99, currency="EUR"), Money(amount=14.99, currency="USD"),
])
async def test_conflicting_known_amount_from_the_same_email_remains_a_dispute(money):
    db = AsyncMongoMockClient().financial_v158_disagreement
    store = FinancialStore(db)
    old = card_fact(money=Money(amount=14.99, currency="EUR"))
    await store.remember(old)
    new = old.model_copy(update={"id": "conflicting", "money": money})
    result = await store.remember(new)
    assert result["outcome"] == "disputed"
    assert result["disputes"] == [old.id]
    versions = await store.known("owner")
    assert {f.status for f in versions} == {"disputed"}
    assert {(f.money.amount, f.money.currency) for f in versions} == {
        (14.99, "EUR"), (money.amount, money.currency),
    }


@pytest.mark.asyncio
async def test_bridge_governs_and_returns_the_retained_fact_when_reread_changes_nothing(monkeypatch):
    from financial import bridge, durable, reasoning

    db = AsyncMongoMockClient().financial_v158_bridge
    old = card_fact()
    await FinancialStore(db).remember(old)
    monkeypatch.setattr(bridge, "_life", AsyncMock(return_value={}))
    monkeypatch.setattr(reasoning, "read_financial_meaning", AsyncMock(return_value={
        "what_it_is": old.kind, "in_their_words": old.what, "amount": None,
        "direction": old.direction, "how_often": old.cadence,
        "recurrence": old.recurrence, "due_at": old.due_at,
        "what_is_not_known": ["l'importo"],
    }))
    governance = AsyncMock(return_value={"decision": "CLARIFY", "persisted": False})
    monkeypatch.setattr(durable, "propose", governance)
    result = await bridge.read_money_in(
        db, "owner", observation={"in_words": "Promemoria carta"},
        provenance=Provenance(source="email", source_ref="owned_message"),
        source_refs=["mail:owned_message"],
    )
    assert result["outcome"] == "already_known"
    assert result["fact_id"] == old.id
    assert governance.await_args.args[1].id == old.id
    assert await db.financial_facts.count_documents({}) == 1


@pytest.mark.asyncio
async def test_old_completed_review_can_recover_after_the_correction_then_is_idempotent(monkeypatch):
    import deps
    from financial import source_review

    db = AsyncMongoMockClient().financial_v158_review
    await FinancialStore(db).remember(card_fact())
    await db.ingestion_events.insert_one({
        "user_id": "owner", "external_id": "owned_message",
        "source_record_type": "email_message", "connector_instance_id": "gmail_owner",
        "ingestion_status": "processed", "normalized_payload": {"subject": "Promemoria carta"},
    })
    await db.financial_source_reviews.insert_one({
        "owner_id": "owner", "message_ref": "owned_message", "status": "completed",
    })
    mail = type("SyntheticMail", (), {"body_for": AsyncMock(return_value="Avviso sintetico.")})()
    monkeypatch.setattr(deps, "get_gmail_service", lambda: mail)
    reread = AsyncMock(return_value={"outcome": "superseded"})
    monkeypatch.setattr(source_review, "read_money_in", reread)
    first = await source_review.review_email_financial_sources(db, "owner")
    assert first["checked"] == first["updated"] == 1
    repeat = await source_review.review_email_financial_sources(db, "owner")
    assert repeat["checked"] == 0 and repeat["already_reviewed"] == 1
    assert mail.body_for.await_count == 1
    audits = await db.financial_source_reviews.find({}).to_list(5)
    assert "Avviso sintetico" not in str(audits)


@pytest.mark.asyncio
async def test_original_source_reaches_real_home_updates_without_becoming_focus(monkeypatch):
    from financial import durable, horizon
    from home import service as home_module
    from home.adapters.financial import load_financial_context
    from home.models import CurrentSituation

    db = AsyncMongoMockClient().financial_v158_home
    now = datetime.now(timezone.utc)
    due = (now + timedelta(days=2)).date().isoformat()
    fact = card_fact(due_at=due)
    await db.ingestion_events.insert_many([
        {
            "user_id": "owner", "external_id": "owned_message",
            "source_record_type": "email_message", "ingestion_status": "processed",
            "ingested_at": "2026-10-08T12:00:00+00:00",
            "normalized_payload": {
                "subject": {"value": "Promemoria dalla tua carta di credito"},
                "received_at": {"value": "2026-10-08T12:00:00+00:00"},
            },
        },
        {
            "user_id": "other-owner", "external_id": "owned_message",
            "source_record_type": "email_message", "ingestion_status": "processed",
            "ingested_at": "2026-10-09T12:00:00+00:00",
            "normalized_payload": {"subject": "Estratto di un'altra persona"},
        },
    ])
    incoming = Horizon(
        owner_id="owner", days=30, from_day=now.date().isoformat(), to_day=due,
        outgoing=[fact],
    )
    monkeypatch.setattr(horizon, "what_is_coming", AsyncMock(return_value=incoming))
    monkeypatch.setattr(FinancialStore, "disagreements", AsyncMock(return_value=[]))
    monkeypatch.setattr(durable, "needs_your_word", AsyncMock(return_value=[]))
    items, warnings = await load_financial_context(db, "owner")
    monkeypatch.setattr(home_module, "gather_all", AsyncMock(return_value=(
        items, warnings, {"connected": False},
    )))
    monkeypatch.setattr(home_module, "load_active_goals", AsyncMock(return_value=[]))
    service = home_module.HomeService(db)
    monkeypatch.setattr(service, "_build_situation", AsyncMock(return_value=CurrentSituation()))
    monkeypatch.setattr(service, "_weather_now", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_load_ora_ti_consiglia", AsyncMock(return_value=[]))
    home = await service.build_home("owner")
    assert home.primary_focus is None
    assert home.priorities == []
    assert len(home.insights) == 1
    insight = home.insights[0]
    assert "Promemoria dalla tua carta di credito" in insight.source
    assert "importo non noto" in insight.text.lower()
    assert "Estratto di un'altra persona" not in str(home.model_dump())
    assert insight.created_at == fact.created_at
    assert insight.valid_until == due
    assert insight.action.route == "/conti-e-denaro"
    # Refreshing the page or reinterpreting the same source cannot make an
    # old notice appear newly created. No source is reread to render Home.
    items[0].created_at = now.isoformat()
    again = await service.build_home("owner")
    assert again.insights[0].created_at == fact.created_at
    await db.home_insights.update_one(
        {"user_id": "owner", "id": insight.id}, {"$set": {"status": "read"}},
    )
    assert (await service.build_home("owner")).insights == []
    # A corrected UUID for the same original email is still the same notice.
    incoming.outgoing = [fact.model_copy(update={"id": "corrected_uuid"})]
    same_items, _ = await load_financial_context(db, "owner")
    assert same_items[0].source_id == items[0].source_id
    # A genuinely new source can surface even though the last summary was read.
    incoming.outgoing = [fact.model_copy(update={
        "id": "new_source_fact",
        "provenance": [Provenance(source="email", source_ref="a_new_message")],
        "source_refs": ["mail:a_new_message"],
    })]
    next_items, _ = await load_financial_context(db, "owner")
    monkeypatch.setattr(home_module, "gather_all", AsyncMock(return_value=(
        next_items, [], {"connected": False},
    )))
    next_home = await service.build_home("owner")
    assert len(next_home.insights) == 1
    assert next_home.insights[0].id != insight.id
    assert next_home.primary_focus is None


@pytest.mark.asyncio
async def test_undated_summary_expiry_is_fixed_and_date_only_notices_last_the_day():
    from home.models import HomeItem
    from home.service import HomeService

    db = AsyncMongoMockClient().financial_v158_expiration
    service = HomeService(db)
    now = datetime(2026, 10, 11, 15, 0, tzinfo=timezone.utc)
    item = HomeItem(
        id="summary", type="insight", title="Impegni economici conosciuti",
        source_type="financial", source_id="horizon", created_at=now.isoformat(),
        meta={"knowledge_only": True, "source_label": "Una fonte sintetica"},
    )
    first = (await service._build_insights("owner", [item], {}, now))[0]
    again = (await service._build_insights("owner", [item], {}, now + timedelta(hours=4)))[0]
    assert again.valid_until == first.valid_until
    assert await service._build_insights("owner", [item], {}, now + timedelta(days=2)) == []
    # A real day-only source expiry is valid through that day and takes
    # precedence over the generic display lifetime of an undated summary.
    item.meta["valid_until"] = "2026-10-11"
    dated = await service._build_insights("owner", [item], {}, now)
    assert len(dated) == 1 and dated[0].valid_until == "2026-10-11"
    assert await service._build_insights("owner", [item], {}, now + timedelta(days=1)) == []

