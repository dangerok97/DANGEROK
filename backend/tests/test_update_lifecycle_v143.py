"""Regression: perishable Home signals disappear at the exact useful deadline.

This is deliberately an owner-neutral synthetic test. The annual birthday
memory is a separate durable record and is never deleted by display gating.
"""
from types import SimpleNamespace
import pytest

from opportunities.models import EvidenceRef, Opportunity
from opportunities.surfacing import SurfacingService


@pytest.mark.asyncio
async def test_expired_birthday_not_current_the_day_after():
    service = SurfacingService(db=None)
    birthday = Opportunity(
        owner_id="synthetic-owner",
        identity_key="recurring_memo:synthetic:2026",
        status="active",
        semantic_summary="Compleanno di zia Elena",
        why_it_matters="Ricorrenza salvata",
        source_context="recurring_memo",
        evidence=[EvidenceRef(kind="memory", ref="mem_synthetic", summary="8 ottobre")],
        valid_until="2026-10-08T23:59:59+02:00",
        surface_state="surfaced",
    )
    assert await service._current(
        "synthetic-owner", birthday, "2026-10-08T14:00:00+02:00"
    ) is True
    assert await service._current(
        "synthetic-owner", birthday, "2026-10-09T00:00:00+02:00"
    ) is False
    card = birthday.for_home()
    assert card["created_at"] == birthday.created_at
    assert card["valid_until"] == birthday.valid_until
    assert birthday.status == "active"  # display guard never mutates memory


@pytest.mark.asyncio
async def test_timezone_and_date_only_expiration():
    service = SurfacingService(db=None)
    item = SimpleNamespace(valid_until="2026-09-20T08:00:00+02:00", evidence=[])
    assert not await service._current(
        "synthetic-owner", item, "2026-10-09T10:00:00+02:00"
    )
    item.valid_until = "2026-10-09"
    assert await service._current(
        "synthetic-owner", item, "2026-10-09T17:00:00+02:00"
    )
    assert not await service._current(
        "synthetic-owner", item, "2026-10-10T02:00:00+02:00"
    )
    item.valid_until = "invalid-date"
    assert not await service._current(
        "synthetic-owner", item, "2026-10-09T17:00:00+02:00"
    )
