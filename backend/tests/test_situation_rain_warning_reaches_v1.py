"""A rain warning read minutes ago is not refused for being minutes old.

Production 23/10/2026, Tarquinia, laundry out at 18:23:
- 19:16 "ritira i panni, arriva la pioggia" refused: the forecast had been read
  8 minutes earlier, in the previous pass of the same check;
- 20:16 the model wrote "status": "early_risk" with basis direct_observation:
  refused as schema_invalid.
Readiness still needs a reading from this very pass.
"""
from datetime import datetime, timedelta, timezone

import pytest

from situations.outcomes import validate_assessment
from test_situation_useful_outcome_v160 import OWNER, action, setup


def warning(baseline, live):
    raw = action(baseline, live)
    raw.update(action_reason="early_risk", headline="Ritira i panni: arriva la pioggia.",
               action_summary="Ritirali adesso; non significa che siano asciutti.",
               evidence_ids=[live.id])
    return raw


async def read_minutes_before_run(service, live, minutes):
    run_start = datetime.now(timezone.utc)
    live.observed_at = (run_start - timedelta(minutes=minutes)).isoformat()
    live.provenance.observed_at = live.observed_at
    return run_start.isoformat()


@pytest.mark.asyncio
async def test_a_warning_from_a_reading_eight_minutes_old_reaches_the_person(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    run_at = await read_minutes_before_run(service, live, 8)
    reasons = []
    result = await validate_assessment(db, OWNER, goal, warning(baseline, live),
                                       evidence=[live], run_at=run_at, reasons=reasons)
    assert result is not None, reasons
    assert result.action_reason == "early_risk"


@pytest.mark.asyncio
async def test_readiness_still_needs_a_reading_from_this_pass(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    run_at = await read_minutes_before_run(service, live, 8)
    reasons = []
    assert await validate_assessment(db, OWNER, goal, action(baseline, live),
                                     evidence=[baseline, live], run_at=run_at, reasons=reasons) is None
    assert reasons == ["no_fresh_evidence_this_run"]


@pytest.mark.asyncio
async def test_an_old_reading_is_still_too_old(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    run_at = await read_minutes_before_run(service, live, 45)
    reasons = []
    assert await validate_assessment(db, OWNER, goal, warning(baseline, live),
                                     evidence=[live], run_at=run_at, reasons=reasons) is None
    assert reasons == ["no_fresh_evidence_this_run"]


@pytest.mark.asyncio
async def test_reason_written_as_status_is_placed_where_it_belongs(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    raw = warning(baseline, live)
    raw.update(status="early_risk", basis="direct_observation")
    reasons = []
    result = await validate_assessment(db, OWNER, goal, raw, evidence=[live], run_at=run.at, reasons=reasons)
    assert result is not None, reasons
    assert (result.status, result.action_reason) == ("action_now", "early_risk")
