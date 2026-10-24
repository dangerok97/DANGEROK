"""Laundry estimated dry 17:19–18:19 must become "should be dry now" at the 17:29 check.

Production 24/10/2026, Tarquinia: the checkpoint re-read the weather at
17:29:34; the judgement arrived in the next pass at 17:30:44 with
status action_now / outcome_ready / basis direct_observation, citing weather and
research. It was refused (no_fresh_evidence_this_run), no notification left,
and a later pass moved the estimate to 19:30–20:30 for no reason.
"""
from datetime import datetime, timedelta, timezone

import pytest

from situations.outcomes import validate_assessment
from test_situation_useful_outcome_v160 import OWNER, action, setup


def read_before(live, minutes):
    run_start = datetime.now(timezone.utc)
    live.observed_at = (run_start - timedelta(minutes=minutes)).isoformat()
    live.provenance.observed_at = live.observed_at
    return run_start.isoformat()


@pytest.mark.asyncio
async def test_a_reading_from_the_same_checkpoint_one_minute_earlier_is_fresh(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    run_at = read_before(live, 1)
    reasons = []
    result = await validate_assessment(db, OWNER, goal, action(baseline, live),
                                       evidence=[baseline, live], run_at=run_at, reasons=reasons)
    assert result is not None, reasons
    assert result.action_reason == "outcome_ready"


@pytest.mark.asyncio
async def test_observed_readiness_from_forecast_and_research_is_kept_as_an_estimate(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    raw = action(baseline, live)
    raw["basis"] = "direct_observation"
    reasons = []
    result = await validate_assessment(db, OWNER, goal, raw, evidence=[baseline, live],
                                       run_at=read_before(live, 1), reasons=reasons)
    assert result is not None, reasons
    assert result.basis == "estimate"


@pytest.mark.asyncio
async def test_observed_readiness_from_weather_alone_is_still_refused(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    raw = action(baseline, live)
    raw.update(basis="direct_observation", evidence_ids=[live.id])
    reasons = []
    assert await validate_assessment(db, OWNER, goal, raw, evidence=[live],
                                     run_at=read_before(live, 1), reasons=reasons) is None
    assert reasons == ["direct_observation_unsupported"]


def test_guidance_says_a_reached_window_is_readiness_not_a_later_window():
    from agent.reasoning import _SITUATION_OUTCOME as text
    assert "inside or past a previously estimated window" in text
    assert "time passing is not such a reason" in text
