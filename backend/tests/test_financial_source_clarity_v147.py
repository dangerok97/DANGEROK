"""v147 — sourced money facts, card-settlement truth and simulator isolation."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from financial.models import FinancialFact, Money, Provenance
from financial.source_display import (
    exact_named_zone_timestamp, email_source_labels,
)


def test_explicit_source_timezone_outweighs_approximate_email_subject():
    body = (
        "Il tuo piano si rinnova automaticamente ogni mese a 0,99 € "
        "a partire dal giorno 2026-10-11 03:25:28 America/Los_Angeles."
    )
    parsed = exact_named_zone_timestamp({"body": body})
    assert parsed == "2026-10-11T03:25:28-07:00"
    assert datetime.fromisoformat(parsed).astimezone(
        __import__("zoneinfo").ZoneInfo("Europe/Rome")
    ).strftime("%Y-%m-%d %H:%M") == "2026-10-11 12:25"
    assert exact_named_zone_timestamp({"body": "fra 2 giorni"}) is None
    assert exact_named_zone_timestamp({"body": body + " e 2026-11-11 03:25:28 America/Los_Angeles"}) is None


@pytest.mark.asyncio
async def test_exact_email_subject_is_owner_scoped_and_not_a_guess():
    db = AsyncMongoMockClient().v147_sources
    await db.ingestion_events.insert_many([
        {
            "user_id": "owner", "source_record_type": "email_message",
            "external_id": "msg_credit", "ingestion_status": "processed",
            "ingested_at": "2026-10-08T09:00:00+00:00",
            "normalized_payload": {
                "subject": {"value": "Promemoria dalla tua carta di credito"},
                "received_at": {"value": "2026-10-08T09:00:00+00:00"},
            },
        },
        {
            "user_id": "stranger", "source_record_type": "email_message",
            "external_id": "msg_foreign", "ingestion_status": "processed",
            "normalized_payload": {"subject": "ALTRO CONTO NON TUO"},
        },
    ])
    credit = FinancialFact(
        id="fin_credit_fixture", owner_id="owner", kind="commitment",
        what="Addebito mensile della carta di credito",
        money=Money(amount=None), direction="outgoing",
        due_at="2026-10-10",
        provenance=[Provenance(source="email", source_ref="msg_credit")],
    )
    other = credit.model_copy(deep=True)
    other.id = "fin_foreign_fixture"
    other.provenance[0].source_ref = "msg_foreign"
    labels = await email_source_labels(db, "owner", [credit, other])
    assert labels == {"fin_credit_fixture": "Email «Promemoria dalla tua carta di credito»"}
    assert "ALTRO CONTO" not in str(labels)
    assert credit.money.amount is None, "no arbitrary amount for card statement"


@pytest.mark.asyncio
async def test_old_admin_hint_is_not_billed_or_promoted_to_focus():
    from home.adapters.action_engine_adapter import load_action_engine_items

    db = AsyncMongoMockClient().v147_admin
    await db.action_projects.insert_many([
        {"user_id": "owner", "id": "project_unfounded", "status": "active",
         "flow": "admin", "title": "Pagamento",
         "next_focus_hint": "Conosco un pagamento entro fine mese"},
        {"user_id": "owner", "id": "project_supported", "status": "active",
         "flow": "admin", "title": "Richiesta esplicita",
         "work_reason": "user_request", "next_focus_hint": "Preparare il documento"},
    ])
    items, _ = await load_action_engine_items(db, "owner")
    assert len(items) == 1
    assert items[0].source_id == "project_supported"
    assert items[0].type == "activity", "admin must not automatically mean bill"
    assert items[0].meta["work_reason"] == "user_request"


@pytest.mark.asyncio
async def test_financial_model_receives_exact_ephemeral_email_body(monkeypatch):
    from financial import bridge, reasoning
    from financial.store import FinancialStore

    db = AsyncMongoMockClient().v147_bridge
    monkeypatch.setattr(FinancialStore, "known", AsyncMock(return_value=[]))
    monkeypatch.setattr(bridge, "_life", AsyncMock(return_value={}))
    observe = AsyncMock(return_value={"what_it_is": "nothing"})
    monkeypatch.setattr(reasoning, "read_financial_meaning", observe)
    body = "L'addebito mensile della carta è previsto il 10/10. L'importo è consultabile in app."
    result = await bridge.read_money_in(
        db, "owner", observation={"in_words": "Promemoria carta"},
        provenance=Provenance(source="email", source_ref="msg_credit"),
        source_refs=["mail:msg_credit"],
        source_content={"body": body},
    )
    assert result["outcome"] == "nothing"
    assert observe.await_args.args[0]["source_excerpt_read_for_this_judgement"]["body"] == body
    assert await db.financial_facts.count_documents({}) == 0
    assert await db.connected_signals.count_documents({}) == 0


@pytest.mark.asyncio
async def test_fake_account_snapshot_is_labeled_simulated():
    from connectors.bank.provider import FakeBankProvider
    from connectors.bank.service import BankReadService

    db = AsyncMongoMockClient().v147_mock
    fake = FakeBankProvider()
    service = BankReadService(
        db=db, permissions=object(), vault=object(), provider=fake
    )
    account = (await fake.accounts(access_token="fake-token"))[0]
    service._same_account_come_back = AsyncMock()
    await service._remember_account("owner", "fake-instance", account)
    stored = await db.bank_accounts.find_one({"owner_id": "owner"})
    assert stored["source_reality"] == "simulated"
    assert stored["available_balance"] == 3250


@pytest.mark.asyncio
async def test_money_overview_never_calls_sandbox_balance_available_cash(monkeypatch):
    from financial import overview, knowledge, durable
    from connectors.bank import service as bank
    from financial.store import FinancialStore

    db = AsyncMongoMockClient().v147_overview
    monkeypatch.setattr(overview, "_connection", AsyncMock(return_value={
        "stato": "collegato", "realta": "simulated",
        "in_parole": "Collegamento di prova",
    }))
    monkeypatch.setattr(bank, "accounts_of", AsyncMock(return_value=[{
        "institution": "Mock ASPSP", "display_name": "Conto",
        "currency": "EUR", "available_balance": 3250.0,
        "balance_at": datetime.now(timezone.utc).isoformat(),
    }]))
    monkeypatch.setattr(knowledge, "what_ora_knows", AsyncMock(return_value={
        "so": [], "ho_letto": [],
    }))
    monkeypatch.setattr(durable, "governed_facts", AsyncMock(return_value=[]))
    monkeypatch.setattr(FinancialStore, "known", AsyncMock(return_value=[]))
    monkeypatch.setattr(overview, "seen_not_understood", AsyncMock(return_value=[]))
    monkeypatch.setattr(overview, "recent_movements", AsyncMock(return_value=[]))
    result = await overview.money_overview(db, "owner")
    account = result["conti"][0]
    assert account["simulato"] is True
    assert account["saldo_di_prova"] is True
    assert "simulat" in account["avviso_simulazione"]
    assert account["saldo"] == "€3.250"


@pytest.mark.asyncio
async def test_connected_life_forwards_private_content_only_for_meaningful_money(monkeypatch):
    from connected.models import ConnectedSignal
    from connected.service import ConnectedLifeService
    from financial import bridge

    db = AsyncMongoMockClient().v147_connected
    observed = AsyncMock(return_value={"outcome": "nothing"})
    monkeypatch.setattr(bridge, "read_money_in", observed)
    signal = ConnectedSignal(
        owner_id="owner", source_id="mail_instance",
        source_type="email", signal_type="email.message.added",
        source_object_ref="message_owned",
        payload_summary="È arrivato un promemoria economico.",
        raw_ref="mail:message_owned",
    )
    excerpt = {"body": "Il 10 ottobre si addebiteranno le spese della carta, importo non indicato."}
    await ConnectedLifeService(db)._pass_on(
        "owner", signal, {
            "outcome": "worth_knowing", "touches_money": True,
            "what_it_means": "Promemoria carta"
        }, source_content=excerpt
    )
    assert observed.await_count == 1
    assert observed.await_args.kwargs["source_content"] == excerpt
    assert observed.await_args.kwargs["provenance"].source_ref == "message_owned"

    observed.reset_mock()
    await ConnectedLifeService(db)._pass_on(
        "owner", signal, {
            "outcome": "worth_knowing", "touches_money": False,
            "what_it_means": "Altro"
        }, source_content=excerpt
    )
    observed.assert_not_awaited()
