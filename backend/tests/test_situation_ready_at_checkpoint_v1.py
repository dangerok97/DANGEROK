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


@pytest.mark.asyncio
async def test_readiness_before_its_own_estimated_window_is_refused(monkeypatch):
    """Production 25/10 12:14: estimated 14:00-16:00, 'should be ready now' at 12:14."""
    from test_situation_useful_outcome_v160 import estimate
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    previous = await validate_assessment(db, OWNER, goal, estimate(baseline, live),
                                         evidence=[baseline, live], run_at=read_before(live, 1))
    assert previous is not None and previous.window_start
    goal.situation_outcome = previous
    reasons = []
    early = await validate_assessment(db, OWNER, goal, action(baseline, live), evidence=[baseline, live],
                                      run_at=read_before(live, 1), reasons=reasons)
    from datetime import datetime as _dt
    starts = _dt.fromisoformat(previous.window_start)
    if starts - _dt.now(starts.tzinfo) > timedelta(minutes=10):
        assert early is None and reasons == ["ready_before_window"]


@pytest.mark.asyncio
async def test_an_older_reading_next_to_a_fresh_one_is_set_aside(monkeypatch):
    import copy
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    run_at = read_before(live, 1)
    old = copy.deepcopy(live)
    old.id = "evd_old_reading"
    old.observed_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    old.provenance.observed_at = old.observed_at
    await db.agent_evidence.insert_one(old.model_dump())
    raw = action(baseline, live)
    raw["evidence_ids"] = [baseline.id, live.id, old.id]
    reasons = []
    result = await validate_assessment(db, OWNER, goal, raw, evidence=[baseline, live, old],
                                       run_at=run_at, reasons=reasons)
    if result is None:
        assert reasons and reasons[0] != "weather_not_reread_this_run", reasons
    else:
        assert old.id not in result.evidence_ids


@pytest.mark.asyncio
async def test_a_refused_proposal_does_not_erase_the_last_valid_estimate(monkeypatch):
    """Production 25/10 12:14: one rejected proposal wiped the 14:00-16:00 estimate from Home."""
    from test_situation_useful_outcome_v160 import estimate
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    assert await service._record_situation_outcome(OWNER, goal, estimate(baseline, live), run)
    before = (await db.agent_goals.find_one({"id": goal.id}))["situation_outcome"]
    bad = estimate(baseline, live)
    bad["evidence_ids"] = ["evd_not_there"]
    assert not await service._record_situation_outcome(OWNER, goal, bad, run)
    after = (await db.agent_goals.find_one({"id": goal.id}))["situation_outcome"]
    assert after and after["id"] == before["id"]
    kinds = [j["kind"] for j in await db.agent_journal.find({"goal_id": goal.id}).to_list(20)]
    assert "situation_outcome_rejected" in kinds
