"""Verification must receive the actual result and its cited source intact.

The two synthetic drafts are the 1151/1098-character outputs recorded in the
c38b diagnostic. This reconstructs the production reader/preparation/context
boundary; the historical HTTP request was not recorded. Injected replies and
a real SDK with fake HTTP prove transport, not the quality of a live judgement.
No network, real account, notification or external effect is exercised.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import reasoning
from agent.evidence import EvidenceStore, for_verification
from agent.execution import StepExecutor
from agent.models import ActionPlan, ActionStep, AgentBudget, AgentRun, AutonomousGoal
from agent.service import AgentService, _user_clock_context
from agent.source_refresh import context as source_context
from scripts import autonomy_completion_eval_v162 as gate
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401
from test_agent_preparation_dependency_v162 import fake_gemini


OWNER = gate.OWNER
COMPLETED = """Confronto delle due formule per la gestione dell'archivio digitale su un orizzonte di dodici mesi, basato sui dati indicati nella nota salvata:

1. Formula Mensile
- Costo mensile: 15 euro
- Costo totale per 12 mesi: 180 euro
- Spese iniziali: nulle
- Spazio e assistenza: 100 GB e assistenza uguale all'altra opzione
- Vincoli e rimborso: non specificati ulteriori vincoli nella nota

2. Formula Annuale
- Costo totale anticipato per 12 mesi: 120 euro
- Spese iniziali: nulle
- Spazio e assistenza: 100 GB e assistenza uguale all'altra opzione
- Vincoli e rimborso: l'annuale non prevede rimborso in caso di disdetta anticipata

Sintesi dei costi e differenza:
- Costo totale a 12 mesi (mensile): 180 euro
- Costo totale a 12 mesi (annuale anticipato): 120 euro
- Differenza: la formula annuale comporta un esborso inferiore di 60 euro rispetto al totale della formula mensile su dodici mesi, ma richiede il pagamento anticipato e non prevede rimborso in caso di disdetta anticipata.

Nota di limite: I dati derivano da segnalazione utente registrata in memoria e non costituiscono una conferma diretta o verifica indipendente da parte del fornitore."""
PLANNING_OUTAGE = """Confronto delle opzioni per il mantenimento dell'archivio digitale per un periodo di 12 mesi, basato sui dati riferiti (mem_43262246ed92296b9353):

**Caratteristiche comuni a entrambe le opzioni:**
- Spazio di archiviazione: 100 GB
- Assistenza: ugualmente inclusa
- Spese iniziali: nulle

**Opzione 1: Formula Mensile**
- Costo mensile: 15 euro
- Costo totale a 12 mesi: 180 euro
- Vincoli e condizioni: Dati riferiti dall'utente; nessun cambio di contratto o pagamento autorizzato.

**Opzione 2: Formula Annuale (Anticipata)**
- Costo totale a 12 mesi: 120 euro anticipati
- Vincoli e condizioni: L'annuale non prevede rimborso in caso di disdetta anticipata.

**Confronto dei costi e differenze (orizzonte temporale: 12 mesi):**
- Totale Opzione Mensile: 180 euro
- Totale Opzione Annuale: 120 euro
- Differenza: L'opzione annuale costa 120 euro anticipati rispetto ai 180 euro complessivi della formula mensile, a fronte però dell'assenza di rimborso in caso di disdetta anticipata.

*Nota di limite:* Le informazioni si basano sui dati riferiti dall'utente e non sono confermate dal fornitore."""


async def reconstruct(draft, *, partial=False):
    db = AsyncMongoMockClient().verification_context_v162
    with gate.isolated_engine(db):
        opportunity_id = await gate.seed_case(db, "planning_outage")
        opportunity = await db.opportunities.find_one({"owner_id": OWNER, "id": opportunity_id})
        ref = opportunity["evidence"][0]["ref"]
        text = gate.FIXTURE_NOTE
        if partial:
            text += " Seguito non ancora letto." * 30
            await db.memories.update_one({"user_id": OWNER, "id": ref}, {"$set": {"statement": text}})
        goal = AutonomousGoal(
            owner_id=OWNER, status="active", origin="agent_initiated",
            source_kind="opportunity", opportunity_id=opportunity_id,
            opportunity_revision=opportunity["agent_review_revision"],
            source_refs=[ref], source_situation=source_context(opportunity),
            objective="Mettere a disposizione il confronto scritto dei costi e dei vincoli per la scelta tra le due formule.",
            desired_outcome="Il confronto dettagliato di costi e vincoli per dodici mesi è disponibile per la valutazione dell'utente.",
            # The report did not export admission criteria. These explicit
            # synthetic criteria exercise preservation, not historical replay.
            success_criteria=[
                "Confronto scritto dei totali e della differenza su dodici mesi.",
                "Esplicitare i vincoli riferiti e distinguere i dati non confermati dal fornitore.",
            ],
            stop_conditions=["Nessun pagamento, invio o modifica del contratto autorizzato."],
        )
        await db.agent_goals.insert_one(goal.model_dump())
        read = ActionStep(step_type="inspect", capability_needed="information.read", input_refs=[ref],
            intent="Leggere la nota salvata con i dettagli delle formule.",
            expected_result="I dati della nota con provenienza, vincoli e copertura della lettura.")
        result = await StepExecutor(db).run(OWNER, goal, read, may_touch_the_world=False)
        assert result.status == ("partial" if partial else "succeeded")
        read.status, read.note = "succeeded", result.observation
        source, = await EvidenceStore(db).for_goal(OWNER, goal.id)
        prepare = ActionStep(ordinal=1, step_type="prepare", capability_needed="document.create",
            input_refs=[ref], intent="Produrre il confronto scritto dei costi e dei vincoli per dodici mesi.",
            expected_result=goal.desired_outcome)
        replies = AsyncMock(side_effect=[
            {"content": draft, "evidence_ids": [source.id]},
            {"verified": True, "content": draft, "evidence_ids": [source.id]},
        ])
        with patch.object(reasoning, "_ask_model", replies):
            made = await StepExecutor(db).run(OWNER, goal, prepare, may_touch_the_world=False)
        assert made.status == "succeeded" and replies.await_count == 2
        prepare.status, prepare.note = "succeeded", made.observation
        steps = [read, prepare]
        if draft == PLANNING_OUTAGE:
            pending = prepare.model_copy(deep=True, update={"id": "stp_pending_preparation", "status": "pending", "note": ""})
            prepare.ordinal = 2
            steps = [read, pending, prepare]
        plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, steps=steps,
            plan_summary="Legge la nota salvata e produce il confronto scritto di costi e vincoli a dodici mesi.")
        await AgentService(db).repo.save_plan(plan)
        # Reload exactly as a subsequent worker would. Text, references and
        # reader limits must not depend on in-process preparation state.
        goal = AutonomousGoal(**await db.agent_goals.find_one({"owner_id": OWNER, "id": goal.id}))
        evidence = await EvidenceStore(db).for_goal(OWNER, goal.id)
        assert len(evidence) == 4 and goal.prepared_text == draft
        payload = {
            "goal": await AgentService(db)._reasoning_goal(OWNER, goal),
            "what_was_done": {
                "what_was_found": for_verification(evidence),
                "steps": [step.for_ai() for step in plan.steps],
                "what_was_prepared": [], "prepared_result": goal.prepared_text,
                "prepared_source_refs": list(goal.prepared_sources),
                "local_clock": await _user_clock_context(db, OWNER),
                "what_the_services_said": [],
            },
        }
    return SimpleNamespace(db=db, goal=goal, plan=plan, source=source, evidence=evidence, payload=payload, text=text)


def assert_complete(payload, original, source):
    done = payload["what_was_done"]
    assert done["prepared_result"] == original["what_was_done"]["prepared_result"]
    assert done["prepared_source_refs"] == [source.id]
    actual = next(row for row in done["what_was_found"] if row["evidence_id"] == source.id)
    expected = next(row for row in original["what_was_done"]["what_was_found"] if row["evidence_id"] == source.id)
    assert actual == expected
    for key in ("objective", "desired_outcome", "success_criteria", "stop_conditions", "user_clarifications_not_authority"):
        assert payload["goal"][key] == original["goal"][key]


@pytest.mark.asyncio
@pytest.mark.parametrize("draft,expected_length", [(COMPLETED, 1151), (PLANNING_OUTAGE, 1098)],
                         ids=["completed_1151", "planning_outage_1098"])
async def test_recorded_draft_and_complete_source_survive_normal_verification_budget(monkeypatch, draft, expected_length):
    assert len(draft) == expected_length
    h = await reconstruct(draft)
    original = deepcopy(h.payload)
    assert len(json.dumps(original, ensure_ascii=False)) > 9000
    captured = []

    async def reply(_system, encoded):
        assert len(encoded) <= 9000
        captured.append(json.loads(encoded))
        return {"outcome": "partially_achieved", "what_is_missing": "Giudizio sintetico, non corretto dal formatter."}

    monkeypatch.setattr(reasoning, "_ask_model", reply)
    result = await reasoning.verify_goal(h.payload["goal"], evidence=h.payload["what_was_done"])
    assert result["outcome"] == "partially_achieved"
    assert len(captured) == 1
    assert_complete(captured[0], original, h.source)
    assert h.payload == original


@pytest.mark.asyncio
@pytest.mark.parametrize("history_count", [0, 13], ids=["current_citation", "citation_before_latest_twelve"])
async def test_finish_binds_current_saved_result_and_citation_through_real_sdk_http(monkeypatch, history_count):
    h = await reconstruct(PLANNING_OUTAGE)
    for index in range(history_count):
        old_draft = h.evidence[-1].model_copy(deep=True, update={
            "id": f"evd_generated_history_{index}",
            "observed_at": (datetime.now(timezone.utc) + timedelta(seconds=index)).isoformat(),
        })
        await EvidenceStore(h.db).record(old_draft)
    if history_count:
        latest = await EvidenceStore(h.db).for_goal(OWNER, h.goal.id)
        assert h.source.id not in {row["evidence_id"] for row in for_verification(latest)}
        selected = for_verification(latest, required_refs=h.goal.prepared_sources)
        assert len(selected) == 12 and h.source.id in {row["evidence_id"] for row in selected}

    def reply(system, payload):
        assert "judge its actual wording" in system
        assert_complete(payload, h.payload, h.source)
        assert payload["context_truncated"] is True
        assert payload["verification_context_omitted"]["generated_artifact_evidence_ids"]
        assert not any(row.get("generated_artifact") for row in payload["what_was_done"]["what_was_found"])
        # The formatter must not turn either a model's incomplete judgement
        # or a missing arithmetic conclusion into a successful completion.
        return {"outcome": "partially_achieved", "reasoning": "Giudizio sintetico.",
                "what_is_missing": "Manca una conclusione richiesta nel risultato scritto."}

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(h.db, mode="live") as probe:
        service = AgentService(h.db)
        pause = AsyncMock(return_value={"state": "verification_remains_open"})
        monkeypatch.setattr(service, "_pause", pause)
        # This test covers the complete verification payload, not the later
        # repair decision. Its partial verdict now reaches reconsideration;
        # real repair after that boundary is covered by verification_recovery.
        reconsider = AsyncMock(return_value=None)
        with patch.object(service, "_reconsider", reconsider):
            result = await service._finish(OWNER, h.goal, h.plan,
                AgentRun(owner_id=OWNER, goal_id=h.goal.id), AgentBudget(), language="it")
        assert result == {"state": "verification_remains_open"}
        assert pause.await_args.args[-1] == "Manca una conclusione richiesta nel risultato scritto."
        assert reconsider.await_count == 1
        assert reconsider.await_args.kwargs["what_happened"]["result"]["what_is_missing"] == pause.await_args.args[-1]
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert not probe.network.blocked and not probe.blocked_effects
        assert await h.db.agent_goals.count_documents({"owner_id": OWNER, "status": "completed"}) == 0
        assert await h.db.agent_journal.count_documents({"owner_id": OWNER, "goal_id": h.goal.id,
                                                       "kind": "verified", "detail.outcome": "partially_achieved"}) == 1


@pytest.mark.asyncio
async def test_partial_read_qualifiers_are_preserved_without_becoming_complete(monkeypatch):
    h = await reconstruct(COMPLETED, partial=True)
    original = deepcopy(h.payload)
    source_row = next(row for row in original["what_was_done"]["what_was_found"] if row["evidence_id"] == h.source.id)
    assert source_row["memory_reads"][0]["next_offset"] == 600
    model = AsyncMock(return_value={"outcome": "uncertain", "what_is_missing": "Seguito della fonte non letto."})
    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await reasoning.verify_goal(h.payload["goal"], evidence=h.payload["what_was_done"])
    assert result["outcome"] == "uncertain"
    encoded = model.await_args.args[1]
    assert len(encoded) <= 9000
    assert_complete(json.loads(encoded), original, h.source)
    assert h.payload == original


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["absent_row", "wrong_id", "empty_binding"])
async def test_missing_current_citation_is_unavailable_before_any_model_call(monkeypatch, caplog, missing):
    h = await reconstruct(COMPLETED)
    payload = deepcopy(h.payload)
    if missing == "absent_row":
        payload["what_was_done"]["what_was_found"] = [row for row in payload["what_was_done"]["what_was_found"]
                                                     if row["evidence_id"] != h.source.id]
    elif missing == "wrong_id":
        payload["what_was_done"]["prepared_source_refs"] = ["evd_not_supplied"]
    else:
        payload["what_was_done"]["prepared_source_refs"] = []
    model = AsyncMock(return_value={"outcome": "achieved"})
    monkeypatch.setattr(reasoning, "_ask_model", model)
    with caplog.at_level("INFO", logger="agent.reasoning"):
        answer = await reasoning.verify_goal(payload["goal"], evidence=payload["what_was_done"])
    assert answer is None and model.await_count == 0
    assert "prepared_source_missing" in caplog.text
    assert h.goal.status == "active" and h.goal.prepared_text == COMPLETED


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["deleted_evidence", "superseded_evidence", "foreign_evidence", "corrected_memory", "forgotten_memory"])
async def test_finish_keeps_owner_and_current_source_fences_before_verification(monkeypatch, changed):
    h = await reconstruct(COMPLETED)
    query = {"owner_id": OWNER, "goal_id": h.goal.id, "id": h.source.id}
    if changed == "deleted_evidence":
        await h.db.agent_evidence.delete_one(query)
    elif changed == "superseded_evidence":
        await h.db.agent_evidence.update_one(query, {"$set": {"superseded": True}})
    elif changed == "foreign_evidence":
        await h.db.agent_evidence.update_one(query, {"$set": {"owner_id": "another-synthetic-owner"}})
    else:
        mutation = {"statement": h.text + " Condizione corretta."} if changed == "corrected_memory" else {"status": "forgotten"}
        await h.db.memories.update_one({"user_id": OWNER, "id": h.goal.source_refs[0]}, {"$set": mutation})
    model = AsyncMock(return_value={"outcome": "achieved"})
    with gate.isolated_engine(h.db), patch.object(reasoning, "_ask_model", model):
        service = AgentService(h.db)
        result = await service._finish(OWNER, h.goal, h.plan,
            AgentRun(owner_id=OWNER, goal_id=h.goal.id), AgentBudget(), language="it")
        assert result["state"] in ("source_changed", "abandoned")
        assert model.await_count == 0 and not h.goal.prepared_text
        assert await h.db.agent_goals.count_documents({"owner_id": OWNER, "status": "completed"}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", ["criteria", "cited_sources", "uncited_source"])
async def test_material_overflow_is_explicitly_unavailable_without_shortening_or_dropping_facts(monkeypatch, caplog, extra):
    h = await reconstruct(COMPLETED)
    payload = deepcopy(h.payload)
    done = payload["what_was_done"]
    if extra == "criteria":
        # Technical bound probe, not an admitted natural-language fixture.
        payload["goal"]["success_criteria"] = ["Criterio materiale da conservare. " * 400]
    else:
        source_row = next(row for row in done["what_was_found"] if row["evidence_id"] == h.source.id)
        for index in range(8):
            additional = deepcopy(source_row)
            additional["evidence_id"] = f"evd_material_{index}"
            additional["what_was_found"] = "Condizione materiale potenzialmente contraria. " * 12
            done["what_was_found"].append(additional)
            if extra == "cited_sources":
                done["prepared_source_refs"].append(additional["evidence_id"])
    original = deepcopy(payload)
    model = AsyncMock(return_value={"outcome": "achieved"})
    monkeypatch.setattr(reasoning, "_ask_model", model)
    with caplog.at_level("INFO", logger="agent.reasoning"):
        result = await reasoning.verify_goal(payload["goal"], evidence=done)
    assert result is None and model.await_count == 0
    assert "material_context_exceeds_budget" in caplog.text
    assert payload == original and h.goal.status == "active"
