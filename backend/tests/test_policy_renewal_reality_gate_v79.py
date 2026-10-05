from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AgentBudget, AgentRun
from agent.service import AgentService
from opportunities.discovery import OpportunityDiscovery


OWNER = "alice"
DOC_ID = "policy_renewal_v79"


async def _prepare_opportunity(monkeypatch, db):
    from opportunities import reasoning as opportunity_reasoning
    from opportunities import snapshot

    await db.documents.insert_one({
        "id": DOC_ID,
        "user_id": OWNER,
        "filename": "polizza_casa.txt",
        "display_title": "Polizza Casa",
        "extracted_text": (
            "POLIZZA CASA - condizioni sintetiche di test. "
            "Premio annuo attuale: 480 euro. "
            "Scadenza e rinnovo: 20 ottobre 2026. "
            "Rinnovo automatico: sì. "
            "Termine per comunicare la disdetta: 10 ottobre 2026. "
            "Massimale responsabilità civile: 500.000 euro. "
            "Franchigia danni acqua: 250 euro."
        ),
    })

    async def prepared(_db, owner_id, *, changes=None):
        docs = await snapshot._documents(
            _db, owner_id, __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ), document_ids=[DOC_ID],
        )
        return {
            "documents": docs,
            "what_changed": list(changes or []),
            "temporal": {"local_date": "2026-10-05"},
            "unavailable_sources": [],
        }

    monkeypatch.setattr(snapshot, "build", prepared)
    monkeypatch.setattr("opportunities.discovery.COOLDOWN_SECONDS", 0)

    async def scan(state, **kwargs):
        docs = state.get("documents") or []
        assert len(docs) == 1
        assert docs[0]["ref"] == f"document:{DOC_ID}"
        excerpt = docs[0]["unverified_excerpt"]
        assert "20 ottobre 2026" in excerpt
        assert "480 euro" in excerpt
        return {
            "opportunities": [{
                "identity_key": "renewal-window:policy-home",
                "what": "La polizza ha una scadenza vicina e condizioni da verificare prima del rinnovo.",
                "why_it_matters": (
                    "Prima che la finestra utile si chiuda conviene capire condizioni attuali "
                    "e alternative realmente confrontabili."
                ),
                "why_now": "La scadenza indicata nel documento è vicina.",
                "initiative": "prepare",
                "what_i_can_do": (
                    "Posso leggere le condizioni, cercare alternative aggiornate e confrontare "
                    "solo ciò che è verificabile."
                ),
                "evidence_refs": [f"document:{DOC_ID}"],
            }]
        }

    monkeypatch.setattr(opportunity_reasoning, "scan", AsyncMock(side_effect=scan))

    discovery = OpportunityDiscovery(db)
    await discovery.note(
        OWNER,
        source="documents",
        kind="document.updated",
        entity_ref=f"document:{DOC_ID}",
        entity_kind="document",
        wake=False,
    )
    review = await discovery.review(OWNER, force=True)
    assert review.ran is True
    assert review.scan is not None
    assert len(review.scan.created) == 1
    return review.scan.created[0]


@pytest.mark.asyncio
async def test_near_renewal_document_becomes_read_research_compare_without_world_effect(monkeypatch):
    """
    v79 Reality Gate:
      near-renewal document -> Opportunity -> autonomous goal
      -> exact private document read -> bounded public research -> comparison.

    There is no policy/insurance router in production. The cognitive layers
    decide significance and compose generic capabilities.
    """
    from agent import reasoning
    from comparison.service import ComparisonService
    from research.models import (
        EvidenceClaim,
        EvidenceSource,
        ResearchAssessment,
        ResearchRun,
        ResearchSynthesis,
    )
    from research.service import ResearchService

    db = AsyncMongoMockClient().test
    opportunity = await _prepare_opportunity(monkeypatch, db)
    service = AgentService(db)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())

    async def decide_goal(payload, *, language="it"):
        context = payload.get("source_context") or []
        assert len(context) == 1
        assert context[0]["ref"] == f"document:{DOC_ID}"
        assert "480 euro" in context[0]["unverified_excerpt"]
        return {
            "outcome": "create_goal",
            "objective": "Verificare il rinnovo della polizza prima che la finestra utile si chiuda",
            "desired_outcome": (
                "Avere condizioni attuali e alternative confrontabili, senza cambiare contratto "
                "senza autorizzazione"
            ),
            "why_now": "La scadenza è vicina.",
            "success_criteria": [
                "Le condizioni correnti sono lette dal documento",
                "Le alternative sono sostenute da fonti aggiornate",
                "Il confronto dichiara i limiti e non inventa equivalenze",
            ],
            "stop_conditions": ["La polizza risulta non più attiva o la scadenza viene superata"],
            "reasoning": "La finestra temporale rende utile preparare il confronto adesso.",
        }

    monkeypatch.setattr(reasoning, "decide_goal", decide_goal)

    admitted = await service.consider(
        OWNER,
        situation={
            "what": opportunity.semantic_summary,
            "why_it_matters": opportunity.why_it_matters,
            "why_now": opportunity.why_now,
        },
        origin="agent_initiated",
        opportunity_id=opportunity.id,
        source_kind="opportunity",
        source_refs=[f"document:{DOC_ID}"],
    )
    assert admitted["outcome"] == "create_goal"
    goal = await service.repo.get_goal(OWNER, admitted["goal_id"])
    assert goal is not None
    assert goal.origin == "agent_initiated"

    async def make_plan(goal_payload, *, capabilities, context, language="it"):
        names = {row.get("capability") for row in capabilities}
        assert {"document.read", "web.research", "comparison.run"} <= names
        assert f"document:{DOC_ID}" in goal_payload["source_refs"]
        return {
            "plan_summary": (
                "Leggere la polizza, cercare alternative correnti e confrontarle "
                "senza toccare il contratto."
            ),
            "expected_outcome": "Un confronto utilizzabile prima della scadenza.",
            "assumptions": [],
            "known_constraints": ["Nessuna disdetta o sottoscrizione viene eseguita."],
            "steps": [
                {
                    "intent": "Leggere le condizioni esatte della polizza corrente",
                    "step_type": "inspect",
                    "capability_needed": "document.read",
                    "input_refs": [f"document:{DOC_ID}"],
                    "parameters": {"document_offset": 0},
                    "expected_result": "Scadenza, premio, rinnovo, massimale e franchigia correnti",
                    "external_effect": False,
                    "reversibility": "easily",
                },
                {
                    "intent": "Cercare alternative attuali con condizioni abbastanza dettagliate da confrontare",
                    "step_type": "research",
                    "capability_needed": "web.research",
                    "input_refs": [],
                    "parameters": {},
                    "expected_result": (
                        "Alternative attuali con premio, coperture, massimali e franchigie verificabili"
                    ),
                    "external_effect": False,
                    "reversibility": "easily",
                },
                {
                    "intent": "Confrontare la polizza corrente con le alternative realmente comparabili",
                    "step_type": "compare",
                    "capability_needed": "comparison.run",
                    "input_refs": [],
                    "parameters": {},
                    "expected_result": "Un confronto con limiti espliciti e senza equivalenze inventate",
                    "external_effect": False,
                    "reversibility": "easily",
                },
            ],
        }

    monkeypatch.setattr(reasoning, "make_plan", make_plan)
    monkeypatch.setattr(
        service.capabilities,
        "available",
        AsyncMock(return_value=[
            {"capability": "document.read", "status": "available_real", "writes": False},
            {"capability": "web.research", "status": "available_real", "writes": False},
            {"capability": "comparison.run", "status": "available_real", "writes": False},
        ]),
    )

    research_run = ResearchRun(
        id="rr_policy_market",
        user_id=OWNER,
        need=__import__("research.models", fromlist=["ResearchNeed"]).ResearchNeed(
            question="Alternative correnti confrontabili",
            purpose="Confrontare prima della scadenza",
        ),
        sources=[
            EvidenceSource(
                source_id="src_alt_a",
                url="https://example.test/alt-a",
                title="Alternativa A - condizioni",
                publisher="Operatore A",
            ),
            EvidenceSource(
                source_id="src_alt_b",
                url="https://example.test/alt-b",
                title="Alternativa B - condizioni parziali",
                publisher="Operatore B",
            ),
        ],
        assessments=[ResearchAssessment(
            sufficiency="sufficient",
            reason="Una alternativa è dettagliata; l'altra resta incompleta.",
        )],
        synthesis=ResearchSynthesis(
            answer=(
                "Alternativa A pubblica premio 410 euro, massimale 500.000 euro e "
                "franchigia 250 euro. Alternativa B pubblica solo il prezzo."
            ),
            claims=[
                EvidenceClaim(
                    statement=(
                        "Alternativa A: premio 410 euro, massimale 500.000 euro, "
                        "franchigia 250 euro."
                    ),
                    supported_by=["src_alt_a"],
                ),
                EvidenceClaim(
                    statement=(
                        "Alternativa B: prezzo pubblicato 360 euro, ma nella fonte letta "
                        "mancano massimale e franchigia necessari al confronto."
                    ),
                    supported_by=["src_alt_b"],
                ),
            ],
            caveats=["Alternativa B non è confrontabile in modo affidabile con i dati disponibili."],
        ),
        status="completed",
        outcome_note="Ricerca completata con una alternativa confrontabile e una incompleta.",
    )

    async def research(self, user_id, need, **kwargs):
        assert user_id == OWNER
        assert "massimali" in need.question.lower() or "franchig" in need.question.lower()
        return research_run

    monkeypatch.setattr(ResearchService, "run", research)

    async def compare(self, user_id, need, alternatives, **kwargs):
        assert user_id == OWNER
        assert kwargs.get("research_run_ids") == ["rr_policy_market"]
        return SimpleNamespace(
            id="cmp_policy_v79",
            recommendation=SimpleNamespace(recommended="Alternativa A"),
            outcome_note=(
                "Alternativa A è confrontabile con i dati disponibili; Alternativa B "
                "resta esclusa dal confronto affidabile perché mancano condizioni essenziali."
            ),
        )

    monkeypatch.setattr(ComparisonService, "run", compare)

    run = AgentRun(owner_id=OWNER, goal_id=goal.id, background=True)
    budget = AgentBudget()
    plan = await service._build_plan(OWNER, goal, run, budget, language="it")
    assert plan is not None
    assert [s.capability_needed for s in plan.steps] == [
        "document.read", "web.research", "comparison.run"
    ]

    # Execute the real agent adapters in order. They may read/research/compare,
    # but there is no execute step and therefore no external contract effect.
    for step in plan.steps:
        outcome = await service._do_step(
            OWNER, goal, plan, step, run, budget, language="it"
        )
        assert outcome is None

    evidence = await service.evidence.for_goal(OWNER, goal.id)
    blob = str([e.for_ai() for e in evidence])
    assert "480 euro" in blob
    assert "410 euro" in blob
    assert "Alternativa A" in blob
    assert "Alternativa B" in blob
    assert "mancano massimale e franchigia" in blob
    assert await service.evidence.research_refs(OWNER, goal.id) == ["rr_policy_market"]

    # A read-only autonomous investigation is not complete until it has a
    # useful grounded result for the person. Exercise that completion contract:
    # prepare from the evidence, audit the draft, then verify the outcome.
    import json

    async def draft_and_audit(system, payload):
        data = json.loads(payload)
        if "Produce the actual useful draft" in system:
            rows = data["evidence"]
            ids = [row["id"] for row in rows]
            return {
                "content": (
                    "La polizza attuale indica 480 euro annui e scadenza il 20 ottobre 2026. "
                    "Alternativa A indica 410 euro con massimale 500.000 euro e franchigia "
                    "250 euro; con i dati disponibili è confrontabile. Alternativa B costa "
                    "meno, ma non ha massimale e franchigia verificabili e quindi non la "
                    "considero una scelta affidabile."
                ),
                "evidence_ids": ids,
            }
        rows = data["evidence"]
        ids = [row["id"] for row in rows]
        return {
            "verified": True,
            "content": (
                "La polizza attuale indica 480 euro annui e scadenza il 20 ottobre 2026. "
                "Alternativa A indica 410 euro con massimale 500.000 euro e franchigia "
                "250 euro; con i dati disponibili è confrontabile. Alternativa B costa "
                "meno, ma non ha massimale e franchigia verificabili e quindi non la "
                "considero una scelta affidabile."
            ),
            "evidence_ids": ids,
        }

    async def verify_goal(goal_payload, *, evidence, language="it"):
        prepared = str(evidence.get("prepared_result") or "")
        assert "480 euro" in prepared
        assert "410 euro" in prepared
        assert "non la considero una scelta affidabile" in prepared
        return {
            "outcome": "achieved",
            "reasoning": (
                "Il confronto utile è stato preparato da lettura privata, ricerca esterna "
                "e confronto, senza eseguire modifiche al contratto."
            ),
            "what_is_missing": "",
            "revisit_in_hours": None,
        }

    monkeypatch.setattr(reasoning, "_ask_model", draft_and_audit)
    monkeypatch.setattr(reasoning, "verify_goal", verify_goal)
    monkeypatch.setattr(service, "_observe_life_change", AsyncMock())

    completed = await service._finish(
        OWNER, goal, plan, run, budget, language="it"
    )
    assert completed["state"] == "completed"
    saved = await service.repo.get_goal(OWNER, goal.id)
    assert saved is not None
    assert "Alternativa A" in saved.prepared_text
    assert "Alternativa B" in saved.prepared_text
    assert "non la considero una scelta affidabile" in saved.prepared_text

    assert await service.executor.intents_for(OWNER, goal.id) == []
    assert await service.executor.receipts_for(OWNER, goal.id) == []


@pytest.mark.asyncio
async def test_incomplete_offer_never_becomes_fake_saving_or_winner(monkeypatch):
    """If the comparison engine refuses a winner, the agent adapter must not invent one."""
    from agent import providers
    from agent.models import ActionStep, AutonomousGoal
    from comparison.service import ComparisonService

    db = AsyncMongoMockClient().test
    goal = AutonomousGoal(
        id="goal_policy_negative_v79",
        owner_id=OWNER,
        status="active",
        objective="Confrontare alternative prima del rinnovo",
        desired_outcome="Sapere se esiste davvero una scelta migliore",
    )
    step = ActionStep(
        id="compare_incomplete_v79",
        ordinal=0,
        intent="Confrontare solo offerte con condizioni equivalenti verificabili",
        step_type="compare",
        capability_needed="comparison.run",
    )

    async def insufficient(self, user_id, need, alternatives, **kwargs):
        return SimpleNamespace(
            id="cmp_policy_incomplete",
            recommendation=None,
            outcome_note=(
                "Non posso consigliare un cambio: l'offerta più economica non pubblica "
                "massimale e franchigia comparabili."
            ),
        )

    monkeypatch.setattr(ComparisonService, "run", insufficient)

    outcome = await providers.do_comparison(
        db,
        OWNER,
        goal,
        step,
        research_refs=["rr_incomplete_offer"],
    )

    assert outcome.status == "partial"
    assert outcome.error_type == "no_clear_choice"
    text = " ".join(c.text for c in outcome.claims)
    assert "non posso consigliare" in text.lower()
    assert "piu adatta risulta" not in text.lower()
    assert "risparm" not in text.lower()
