"""A sufficient, cited baseline is not refused for an open caveat.

Production 23/10/2026 17:51, Tarquinia: the drying-time research was
`sufficient`, every claim cited, nothing missing — yet `research_sufficient`
was False because the synthesis noted the evening drizzle was uncertain.
The estimate that cited it was then refused as a whole, so neither the
readiness window nor the rain warning reached the person.
"""
from datetime import datetime, timedelta, timezone

import pytest

from agent import providers
from situations.outcomes import validate_assessment
from test_situation_research_integrity_v159 import research_run, research_step, use_run
from test_situation_useful_outcome_v160 import OWNER, action, estimate, setup


@pytest.mark.asyncio
async def test_open_caveat_keeps_a_sufficient_cited_baseline(monkeypatch):
    from test_situation_wait_integrity_v157 import setup as wait_setup

    db, service, goal, plan, run, sid = await wait_setup(monkeypatch)
    fixture = research_run()
    fixture.user_id = goal.owner_id
    fixture.synthesis.unresolved = ["L'evoluzione esatta della pioviggine in serata."]
    use_run(monkeypatch, fixture)
    outcome = await providers.do_research(db, goal.owner_id, goal, research_step())
    assert outcome.provenance.research_sufficient is True
    assert "resta aperto" in outcome.provenance.certainty_note
    # Still refused when evidence is actually missing.
    fixture.assessments[-1].missing_evidence = ["Manca una fonte sui tempi"]
    outcome = await providers.do_research(db, goal.owner_id, goal, research_step())
    assert outcome.provenance.research_sufficient is False


@pytest.mark.asyncio
async def test_unestablished_research_citation_does_not_sink_a_rain_warning(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    baseline.provenance.research_sufficient = False
    raw = action(baseline, live)
    raw.update(action_reason="early_risk", headline="Ritira i panni: in serata è prevista pioggia.",
               action_summary="Ritirali prima della pioggia; non significa che siano già asciutti.",
               evidence_ids=[baseline.id, live.id])
    reasons = []
    result = await validate_assessment(db, OWNER, goal, raw, evidence=[baseline, live],
                                       run_at=run.at, reasons=reasons)
    assert result is not None, reasons
    assert result.evidence_ids == [live.id]


@pytest.mark.asyncio
async def test_estimate_still_needs_an_established_baseline(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    baseline.provenance.research_sufficient = False
    reasons = []
    result = await validate_assessment(db, OWNER, goal, estimate(baseline, live),
                                       evidence=[baseline, live], run_at=run.at, reasons=reasons)
    assert result is None and reasons == ["estimate_without_baseline"]


@pytest.mark.asyncio
async def test_stale_weather_citation_still_refuses(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    live.provenance.weather_valid_until = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    reasons = []
    assert await validate_assessment(db, OWNER, goal, estimate(baseline, live),
                                     evidence=[baseline, live], run_at=run.at, reasons=reasons) is None
    assert reasons == ["evidence_not_usable"]
