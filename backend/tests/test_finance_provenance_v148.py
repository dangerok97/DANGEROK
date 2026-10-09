"""V148 — source identity, provider-time fidelity, and fake-bank isolation."""
from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from financial.models import FinancialFact, Money, Provenance
from financial.observation import BankObservation, ObservationStore
from financial.source_display import email_labels_for_facts
from financial.source_grounding import exact_source_datetime


def explicit_named_zone_due_at(observation):
    return exact_source_datetime((observation or {}).get("private_source_excerpt") or "")


@pytest.mark.asyncio
async def test_exact_email_subject_is_owner_scoped_for_old_and_governed_facts():
    db = AsyncMongoMockClient().v148_source
    await db.ingestion_events.insert_many([
        {
            "user_id": "owner", "source_record_type": "email_message",
            "external_id": "ing_msg", "ingestion_status": "processed",
            "ingested_at": "2026-10-08T12:00:00+00:00",
            "normalized_payload": {
                "subject": {"value": "Promemoria dalla tua carta di credito"},
                "received_at": {"value": "2026-10-08T12:00:00+00:00"},
            },
        },
        {
            "user_id": "owner", "source_record_type": "email_message",
            "external_id": "apple_msg", "ingestion_status": "processed",
            "ingested_at": "2026-10-08T14:00:00+00:00",
            "normalized_payload": {"subject": "L'importo per il piano iCloud+"},
        },
        {
            "user_id": "another-owner", "source_record_type": "email_message",
            "external_id": "foreign_msg", "ingestion_status": "processed",
            "ingested_at": "2026-10-08T14:00:00+00:00",
            "normalized_payload": {"subject": "Segreto di un'altra persona"},
        },
    ])
    ing = FinancialFact(
        id="fin_ing", owner_id="owner", kind="commitment",
        what="Carta di credito", money=Money(amount=None),
        direction="outgoing", due_at="2026-10-10",
        provenance=[Provenance(source="email", source_ref="ing_msg")],
    )
    apple = FinancialFact(
        id="mem_icloud", owner_id="owner", kind="commitment",
        what="iCloud+", money=Money(amount=0.99, currency="EUR"),
        direction="outgoing", due_at="2026-10-11",
        # Governed facts may lose original source_ref but keep evidence_refs.
        provenance=[Provenance(source="structured")],
        source_refs=["mail:apple_msg"],
    )
    stranger = ing.model_copy(deep=True)
    stranger.id = "fin_foreign"
    stranger.provenance[0].source_ref = "foreign_msg"
    result = await email_labels_for_facts(db, "owner", [ing, apple, stranger])
    assert result == {
        "fin_ing": "Email «Promemoria dalla tua carta di credito»",
        "mem_icloud": "Email «L'importo per il piano iCloud+»",
    }
    assert "Segreto" not in str(result)
    assert "body" not in str(result)


@pytest.mark.asyncio
async def test_fake_transactions_do_not_merge_into_real_recurring_charges():
    from financial.overview import seen_not_understood

    db = AsyncMongoMockClient().v148_mock
    await db.bank_accounts.insert_many([
        {"owner_id": "owner", "account_ref": "fake",
         "institution": "Mock ASPSP", "available_balance": 3250},
        {"owner_id": "owner", "account_ref": "real",
         "institution": "ING", "provider_reality": "real"},
    ])
    for account in ("fake", "real"):
        for i, day in enumerate(("2026-09-01", "2026-10-01")):
            await ObservationStore(db).record(BankObservation(
                owner_id="owner", account_ref=account,
                transaction_ref=f"{account}_{i}", booked_at=day,
                amount=-760, currency="EUR", direction="outgoing",
                raw_description="PAGAMENTO GENERICO",
                provenance={"institution": "Mock ASPSP" if account == "fake" else "ING"},
            ))
    rows = await seen_not_understood(db, "owner")
    assert len(rows) == 2, "demo observations must never count toward real recurrence"
    by_state = {row["stato"]: row for row in rows}
    assert "SIMULATO" in by_state and "HO VISTO" in by_state
    assert "Movimento di prova" in by_state["SIMULATO"]["cosa"]
    assert "non rappresenta una spesa reale" in by_state["SIMULATO"]["non_so"]
    assert "Movimento di prova" not in by_state["HO VISTO"]["cosa"]
    from financial.overview import recent_movements
    recent = await recent_movements(db, "owner")
    assert any(x["simulato"] for x in recent)
    assert any(not x["simulato"] for x in recent)
    assert await seen_not_understood(db, "another-owner") == []


def test_explicit_icloud_provider_zone_is_preserved_not_guessed():
    body = (
        "Il tuo piano di archiviazione da 50 GB si rinnova ogni mese "
        "a 0,99 € a partire dal giorno "
        "2026-10-11 03:25:28 America/Los_Angeles."
    )
    due = explicit_named_zone_due_at({"private_source_excerpt": body})
    assert due == "2026-10-11T03:25:28-07:00"
    assert datetime.fromisoformat(due).astimezone(
        ZoneInfo("Europe/Rome")
    ).strftime("%Y-%m-%d %H:%M") == "2026-10-11 12:25"
    assert explicit_named_zone_due_at(
        {"private_source_excerpt": "L'importo per il piano sarà addebitato fra 2 giorni"}
    ) is None
    assert explicit_named_zone_due_at(
        {"private_source_excerpt": body + " 2026-11-11 03:25:28 America/Los_Angeles"}
    ) is None


@pytest.mark.asyncio
async def test_financial_bridge_uses_exact_source_due_only_for_identified_commitment(monkeypatch):
    from financial import bridge, reasoning, durable
    from financial.store import FinancialStore

    db = AsyncMongoMockClient().v148_bridge
    monkeypatch.setattr(FinancialStore, "known", AsyncMock(return_value=[]))
    monkeypatch.setattr(bridge, "_life", AsyncMock(return_value={}))
    remember = AsyncMock(return_value={"outcome": "kept", "disputes": []})
    monkeypatch.setattr(FinancialStore, "remember", remember)
    monkeypatch.setattr(durable, "propose", AsyncMock(
        return_value={"decision": "CLARIFY", "persisted": False}))
    monkeypatch.setattr(reasoning, "read_financial_meaning", AsyncMock(
        return_value={
            "what_it_is": "commitment", "in_their_words": "iCloud+ 50 GB",
            "amount": 0.99, "currency": "EUR", "direction": "outgoing",
            "how_often": "recurring", "recurrence": "ogni mese",
            "due_at": "2026-10-11", "what_is_not_known": [],
        }
    ))
    body = "Si rinnova a 0,99 € dal 2026-10-11 03:25:28 America/Los_Angeles."
    result = await bridge.read_money_in(
        db, "owner", observation={
            "in_words": "L'importo per il piano iCloud+",
            "private_source_excerpt": body,
        },
        provenance=Provenance(source="email", source_ref="apple_msg"),
        source_refs=["mail:apple_msg"],
    )
    assert result["outcome"] == "kept"
    assert remember.await_args.args[0].due_at == "2026-10-11T03:25:28-07:00"
    assert remember.await_args.args[0].money.amount == 0.99
    assert body not in str(result), "only normalized data leaves financial judgement"
