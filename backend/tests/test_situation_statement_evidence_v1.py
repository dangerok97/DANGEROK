"""A deadline the person declared can be cited, so it can become a reminder.

Production 24/10/2026 03:54: "ho pagato il parcheggio fino alle 5:30" was
stored only in the Situation's facts. No result could cite it, so a declared
deadline could never turn into "sposta l'auto prima delle 5:30".
"""
from datetime import datetime, timedelta, timezone

import pytest

from situations.outcomes import validate_assessment
from test_situation_useful_outcome_v160 import OWNER, setup


@pytest.mark.asyncio
async def test_statement_is_recorded_once_per_pass_window(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    await service._note_situation_statement(OWNER, goal)
    await service._note_situation_statement(OWNER, goal)
    rows = await db.agent_evidence.find({"goal_id": goal.id, "kind": "situation_statement"}).to_list(None)
    assert len(rows) == 1
    row = rows[0]
    assert row["provenance"]["capability"] == "situation.read"
    assert row["provenance"]["source_refs"] == [f"situation:{state.id}:revision:{state.revision}"]
    assert "Dichiarato dalla persona" in row["claim"]
    assert state.facts[0][:20] in row["claim"]


@pytest.mark.asyncio
async def test_a_declared_deadline_supports_a_timely_reminder(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    run_at = datetime.now(timezone.utc).isoformat()
    await service._note_situation_statement(OWNER, goal)
    statement = [e for e in await service.evidence.for_goal(OWNER, goal.id) if e.kind == "situation_statement"][0]
    now = datetime.now(timezone.utc)
    raw = {"status": "action_now", "basis": "estimate", "action_reason": "early_risk",
           "headline": "Il limite dichiarato scade tra 10 minuti.",
           "action_summary": "Agisci adesso, prima della scadenza che hai indicato.",
           "valid_until": (now + timedelta(minutes=20)).isoformat(),
           "evidence_ids": [statement.id]}
    reasons = []
    result = await validate_assessment(db, OWNER, goal, raw, evidence=[statement], run_at=run_at, reasons=reasons)
    assert result is not None, reasons


@pytest.mark.asyncio
async def test_a_statement_is_not_proof_of_readiness(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    run_at = datetime.now(timezone.utc).isoformat()
    await service._note_situation_statement(OWNER, goal)
    statement = [e for e in await service.evidence.for_goal(OWNER, goal.id) if e.kind == "situation_statement"][0]
    now = datetime.now(timezone.utc)
    raw = {"status": "action_now", "basis": "estimate", "action_reason": "outcome_ready",
           "headline": "Dovrebbe essere pronto.", "action_summary": "Ritira ora.",
           "valid_until": (now + timedelta(minutes=20)).isoformat(), "evidence_ids": [statement.id]}
    reasons = []
    assert await validate_assessment(db, OWNER, goal, raw, evidence=[statement], run_at=run_at, reasons=reasons) is None
    assert reasons == ["estimate_without_baseline"]


@pytest.mark.asyncio
async def test_a_closed_situation_records_nothing(monkeypatch):
    db, service, state, goal, run, _, baseline, live = await setup(monkeypatch)
    await db.situations.update_one({"id": state.id}, {"$set": {"status": "cancelled"}})
    await service._note_situation_statement(OWNER, goal)
    assert await db.agent_evidence.count_documents({"kind": "situation_statement"}) == 0
