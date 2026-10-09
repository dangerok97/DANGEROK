"""A financial hint must identify the actual fact and not become a fake task."""
from datetime import datetime, timezone
import pytest

from financial.models import FinancialFact, Money, Provenance, Horizon
from home.adapters.financial import load_financial_context


@pytest.mark.asyncio
async def test_named_payment_is_grounded_and_cannot_become_generic_organise(monkeypatch):
    import financial.horizon as horizon_module
    import financial.store as store_module
    import financial.durable as durable_module

    source_date = "2026-10-03T09:00:00+02:00"
    fact = FinancialFact(
        owner_id="synthetic",
        kind="commitment",
        what="bolletta elettrica",
        money=Money(amount=80, currency="EUR"),
        direction="outgoing",
        cadence="one_time",
        due_at="2026-10-28T12:00:00+01:00",
        created_at=source_date,
        provenance=[Provenance(source="email", how_directly="messaggio del fornitore")],
    )
    async def horizon(*args, **kwargs):
        return Horizon(owner_id="synthetic", days=30, from_day="2026-10-09",
                       to_day="2026-11-08", outgoing=[fact])
    async def no_disagreements(*args, **kwargs):
        return []
    async def no_questions(*args, **kwargs):
        return []
    monkeypatch.setattr(horizon_module, "what_is_coming", horizon)
    monkeypatch.setattr(store_module.FinancialStore, "disagreements", no_disagreements)
    monkeypatch.setattr(durable_module, "needs_your_word", no_questions)
    items, _ = await load_financial_context(object(), "synthetic")
    assert len(items) == 1
    card = items[0]
    assert "bolletta elettrica" in card.title
    assert "€80" in card.description
    assert "messaggio del fornitore" in card.description
    assert card.created_at == source_date
    assert card.meta["knowledge_only"] is True
    assert not card.actions
