"""Planning previews do not execute the source read needed by preparation.

Production reasoning, ProviderManager, the Gemini adapter and the installed
SDK use a fake HTTP transport. Replies are synthetic decisions, not evidence
of model quality. The service, reader, evidence store and preparation run
against owned in-memory records; no network or external effect is allowed.
"""
from copy import deepcopy
import json
from unittest.mock import AsyncMock

import httpx
from mongomock_motor import AsyncMongoMockClient
import pytest
from test_preparation_passages_v162 import source_claim

from agent import reasoning
from agent.models import ActionPlan, ActionStep, AgentBudget, AgentRun, AutonomousGoal
from agent.service import AgentService
from llm import manager as llm_manager
from scripts import autonomy_completion_eval_v162 as gate
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401


OWNER = gate.OWNER
MEMORY = "mem_synthetic_preparation_dependency"
SOURCE = (
    "Sto valutando due formule e mi manca il confronto scritto. Ho annotato "
    "che A costa 84 crediti per quattro periodi e B costa 25 crediti per periodo. "
    "La quota di A non è rimborsabile."
)
RESULT = (
    "Secondo la nota salvata, su quattro periodi A costa 84 crediti e B 100: "
    "la differenza è 16 crediti. La quota di A non è rimborsabile. "
    "Il confronto usa le condizioni annotate, senza verificarne l'attualità esterna."
)


def comparison_claim_review(evidence_id, *, price_a=84):
    """Explicit audit data for SOURCE (or its controlled 88-credit correction).

    This does not inspect or validate a model answer. Tests still choose their
    own content/verdict, including deliberately mistaken audits.
    """
    return [
        {"claim": f"Su quattro periodi A costa {price_a}, B 100; differenza {100 - price_a} crediti.",
         "premises": "Prezzi annotati applicati al medesimo orizzonte di quattro periodi.",
         "support": "derived", "correction": "", "evidence_ids": [evidence_id],
         "source_quotes": [{"evidence_id": evidence_id,
             "quote": f"A costa {price_a} crediti per quattro periodi e B costa 25 crediti per periodo."}]},
        {"claim": "La quota di A non è rimborsabile.",
         "premises": "La condizione riguarda A; non stabilisce vincoli per B.",
         "support": "stated", "correction": "", "evidence_ids": [evidence_id],
         "source_quotes": [{"evidence_id": evidence_id, "quote": "La quota di A non è rimborsabile."}]},
    ]


def read_step(*, offset=0, version=None):
    parameters = {"memory_offset": offset}
    if version:
        parameters["memory_version"] = version
    return {
        "step_type": "inspect", "capability_needed": "information.read",
        "intent": "Leggere la parte necessaria della nota citata.",
        "input_refs": [MEMORY], "parameters": parameters,
        "expected_result": "Le condizioni della nota con provenienza e limiti.",
    }


def prepare_step():
    return {
        "step_type": "prepare", "capability_needed": "document.create",
        "intent": "Preparare il confronto sostenuto dalle condizioni lette.",
        "input_refs": [MEMORY],
        "expected_result": "Il confronto scritto con premesse e limiti espliciti.",
    }


async def seed(db, *, partial=False):
    text = SOURCE
    if partial:
        text += " " + "Contesto. " * 60 + "Condizione nel seguito: conta la durata effettiva."
        assert 600 < len(text) < 1200
    goal = AutonomousGoal(
        owner_id=OWNER, status="active", source_kind="memory", source_refs=[MEMORY],
        objective="Preparare il confronto delle condizioni annotate.",
        desired_outcome="Un confronto scritto con premesse e limiti espliciti.",
        success_criteria=["Confrontare quattro periodi senza modificare contratti."],
    )
    await db.agent_goals.insert_one(goal.model_dump())
    await db.memories.insert_one({
        "id": MEMORY, "user_id": OWNER, "status": "known", "revision": 1,
        "statement": text, "authority": "user_stated", "epistemic_status": "known",
        "created_at": "2020-01-01T00:00:00+00:00",
    })
    return goal, text


def fake_gemini(monkeypatch, reply):
    """Keep the real serialization path and block every uncontrolled transport."""
    forwarded, transported = [], []
    original_chat = llm_manager.ProviderManager.chat

    async def observe_manager(self, **kwargs):
        forwarded.append({"system": kwargs["system"], "user": kwargs["user"]})
        return await original_chat(self, **kwargs)

    def respond(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        body = json.loads(request.content)
        system = "".join(part.get("text", "") for part in body["systemInstruction"]["parts"])
        user = "".join(part.get("text", "") for content in body["contents"] for part in content["parts"])
        assert {"system": system, "user": user} == forwarded[-1]
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["temperature"] == pytest.approx(0.2)
        assert len(user) <= 9000
        payload = json.loads(user)
        transported.append({"system": system, "payload": payload})
        answer = reply(system, payload)
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps(answer)}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2, "totalTokenCount": 6},
        })

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda *args, **kwargs: httpx.MockTransport(respond))
    monkeypatch.setattr(llm_manager, "_runtime_preferred", "gemini2")
    monkeypatch.setattr(llm_manager, "_manager", llm_manager.ProviderManager())
    monkeypatch.setattr(llm_manager.ProviderManager, "chat", observe_manager)
    return transported


@pytest.mark.asyncio
async def test_complete_preview_reaches_sdk_but_first_step_really_reads_before_preparation(monkeypatch):
    db = AsyncMongoMockClient().preparation_dependency_plan
    goal, text = await seed(db)
    response = {
        "planning_outcome": "plan", "plan_summary": "Leggere la nota e preparare il confronto.",
        "steps": [read_step(), prepare_step()],
    }

    def reply(system, payload):
        context = payload["context"]["current_source_context"]
        row, = context["sources"]
        assert row["ref"] == MEMORY and row["statement"] == text
        assert row["excerpt_truncated"] is False and row["authority"] == "user_stated"
        assert context["unavailable"] is False
        assert "even when the preview contains every fact needed" in system
        assert "An omitted evidence inventory is not proof the store is empty" in system
        assert "It does not fetch sources from its input_refs" in system
        return response

    transported = fake_gemini(monkeypatch, reply)
    # 'live' selects the production reasoning/SDK, whose sole HTTP transport
    # above is synthetic. No admission fixture or real-model choice is forced.
    with gate.isolated_engine(db, mode="live") as probe:
        service = AgentService(db)
        run, budget = AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget()
        plan = await service._build_plan(OWNER, goal, run, budget, language="it")
        assert [step.capability_needed for step in plan.steps] == ["information.read", "document.create"]
        assert plan.steps[0].input_refs == [MEMORY] and plan.steps[0].parameters["memory_offset"] == 0
        assert await db.agent_evidence.count_documents({}) == 0
        assert not goal.prepared_text

        decision, step = await service._next(OWNER, goal, plan, run, budget, language="it")
        assert decision == "execute" and step.id == plan.steps[0].id
        await service._do_step(OWNER, goal, plan, step, run, budget, language="it")

        evidence, = await service.evidence.for_goal(OWNER, goal.id)
        assert evidence.claim == text and evidence.provenance.source_refs == [MEMORY]
        assert evidence.provenance.memory_reads[0].offset == 0
        assert evidence.provenance.memory_reads[0].next_offset is None
        assert plan.steps[0].status == "succeeded" and plan.steps[1].status == "pending"
        assert not goal.prepared_text and goal.is_open
        assert probe.steps == [{"capability": "information.read", "status": "succeeded"}]
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert not probe.network.blocked and not probe.blocked_effects


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_next_choice_sees_real_evidence_and_reuses_it_or_its_exact_cursor(monkeypatch, partial):
    db = AsyncMongoMockClient().preparation_dependency_current
    goal, text = await seed(db, partial=partial)
    expected_step, source = None, None

    def reply(system, payload):
        if "what_happened" in payload:
            # A final page is still an excerpt: the existing reconsideration
            # sees its coverage instead of silently upgrading it to a full read.
            assert partial
            result = payload["what_happened"]["result"]
            assert result["status"] == "partial" and result["problem"] is None
            page, = result["memory_reads"]
            assert page["offset"] == 600 and page["version"] == source.provenance.memory_reads[0].version
            assert page["next_offset"] is None and page["end"] == page["total"] == len(text)
            return {"decision": "continue", "reasoning": "La lettura ha raggiunto la fine; resta la preparazione."}
        row, = payload["what_has_been_found"]
        assert row["evidence_id"] == source.id
        assert row["what_was_found"] == text[:600]
        assert row["memory_reads"] == source.provenance.for_ai()["memory_reads"]
        assert "same source/version and the parts needed" in system
        assert "If current evidence is already sufficient, use it without another read" in system
        assert "returned continuation cursor and version" in system
        return {"decision": "execute", "step_id": expected_step.id,
                "reasoning": "Decisione sintetica sulla copertura effettiva della lettura."}

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        service = AgentService(db)
        result = await service.executor.run(
            OWNER, goal, ActionStep(**read_step()), may_touch_the_world=False,
        )
        assert result.status == ("partial" if partial else "succeeded")
        source, = await service.evidence.for_goal(OWNER, goal.id)
        cursor = source.provenance.memory_reads[0]
        # A pending read in a revised plan may already be satisfied. The real
        # next-step path receives evidence and may select preparation directly.
        candidate_read = ActionStep(ordinal=0, **read_step(
            offset=cursor.next_offset if partial else 0,
            version=cursor.version if partial else None,
        ))
        candidate_prepare = ActionStep(ordinal=1, **prepare_step())
        plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active",
                          steps=[candidate_read, candidate_prepare])
        await service.repo.save_plan(plan)
        expected_step = candidate_read if partial else candidate_prepare
        run, budget = AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget()

        decision, step = await service._next(OWNER, goal, plan, run, budget, language="it")
        assert decision == "execute" and step.id == expected_step.id
        assert len(probe.steps) == 1  # Judging the next step performs no extra read.
        if partial:
            await service._do_step(OWNER, goal, plan, step, run, budget, language="it")
            sources = await service.evidence.for_goal(OWNER, goal.id)
            continuation, = [item for item in sources if item.id != source.id]
            assert continuation.claim == text[cursor.next_offset:]
            page = continuation.provenance.memory_reads[0]
            assert page.offset == cursor.next_offset == 600 and page.version == cursor.version
            assert page.end == page.total == len(text) and page.next_offset is None
            assert len(probe.steps) == 2
        else:
            assert await db.agent_evidence.count_documents({"goal_id": goal.id}) == 1
            assert budget.capability_calls == 0
        assert not goal.prepared_text and goal.is_open
        expected_calls = 2 if partial else 1  # Existing partial-result reconsideration.
        assert len(transported) == probe.model_attempts == probe.model_http_requests == expected_calls
        assert not probe.network.blocked and not probe.blocked_effects


@pytest.mark.asyncio
async def test_real_missing_preparation_sources_replans_then_reads_and_prepares_after_reload(monkeypatch):
    db = AsyncMongoMockClient().preparation_dependency_recovery
    goal, text = await seed(db)
    failed_step = ActionStep(**prepare_step())
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active", steps=[failed_step])
    await AgentService(db).repo.save_plan(plan)
    stages = []
    current_prepare = None

    def reply(system, payload):
        if "what_happened" in payload:
            stages.append("reconsider")
            result = payload["what_happened"]["result"]
            assert result["status"] == "unavailable"
            assert result["problem"] == "preparation_sources_required"
            assert result["worth_retrying"] is False
            assert payload["plan"]["steps"][0]["status"] == "failed"
            assert payload["goal"]["current_source_context"]["sources"][0]["statement"] == text
            assert "what_happened.result.problem is preparation_sources_required" in system
            assert "missing prerequisite, not a provider outage" in system
            return {"decision": "modify", "replace_step_ids": [],
                    "revised_steps": [read_step(), prepare_step()],
                    "reasoning": "Acquisire la fonte necessaria prima di preparare il risultato."}
        if "what_has_been_found" in payload:
            stages.append("choose")
            row, = payload["what_has_been_found"]
            assert row["what_was_found"] == text and row["source_refs"] == [MEMORY]
            return {"decision": "execute", "step_id": current_prepare.id,
                    "reasoning": "La fonte è stata letta e può sostenere il confronto."}
        stages.append("audit" if "draft" in payload else "draft")
        row, = payload["evidence"]
        assert source_claim(row) == text and row["source_refs"] == [MEMORY]
        assert row["memory_reads"][0]["next_offset"] is None
        answer = {"content": RESULT, "evidence_ids": [row["id"]]}
        if "draft" in payload:
            answer.update(verified=True, claim_review=comparison_claim_review(row["id"]))
        return answer

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(db, mode="live") as probe:
        service = AgentService(db)
        run, budget = AgentRun(owner_id=OWNER, goal_id=goal.id), AgentBudget()
        assert await service._do_step(OWNER, goal, plan, failed_step, run, budget, language="it") is None
        failed_history = deepcopy(failed_step.model_dump())
        assert failed_step.status == "failed" and failed_step.attempts == 1
        assert stages == ["reconsider"]  # The rejected preparation never calls the drafter.
        observed = transported[0]["payload"]["what_happened"]["result"]
        # A real failed attempt is an observation, not a generated artifact.
        # This is the exact result received through the model's SDK boundary.
        assert observed["note"] == "Questo tentativo non ha salvato una nuova bozza verificata."
        assert observed["what_happened"] == "Non ci sono evidenze utilizzabili registrate per questo obiettivo."
        assert observed["where_this_came_from"] == "internal_observation"
        assert observed["capability"] == "document.create" and observed["source_refs"] == []
        assert await db.agent_evidence.count_documents({}) == 0
        assert not goal.prepared_text and goal.is_open
        assert [step.status for step in plan.steps] == ["failed", "pending", "pending"]

        # Only persisted plan and source state survive into this service.
        service = AgentService(db)
        goal = await service.repo.get_goal(OWNER, goal.id)
        plan = await service.repo.plan_for(OWNER, goal.id)
        decision, step = await service._next(OWNER, goal, plan, run, budget, language="it")
        assert decision == "execute" and step.capability_needed == "information.read"
        assert step.input_refs == [MEMORY] and step.parameters["memory_offset"] == 0
        await service._do_step(OWNER, goal, plan, step, run, budget, language="it")
        source, = await service.evidence.for_goal(OWNER, goal.id)
        assert source.claim == text and not goal.prepared_text

        service = AgentService(db)
        goal = await service.repo.get_goal(OWNER, goal.id)
        plan = await service.repo.plan_for(OWNER, goal.id)
        current_prepare = plan.steps[-1]
        decision, step = await service._next(OWNER, goal, plan, run, budget, language="it")
        assert decision == "execute" and step.id == current_prepare.id
        assert await service._do_step(OWNER, goal, plan, step, run, budget, language="it") is None

        saved = await service.repo.get_goal(OWNER, goal.id)
        assert saved.prepared_text == RESULT and saved.prepared_sources == [source.id]
        assert saved.is_open  # A prepared result still requires outcome verification.
        assert plan.steps[0].model_dump() == failed_history
        assert [step.status for step in plan.steps] == ["failed", "succeeded", "succeeded"]
        assert stages == ["reconsider", "choose", "draft", "audit"]
        assert [row["capability"] for row in probe.steps] == [
            "document.create", "information.read", "document.create",
        ]
        assert [row["status"] for row in probe.steps] == ["unavailable", "succeeded", "succeeded"]
        assert await db.agent_evidence.count_documents({"provenance.capability": "information.read"}) == 1
        assert await db.agent_action_attempts.count_documents({}) == 0
        assert await db.agent_needs.count_documents({}) == 0
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 4
        assert not probe.network.blocked and not probe.blocked_effects


@pytest.mark.asyncio
@pytest.mark.parametrize("stage,response", [
    ("plan", {"planning_outcome": "not_possible", "steps": [], "reasoning": "La fonte necessaria non è disponibile."}),
    ("plan", {"planning_outcome": "plan", "steps": [prepare_step()], "reasoning": "Decisione sintetica non riscritta dal codice."}),
    ("choose", {"decision": "complete", "reasoning": "Questo esito non richiede contenuto fattuale basato su una fonte."}),
    ("choose", {"decision": "wait", "wait_minutes": 30, "reasoning": "Una condizione esterna non è ancora stabilita."}),
    ("reconsider", {"decision": "continue", "reasoning": "Il resto del piano resta valido."}),
    ("reconsider", {"decision": "abandon", "reasoning": "Nessuna fonte autorizzata può sostenere il risultato."}),
])
async def test_decisions_remain_model_owned_without_inserting_reads_or_retry(monkeypatch, stage, response):
    ask = AsyncMock(return_value=response)
    monkeypatch.setattr(reasoning, "_ask_model", ask)
    if stage == "plan":
        result = await reasoning.make_plan({}, capabilities=[], context={})
    elif stage == "choose":
        result = await reasoning.choose_next_action({}, plan={}, candidates=[], evidence=[], capabilities=[])
    else:
        result = await reasoning.reconsider({}, plan={}, capabilities=[], what_happened={
            "result": {"status": "unavailable", "problem": "preparation_sources_required"},
        })
    assert result is response
    assert ask.await_count == 1
