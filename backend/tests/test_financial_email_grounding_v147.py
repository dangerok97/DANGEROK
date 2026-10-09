"""v147: source-backed card notice, priced subscription, and truthful finance UI."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from connectors.bank.service import bank_account_is_simulated
from financial.models import FinancialFact, Money, Provenance
from financial.source_grounding import (
    amount_supported, check_financial_extraction, source_amounts,
)
from financial.source_review import review_email_financial_sources
from financial.store import FinancialStore
from home.adapters.action_engine_adapter import load_action_engine_items


def test_actual_email_currency_amount_is_distinguished_from_card_date_or_storage_size():
    apple = (
        "Gentile cliente, il tuo piano di archiviazione da 50 GB si rinnova "
        "automaticamente ogni mese a 0,99 € dal 2026-10-11."
    )
    ing = (
        "Il giorno 10/10/26 verrà effettuato l'addebito mensile delle "
        "spese fatte con la Carta di Credito Mastercard Gold. "
        "L'importo è visibile nella tua app."
    )
    assert source_amounts(apple) == [0.99]
    assert source_amounts(ing) == []
    assert amount_supported(0.99, apple)
    assert not amount_supported(50, apple)
    assert not amount_supported(10, ing)
    wrong = check_financial_extraction({
        "amount": 10, "what_is_not_known": [],
        "in_their_words": "Addebito carta di credito",
    }, {"private_source_excerpt": ing})
    assert wrong["amount"] is None
    assert any("importo" in s for s in wrong["what_is_not_known"])
    correct = check_financial_extraction(
        {"amount": 0.99, "what_is_not_known": []},
        {"private_source_excerpt": apple},
    )
    assert correct["amount"] == 0.99
    assert amount_supported(1234.56, "Spesa: € 1.234,56")
    assert amount_supported(14.99, "Totale EUR 14,99")


@pytest.mark.asyncio
async def test_same_email_reread_supersedes_vague_fact_without_duplicate_debt():
    db = AsyncMongoMockClient().v147_same_email
    store = FinancialStore(db)
    provenance = [Provenance(
        source="email", source_ref="mail_ing_1",
        how_directly="Oggetto email",
    )]
    first = FinancialFact(
        owner_id="owner", kind="commitment", what="Carta di credito",
        direction="outgoing", cadence="unknown", provenance=provenance,
        source_refs=["mail:mail_ing_1"], money=Money(amount=None),
        unknowns=["l'importo"],
    )
    await store.remember(first)
    second = FinancialFact(
        owner_id="owner", kind="commitment",
        what="Addebito mensile carta Mastercard Gold",
        direction="outgoing", cadence="recurring",
        recurrence="ogni mese", due_at="2026-10-10",
        counterparty="ING", provenance=provenance,
        source_refs=["mail:mail_ing_1"], money=Money(amount=None),
        unknowns=["l'importo"],
    )
    out = await store.remember(second)
    assert out["outcome"] == "superseded"
    active = await store.known("owner", kinds=["commitment"])
    assert len(active) == 1
    assert active[0].what == second.what
    assert active[0].money.amount is None
    historic = await db.financial_facts.find_one({"owner_id": "owner", "id": first.id})
    assert historic["status"] == "superseded"
    repeat = await store.remember(second.model_copy(update={"id": "new_duplicate"}))
    assert repeat["outcome"] == "already_known"
    assert await db.financial_facts.count_documents({"owner_id": "owner"}) == 2
    assert await store.known("another-owner") == []


@pytest.mark.asyncio
async def test_source_review_reads_only_owned_email_and_never_stores_raw_body(monkeypatch):
    import deps
    import financial.source_review as review
    db = AsyncMongoMockClient().v147_sources
    fact = FinancialFact(
        owner_id="owner", kind="commitment", what="Qualcosa di economico",
        direction="outgoing", provenance=[
            Provenance(source="email", source_ref="mail_icloud",
                       how_directly="L'importo per il piano"),
        ], money=Money(amount=None), source_refs=["mail:mail_icloud"],
    )
    await db.financial_facts.insert_one(fact.model_dump())
    await db.ingestion_events.insert_one({
        "user_id": "owner", "source_record_type": "email_message",
        "external_id": "mail_icloud", "connector_instance_id": "mail_account_1",
        "ingestion_status": "processed", "ingested_at": datetime.now(timezone.utc).isoformat(),
        "normalized_payload": {"subject": "Rinnovo del piano", "content_available": True},
    })
    class Mail:
        body_for = AsyncMock(return_value=(
            "Il piano iCloud+ da 50 GB si rinnova automaticamente ogni "
            "mese a 0,99 € dal 2026-10-11."
        ))
    mail = Mail()
    monkeypatch.setattr(deps, "get_gmail_service", lambda: mail)
    got = []
    async def spy(db_, owner, *, observation, provenance, source_refs):
        assert owner == "owner"
        assert provenance.source_ref == "mail_icloud"
        got.append(observation)
        return {"outcome": "superseded"}
    monkeypatch.setattr(review, "read_money_in", spy)

    result = await review_email_financial_sources(db, "owner", limit=5)
    assert result["checked"] == 1
    assert result["read_successfully"] == 1
    assert "0,99 €" in got[0]["private_source_excerpt"]
    mail.body_for.assert_awaited_once_with(
        user_id="owner", instance_id="mail_account_1",
        message_id="mail_icloud",
    )
    audits = await db.connected_content_reads.find({"owner_id": "owner"}).to_list(5)
    assert len(audits) == 1
    assert "body" in audits[0]["fields"]
    assert "0,99" not in str(audits)
    assert "0,99" not in str(await db.financial_source_reviews.find({}).to_list(5))
    again = await review_email_financial_sources(db, "owner")
    assert again["checked"] == 0
    assert len(got) == 1
    foreign = await review_email_financial_sources(db, "foreign")
    assert foreign["checked"] == 0


@pytest.mark.asyncio
async def test_unlinked_admin_action_engine_hint_is_not_a_fake_bill_focus():
    db = AsyncMongoMockClient().v147_actions
    await db.action_projects.insert_one({
        "id": "admin_hint_only", "user_id": "owner",
        "status": "active", "flow": "admin",
        "title": "Un promemoria non identificato",
        "next_focus_hint": "Admin: Conosco un pagamento entro fine mese",
        "linked": {"documents": [], "task_ids": [], "reminder_ids": []},
    })
    hidden, _ = await load_action_engine_items(db, "owner")
    assert hidden == []
    await db.action_projects.insert_one({
        "id": "real_task", "user_id": "owner", "status": "active",
        "flow": "admin", "title": "Richiedere una ricevuta",
        "next_focus_hint": "Verificare una ricevuta",
        "session_ids": ["session_1"],
        "linked": {"task_ids": ["task_1"]},
    })
    items, _ = await load_action_engine_items(db, "owner")
    assert len(items) == 1
    assert items[0].type == "activity"
    assert all(action.label != "Segna pagata" for action in items[0].actions)
    assert items[0].actions[0].route == "/action/session_1"


def test_mock_aspsp_is_explicitly_simulated_even_for_older_accounts():
    assert bank_account_is_simulated({
        "institution": "Mock ASPSP", "available_balance": 3250,
    })
    assert bank_account_is_simulated({
        "institution": "Example Bank", "provider_reality": "simulated",
    })
    assert not bank_account_is_simulated({
        "institution": "ING", "provider_reality": "real",
    })
    assert not bank_account_is_simulated({
        "institution": "Example Bank",
    })
