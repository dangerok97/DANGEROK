"""v151: finance source review reports what actually happened, not false Gmail errors."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from financial.models import FinancialFact, Money, Provenance
from financial.source_review import review_email_financial_sources
from financial.horizon import what_is_coming
from financial.store import FinancialStore


async def source(db, *, owner="owner", message="msg_owned", ref=None):
    fact = FinancialFact(
        id=f"fact_{owner}", owner_id=owner, kind="commitment",
        what="Addebito carta con importo ignoto",
        money=Money(amount=None), direction="outgoing", due_at="2026-10-10",
        provenance=[Provenance(source="email", source_ref=ref or message)],
        source_refs=[f"mail:{message}"],
    )
    await db.financial_facts.insert_one(fact.model_dump())
    await db.ingestion_events.insert_one({
        "user_id": owner, "external_id": message,
        "source_record_type": "email_message",
        "connector_instance_id": f"gmail_{owner}",
        "ingestion_status": "processed",
        "ingested_at": "2026-10-08T14:00:00+00:00",
        "normalized_payload": {"subject": "Promemoria carta"},
    })
    return fact


@pytest.mark.asyncio
async def test_legacy_prefixed_email_ref_reread_then_already_reviewed_is_not_gmail_failure(monkeypatch):
    import deps
    import financial.source_review as review
    db = AsyncMongoMockClient().v151_reread
    await source(db, ref="mail:msg_owned")
    class Mail:
        body_for = AsyncMock(return_value=(
            "L'addebito mensile della carta è previsto il 10 ottobre. "
            "L'importo non è indicato."
        ))
    mail = Mail()
    monkeypatch.setattr(deps, "get_gmail_service", lambda: mail)
    model = AsyncMock(return_value={"outcome": "already_known"})
    monkeypatch.setattr(review, "read_money_in", model)

    first = await review_email_financial_sources(db, "owner")
    assert first["checked"] == 1
    assert first["read_successfully"] == 1
    assert first["updated"] == 0
    assert first["unchanged"] == 1
    assert first["already_reviewed"] == 0
    assert "non ho nuovi importi" in first["message"]
    assert model.await_args.kwargs["provenance"].source_ref == "msg_owned"
    assert model.await_args.kwargs["source_refs"] == ["mail:msg_owned"]
    mail.body_for.assert_awaited_once_with(
        user_id="owner", instance_id="gmail_owner", message_id="msg_owned"
    )
    again = await review_email_financial_sources(db, "owner")
    assert again["checked"] == 0 and again["already_reviewed"] == 1
    assert "già stata verificata" in again["message"]
    assert "Non ho potuto rileggere" not in again["message"]
    assert mail.body_for.await_count == 1
    assert await review_email_financial_sources(db, "other") == {
        "checked": 0, "read_successfully": 0, "updated": 0,
        "unchanged": 0, "unconfirmed": 0, "already_reviewed": 0,
        "not_available": 0,
        "message": ("Non risultano email economiche precedentemente riconosciute "
                    "da rileggere. Questo non dimostra che la casella sia vuota."),
    }


@pytest.mark.asyncio
async def test_read_no_financial_meaning_not_reported_as_corrected(monkeypatch):
    import deps
    import financial.source_review as review
    db = AsyncMongoMockClient().v151_no_finance
    await source(db)
    class Mail:
        async def body_for(self, **kwargs):
            return "Un aggiornamento informativo privo di nuovi impegni."
    monkeypatch.setattr(deps, "get_gmail_service", lambda: Mail())
    monkeypatch.setattr(review, "read_money_in",
                        AsyncMock(return_value={"outcome": "nothing"}))
    result = await review_email_financial_sources(db, "owner")
    assert result["checked"] == result["read_successfully"] == 1
    assert result["updated"] == 0
    assert result["unconfirmed"] == 1
    assert "non ha confermato" in result["message"]
    assert await db.financial_source_reviews.count_documents({}) == 0
    assert await db.financial_facts.count_documents({}) == 1


@pytest.mark.asyncio
async def test_model_unavailable_does_not_claim_source_corrected(monkeypatch):
    import deps
    import financial.source_review as review
    db = AsyncMongoMockClient().v151_unavailable
    await source(db)
    class Mail:
        async def body_for(self, **kwargs):
            return "Testo leggibile, giudizio non disponibile."
    monkeypatch.setattr(deps, "get_gmail_service", lambda: Mail())
    monkeypatch.setattr(review, "read_money_in",
                        AsyncMock(return_value={"outcome": "no_answer"}))
    result = await review_email_financial_sources(db, "owner")
    assert result["read_successfully"] == 1
    assert result["not_available"] == 1
    assert result["updated"] == 0
    assert "interpretazioni non" in result["message"]
    assert await db.financial_source_reviews.count_documents({}) == 0


@pytest.mark.asyncio
async def test_date_only_card_settlement_is_visible_through_due_day(monkeypatch):
    from financial import durable
    db = AsyncMongoMockClient().v151_due_day
    due = FinancialFact(
        id="fin_card_today", owner_id="owner", kind="commitment",
        what="Addebito mensile carta",
        money=Money(amount=None), direction="outgoing",
        due_at="2026-10-10", cadence="one_time",
        provenance=[Provenance(source="email", source_ref="msg_owned")],
    )
    scheduled = due.model_copy(deep=True)
    scheduled.id = "fin_card_exact"
    scheduled.what = "Addebito preciso già passato"
    scheduled.due_at = "2026-10-10T08:00:00+02:00"
    monkeypatch.setattr(durable, "governed_facts",
                        AsyncMock(return_value=[]))
    monkeypatch.setattr(FinancialStore, "known",
                        AsyncMock(return_value=[due, scheduled]))
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    today = await what_is_coming(db, "owner", now=now)
    assert [f.id for f in today.outgoing] == ["fin_card_today"]
    assert any("quanto" in unknown for unknown in today.unknowns)
    tomorrow = await what_is_coming(
        db, "owner", now=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    )
    assert tomorrow.outgoing == []
