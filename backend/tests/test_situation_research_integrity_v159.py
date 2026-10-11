"""Synthetic source/quality regressions: real research is not automatically local evidence."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import providers
from agent.models import ActionPlan, ActionStep, AgentRun, AutonomousGoal
from agent.service import AgentService
from opportunities.discovery import OpportunityDiscovery
from research import reasoning
from research.models import (
    EvidenceClaim, EvidenceSource, ResearchAssessment, ResearchConflict,
    ResearchNeed, ResearchPlan, ResearchRun, ResearchSynthesis,
)
from research.repository import ResearchRepository
from research.service import ResearchService
from situations.followup import INITIAL_KIND, KIND, goal_id_for, read_followup
from situations.models import SituationState, SituationUpdate
from situations.repository import SituationRepository
from situations.service import SituationService

OWNER = "research-integrity-owner"


def research_run(variant="complete"):
    now = datetime.now(timezone.utc)
    run = ResearchRun(
        id="rr_synthetic_scope", user_id=OWNER, status="completed",
        need=ResearchNeed(question="Quali condizioni sono documentate?"),
        plan=ResearchPlan(goal="Verificare la condizione", geographic_scope="Località Alfa"),
        sources=[EvidenceSource(
            source_id="rs_synthetic", url="https://source.example/observation",
            title="Osservazione sintetica", snippet="Una condizione documentata",
        )],
        assessments=[ResearchAssessment(sufficiency="sufficient")],
        synthesis=ResearchSynthesis(
            answer="Prosa non validata da non trasformare in una nuova claim.",
            claims=[EvidenceClaim(
                statement="La fonte riporta una condizione da rivalutare.",
                supported_by=["rs_synthetic"],
            )],
        ),
        completed_at=now.isoformat(), valid_until=(now + timedelta(hours=1)).isoformat(),
    )
    if variant == "partial":
        run.status = "partial"
        run.assessments[-1].sufficiency = "insufficient"
    elif variant == "no_claims":
        run.synthesis.claims = []
    elif variant == "uncited":
        run.synthesis.claims[0].supported_by = ["rs_not_retrieved"]
    elif variant == "mixed_claims":
        run.synthesis.claims.append(EvidenceClaim(
            statement="Una conclusione non sostenuta dalla ricerca.", supported_by=["rs_not_retrieved"],
        ))
    elif variant == "no_source_url":
        run.sources[0].url = ""
    elif variant == "person_without_facts":
        run.synthesis.claims[0].scope = "person_specific"
    elif variant == "contradictory_scope":
        run.assessments[-1].conflicts = [ResearchConflict(
            about="La fonte riguarda Località Beta, il contesto Località Alfa.",
            positions=["Località Alfa", "Località Beta"],
            source_ids=["rs_synthetic"], resolved=False,
        )]
    elif variant == "missing_place":
        run.plan.geographic_scope = None
        run.assessments[-1].missing_evidence = ["Il luogo della situazione non è stabilito."]
    elif variant == "expired":
        run.valid_until = (now - timedelta(seconds=1)).isoformat()
    elif variant == "old_reuse":
        run.completed_at = (now - timedelta(days=4)).isoformat()
    return run


def research_step():
    return ActionStep(
        step_type="research", capability_needed="web.research",
        intent="Leggere fonti pertinenti alla situazione",
        expected_result="Quali condizioni sono documentate?",
    )


def use_run(monkeypatch, run, captured=None):
    async def persisted_run(self, owner_id, need, **kwargs):
        if captured is not None:
            captured.update(owner=owner_id, need=need, kwargs=kwargs)
        run.need = need
        run.situation_ref = kwargs.get("situation_ref")
        await ResearchRepository(self.db).save(run)
        return run

    monkeypatch.setattr(ResearchService, "run", persisted_run)


@pytest.mark.asyncio
@pytest.mark.parametrize("place", [None, "Località Alfa"])
async def test_research_rereads_owned_situation_without_inventing_a_location(monkeypatch, place):
    db = AsyncMongoMockClient().research_context
    state = SituationState(
        id="sit_owned_scope", user_id=OWNER, summary="Stato sintetico all'aperto",
        location_label=place, facts=["Un fatto attuale"], assumptions=["Un'ipotesi esplicita"],
        linked_object_refs=["place:synthetic_anchor"] if place else [],
    )
    await SituationRepository(db).insert(state)
    # An unrelated profile/place must not become this Situation's location.
    await db.life_places.insert_one({"user_id": OWNER, "id": "unrelated", "locality": "Località Gamma"})
    goal = AutonomousGoal(
        owner_id=OWNER, objective="Seguire uno stato", desired_outcome="Valutare quando serve agire",
        source_refs=[f"situation:{state.id}"],
    )
    captured = {}
    use_run(monkeypatch, research_run(), captured)

    await providers.do_research(db, OWNER, goal, research_step())
    context = json.loads(captured["need"].already_known[0])
    assert context["source_context_unavailable"] is False
    assert context["source_context"][0]["location_label"] == place
    assert context["source_context"][0]["assumptions"] == state.assumptions
    assert context["source_context"][0]["linked_object_refs"] == state.linked_object_refs
    assert "Località Gamma" not in json.dumps(context)
    assert "history" not in context["source_context"][0]

    await db.situations.update_one({"id": state.id, "user_id": OWNER}, {
        "$set": {"location_label": None, "facts": ["Fatto corretto dopo il piano"], "revision": 2},
    })
    await providers.do_research(db, OWNER, goal, research_step())
    fresh = json.loads(captured["need"].already_known[0])["source_context"][0]
    assert fresh["location_label"] is None and fresh["revision"] == 2
    assert fresh["facts"] == ["Fatto corretto dopo il piano"]


@pytest.mark.asyncio
async def test_missing_or_foreign_situation_context_cannot_validate_research(monkeypatch):
    db = AsyncMongoMockClient().research_owner
    foreign = SituationState(
        id="sit_foreign_scope", user_id="another-owner", summary="Private foreign context",
        location_label="Foreign private place",
    )
    await SituationRepository(db).insert(foreign)
    goal = AutonomousGoal(
        owner_id=OWNER, objective="Seguire uno stato", desired_outcome="Rivalutare",
        source_refs=[f"situation:{foreign.id}", "situation:missing"],
    )
    captured = {}
    use_run(monkeypatch, research_run(), captured)
    outcome = await providers.do_research(db, OWNER, goal, research_step())
    context = json.loads(captured["need"].already_known[0])
    assert context == {"source_context": [], "source_context_unavailable": True}
    assert outcome.provenance.research_sufficient is False
    assert foreign.summary not in str(captured)


@pytest.mark.asyncio
async def test_geographic_scope_and_unknowns_reach_assessment_and_synthesis(monkeypatch):
    plan = ResearchPlan(
        goal="Valutare condizioni pertinenti", geographic_scope="Località Alfa",
        known_context=["Il luogo della situazione è Località Alfa"],
        unknowns=["Non è noto se la fonte riguarda lo stesso luogo"],
        freshness_requirement="Osservazione corrente",
    )
    source = EvidenceSource(
        source_id="rs_other_scope", url="https://source.example/other-place",
        title="Condizioni in Località Beta", snippet="Dato riferito a Località Beta",
    )
    seen = []

    async def model(system, user):
        payload = json.loads(user)
        seen.append(payload)
        assert payload["geographic_scope"] == "Località Alfa"
        assert payload["known_context"] == plan.known_context
        assert payload["unknowns"] == plan.unknowns
        if "what_was_found" in payload:
            return {"sufficiency": "insufficient", "missing_evidence": ["Manca una fonte per Località Alfa"]}
        return {"answer": "Il luogo della fonte è diverso", "claims": [], "unresolved": ["Luogo non verificato"]}

    monkeypatch.setattr(reasoning, "_ask_model", model)
    assessment = await reasoning.assess_evidence(
        plan=plan, sources=[source], already_run=["domanda sintetica"], iteration=1, iterations_left=0,
    )
    synthesis = await reasoning.synthesize(plan=plan, sources=[source], assessment=assessment)
    assert assessment.sufficiency == "insufficient" and not synthesis.claims
    assert seen[1]["freshness_requirement"] == plan.freshness_requirement
    # The model identifies the mismatch; this test does not pretend string
    # equality is a machine proof of geographic applicability.


@pytest.mark.asyncio
async def test_reuse_judgement_sees_the_current_source_context(monkeypatch):
    need = ResearchNeed(question="Condizioni correnti", already_known=[json.dumps({
        "source_context": [{"location_label": None, "facts": ["Luogo ancora sconosciuto"]}],
    })])
    seen = {}

    async def model(system, user):
        seen.update(json.loads(user))
        return {"reuse_run_id": None}

    monkeypatch.setattr(reasoning, "_ask_model", model)
    assert await reasoning.consider_reuse(need, [{"run_id": "rr_old", "answer": "Un altro luogo"}]) is None
    assert seen["already_known"] == need.already_known


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", [
    "partial", "no_claims", "uncited", "mixed_claims", "no_source_url", "person_without_facts",
    "contradictory_scope", "missing_place", "expired", "old_reuse", "complete",
])
async def test_only_sufficient_cited_current_research_can_promote_a_situation(monkeypatch, variant):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setattr(OpportunityDiscovery, "note", AsyncMock(return_value={"outcome": "accepted"}))
    db = AsyncMongoMockClient().research_checkpoint
    created = await SituationService(db).apply(
        user_id=OWNER, session_id="synthetic-scope-session", reasoning_epoch="synthetic-scope-epoch",
        update=SituationUpdate(
            operation="create", summary="Una condizione temporanea sintetica",
            attention_intent="Ricontrollare la condizione quando è utile",
        ),
    )
    sid = created["situation"]["id"]
    service = AgentService(db)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())
    goal = await service.repo.get_goal(OWNER, goal_id_for(OWNER, sid))
    fixture_run = research_run(variant)
    use_run(monkeypatch, fixture_run)
    step = research_step()
    outcome = await providers.do_research(db, OWNER, goal, step)
    await service.executor._as_result(OWNER, goal, step, outcome)

    assert outcome.provenance.research_sufficient is (variant == "complete")
    assert fixture_run.synthesis.answer not in outcome.observation
    if variant in ("no_claims", "uncited", "no_source_url", "person_without_facts"):
        assert not outcome.claims, "Free-text answers must not restore rejected claims."
    if variant == "partial":
        assert outcome.status == "partial" and outcome.claims
    if variant == "old_reuse":
        assert outcome.provenance.freshness == "stale"
        assert outcome.provenance.observed_at == fixture_run.completed_at

    result = await service._wait(
        OWNER, goal, ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active"),
        None, AgentRun(owner_id=OWNER, goal_id=goal.id), minutes=20,
        note="Momento scelto per una nuova lettura", model_decision=True,
    )
    assert result["ok"], result
    durable = await service.repo.get_goal(OWNER, goal.id)
    followup = await read_followup(db, OWNER, sid)
    assert durable.source_kind == (KIND if variant == "complete" else INITIAL_KIND)
    assert followup["status"] == ("scheduled" if variant == "complete" else "review_pending")
    if variant != "complete":
        assert followup["next_check_at"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", ["legacy", "expired_before_wait"])
async def test_unattested_or_expired_stored_research_never_proves_a_checkpoint(monkeypatch, metadata):
    from test_situation_wait_integrity_v157 import OWNER as WAIT_OWNER, setup

    db, service, goal, plan, run, sid = await setup(monkeypatch)
    fixture_run = research_run()
    fixture_run.user_id = WAIT_OWNER
    use_run(monkeypatch, fixture_run)
    step = research_step()
    outcome = await providers.do_research(db, WAIT_OWNER, goal, step)
    assert outcome.provenance.research_sufficient is True
    if metadata == "legacy":
        # Old evidence documents lack both new fields; absence is not consent
        # to reinterpret their historic partial/uncited claims as sufficient.
        outcome.provenance.research_sufficient = None
        outcome.provenance.research_valid_until = None
    else:
        outcome.provenance.research_valid_until = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    await service.executor._as_result(WAIT_OWNER, goal, step, outcome)
    result = await service._wait(
        WAIT_OWNER, goal, plan, None, run, minutes=20,
        note="Rivalutare quando esiste evidenza valida", model_decision=True,
    )
    assert result["ok"]
    assert (await service.repo.get_goal(WAIT_OWNER, goal.id)).source_kind == INITIAL_KIND
    assert (await read_followup(db, WAIT_OWNER, sid))["status"] == "review_pending"
