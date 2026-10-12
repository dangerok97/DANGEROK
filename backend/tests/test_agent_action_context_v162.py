"""The next-action context must not turn a complete source read into a prefix.

The home_write_retry e4b68b diagnostic recorded a complete 0–565 memory read,
then a chooser asking for the terms because excerpt_truncated was true. The
goal and shortened plan descriptions below reconstruct that boundary; they
are not a historical HTTP capture. Real reader/store/service/SDK code uses
owned in-memory records and fake HTTP, never a live model or external effect.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import reasoning
from agent.models import ActionPlan, ActionStep, AgentBudget, AgentRun
from agent.service import AgentService, _user_clock_context
from agent.evidence import for_verification
from scripts import autonomy_completion_eval_v162 as gate
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401
from test_agent_preparation_dependency_v162 import fake_gemini


OWNER = gate.OWNER
OBJECTIVE = (
    "preparare una tabella comparativa dei costi e vincoli delle due formule di archivio digitale "
    "per 12 mesi, basata sui dati forniti dall'utente e chiarendo le condizioni non esplicitate."
)
OUTCOME = (
    "una tabella comparativa chiara e verificabile dei costi e vincoli delle due opzioni di archivio "
    "digitale, con evidenziazione delle differenze chiave (es. flessibilità, rimborso, durata vincolante) "
    "e una dichiarazione esplicita dei limiti di autorità (nessun pagamento o modifica contrattuale)."
)
CRITERIA = [
    "la tabella include costi totali (180€ vs 120€), vincoli contrattuali (assenza di rimborso per l'opzione annuale), durata e condizioni di disdetta",
    "è esplicitato che la sintesi si basa sui dati forniti dall'utente e non confermati dal fornitore",
    "è inclusa una nota che ribadisce l'assenza di autorità per pagamenti o modifiche contrattuali",
]
PLAN_SUMMARY = (
    "Preparare una tabella comparativa dei costi e vincoli delle due formule di archivio digitale "
    "per 12 mesi, basata sui dati forniti dall'utente, evidenziando le differenze chiave e dichiarando "
    "esplicitamente i limiti di autorità."
)
PLAN_STEPS = [
    {
        "step_type": "inspect", "capability_needed": "information.read",
        "intent": "Recuperare e confermare i dati chiave estratti dalla memoria per la preparazione della tabella comparativa.",
        "expected_result": "Conferma che i dati estratti sono completi e coerenti con la richiesta: due formule (mensile e annuale), costi totali, vincoli contrattuali, durata e condizioni",
    },
    {
        "step_type": "prepare", "capability_needed": "document.create",
        "intent": "Preparare una tabella comparativa chiara dei costi e vincoli delle due formule di archivio digitale per 12 mesi, evidenziando le differenze chiave e dichiarando",
        "expected_result": "Un documento strutturato in formato tabella che includa: costi totali (180€ vs 120€), vincoli contrattuali (assenza di rimborso per l'opzione annuale), durata e",
    },
    {
        "step_type": "verify", "capability_needed": "information.read",
        "intent": "Verificare che la tabella preparata includa tutti i vincoli rilevanti e che la dichiarazione di limiti di autorità sia chiara e non ambigua.",
        "expected_result": "Conferma che la tabella sia completa e che la dichiarazione di limiti di autorità sia chiara, soddisfacendo tutti i criteri di successo.",
    },
]


async def reconstruct(*, partial=False):
    db = AsyncMongoMockClient().action_context_v162
    with gate.isolated_engine(db):
        await gate.seed_case(db, "home_write_retry")
        goal_id = await gate.admit(db, "home_write_retry")
        service = AgentService(db)
        goal = await service.repo.get_goal(OWNER, goal_id)
        goal.objective, goal.desired_outcome = OBJECTIVE, OUTCOME
        goal.success_criteria = list(CRITERIA)
        await service.repo.save_goal(goal)
        text = gate.FIXTURE_NOTE
        if partial:
            text += " Condizione nel seguito: la disponibilità di spazio aggiuntivo resta da verificare prima di decidere se sia necessario."
            assert len(text) > 600
            await db.memories.update_one({"user_id": OWNER, "id": goal.source_refs[0]}, {"$set": {"statement": text}})
        steps = [service._read_step(dict(row, input_refs=goal.source_refs), index)
                 for index, row in enumerate(PLAN_STEPS)]
        read = await service.executor.run(OWNER, goal, steps[0], may_touch_the_world=False)
        assert read.status == ("partial" if partial else "succeeded")
        steps[0].status, steps[0].note = "succeeded", read.observation[:200]
        source, = await service.evidence.for_goal(OWNER, goal.id)
        if partial:
            cursor = source.provenance.memory_reads[0]
            steps[2] = ActionStep(
                ordinal=2, step_type="inspect", capability_needed="information.read",
                intent="Leggere il seguito della nota corrente prima di preparare il confronto.",
                expected_result="Le condizioni ancora da leggere, con i limiti della fonte invariati.",
                input_refs=goal.source_refs,
                parameters={"memory_offset": cursor.next_offset, "memory_version": cursor.version},
            )
        plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, steps=steps, plan_summary=PLAN_SUMMARY)
        await service.repo.save_plan(plan)
        payload = {
            "goal": await service._reasoning_goal(OWNER, goal),
            "plan": plan.for_ai(),
            "local_clock": await _user_clock_context(db, OWNER),
            "still_to_do": [step.for_ai() for step in steps if step.status == "pending"],
            "what_has_been_found": for_verification(await service.evidence.for_goal(OWNER, goal.id)),
            "what_ora_can_do": await service.capabilities.available(OWNER),
        }
    return SimpleNamespace(db=db, goal=goal, plan=plan, source=source, payload=payload, text=text)


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True], ids=["complete_565", "real_partial_with_cursor"])
async def test_next_action_http_preserves_source_coverage_and_candidate_effects(monkeypatch, partial):
    h = await reconstruct(partial=partial)
    expected = deepcopy(h.payload)
    assert len(json.dumps(expected, ensure_ascii=False, separators=(",", ":"))) > 9000
    chosen = h.plan.steps[2] if partial else h.plan.steps[1]
    response = {"decision": "execute", "step_id": chosen.id, "reasoning": "Scelta sintetica del passo già presente."}
    transported = fake_gemini(monkeypatch, lambda _system, _payload: response)
    with gate.isolated_engine(h.db, mode="live") as probe:
        result = await AgentService(h.db)._next(
            OWNER, h.goal, h.plan, AgentRun(owner_id=OWNER, goal_id=h.goal.id), AgentBudget(), language="it",
        )
        assert result[0] == "execute" and result[1].id == chosen.id
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert not probe.network.blocked and not probe.blocked_effects
    sent = transported[0]["payload"]
    source, = sent["what_has_been_found"]
    assert source == expected["what_has_been_found"][0]
    assert source["what_was_found"] == h.text[:600]
    cursor, = source["memory_reads"]
    assert cursor == h.source.provenance.for_ai()["memory_reads"][0]
    assert cursor["next_offset"] == (600 if partial else None)
    assert sent["goal"] == expected["goal"]
    assert sent["still_to_do"] == expected["still_to_do"]
    assert sent["what_ora_can_do"] == expected["what_ora_can_do"]
    assert sent["plan"]["steps"][0] == expected["plan"]["steps"][0]
    assert "the candidate with that same id in still_to_do" in transported[0]["system"]
    for step in sent["plan"]["steps"][1:]:
        candidate = next(row for row in sent["still_to_do"] if row["id"] == step["id"])
        assert step["details_in"] == "still_to_do" and step["status"] == candidate["status"]
        assert candidate in expected["plan"]["steps"]
    assert not h.goal.requires_user_input and not h.goal.prepared_text
    assert await h.db.agent_evidence.count_documents({"owner_id": OWNER, "goal_id": h.goal.id}) == 1
    assert await h.db.agent_action_attempts.count_documents({}) == 0


async def choose(payload):
    return await reasoning.choose_next_action(
        payload["goal"], plan=payload["plan"], candidates=payload["still_to_do"],
        evidence=payload["what_has_been_found"], capabilities=payload["what_ora_can_do"],
        clock_context=payload["local_clock"], language="it",
    )


@pytest.mark.asyncio
async def test_context_reduction_does_not_mutate_inputs_or_replace_an_ask_decision(monkeypatch):
    h = await reconstruct()
    original = deepcopy(h.payload)
    # A synthetic judgement tests passthrough, not whether this question is
    # useful. The serializer must never turn an ask into an automatic action.
    answer = {"decision": "ask", "step_id": "", "ask_kind": "knowledge",
              "asks": "Quale requisito personale conta di più?", "reasoning": "Giudizio sintetico."}
    transported = fake_gemini(monkeypatch, lambda _system, _payload: answer)
    with gate.isolated_engine(h.db, mode="live") as probe:
        result = await choose(h.payload)
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert not probe.network.blocked and not probe.blocked_effects
    assert result == answer
    assert h.payload == original
    assert transported[0]["payload"]["what_has_been_found"] == original["what_has_been_found"]


@pytest.mark.asyncio
async def test_same_id_with_different_step_effects_or_parameters_is_not_a_duplicate(monkeypatch):
    from test_completed_result_context_v162 import restore_lossless_choice

    h = await reconstruct()
    # An ID alone cannot establish equivalence to a current candidate. Keep
    # both declarations intact when lossless tables let them fit together.
    h.payload["still_to_do"][0]["effect_target"] = "a-different-target"
    h.payload["still_to_do"][1]["memory_offset"] = 600
    h.payload["still_to_do"][1]["memory_version"] = "a-different-version"
    original = deepcopy(h.payload)
    answer = {"decision": "execute", "step_id": h.plan.steps[1].id}
    transported = fake_gemini(monkeypatch, lambda _system, _payload: answer)
    with gate.isolated_engine(h.db, mode="live") as probe:
        result = await choose(h.payload)
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert not probe.network.blocked and not probe.blocked_effects
    assert result == answer
    restored = restore_lossless_choice(transported[0]["payload"])
    assert json.dumps(restored, sort_keys=True) == json.dumps(original, sort_keys=True)
    for candidate in restored["still_to_do"]:
        step = next(row for row in restored["plan"]["steps"] if row["id"] == candidate["id"])
        assert json.dumps(step, sort_keys=True) != json.dumps(candidate, sort_keys=True)
    assert restored["still_to_do"][0]["effect_target"] == "a-different-target"
    assert restored["still_to_do"][1]["memory_offset"] == 600
    assert restored["still_to_do"][1]["memory_version"] == "a-different-version"
    assert json.dumps(h.payload, sort_keys=True) == json.dumps(original, sort_keys=True)


@pytest.mark.asyncio
async def test_material_overflow_is_unavailable_without_dropping_sources_or_criteria(monkeypatch, caplog):
    h = await reconstruct()
    for index in range(8):
        row = deepcopy(h.payload["what_has_been_found"][0])
        row["evidence_id"] = f"evd_material_source_{index}"
        row["what_was_found"] = f"Condizione distinta {index}: " + "dato materiale da conservare; " * 18
        h.payload["what_has_been_found"].append(row)
    original = deepcopy(h.payload)
    model = AsyncMock(return_value={"decision": "ask", "asks": "Dati già letti?"})
    monkeypatch.setattr(reasoning, "_ask_model", model)
    with caplog.at_level("INFO", logger="agent.reasoning"):
        result = await choose(h.payload)
    assert result is None and model.await_count == 0
    assert "material_context_exceeds_budget" in caplog.text
    assert h.payload == original


@pytest.mark.asyncio
async def test_weather_choice_keeps_empirical_basis_latest_batch_and_clock_after_deduplication(monkeypatch):
    from test_situation_useful_outcome_v160 import setup as situation_fixture, OWNER as situation_owner

    db, service, state, goal, _, _, baseline, live = await situation_fixture(monkeypatch)
    now = datetime.now(timezone.utc)
    rows = [baseline.for_ai()]
    rows[0]["what_was_found"] = "Base empirica sintetica con qualifiche da conservare. " * 10
    for index in range(3):
        row = live.for_ai()
        row.update(evidence_id=f"evd_latest_weather_{index}",
                   what_was_found=f"Condizione sintetica {index}. " * 14, observed_at=now.isoformat())
        rows.append(row)
    plan = ActionPlan(owner_id=situation_owner, goal_id=goal.id, status="active", steps=[
        ActionStep(ordinal=index, intent=("Controllo sintetico qualificato " * 8)[:240],
                   step_type="inspect", capability_needed="weather.read",
                   expected_result=("Risultato con limiti della fonte " * 9)[:290],
                   status="succeeded" if index == 0 else "pending") for index in range(3)
    ])
    payload = {
        "goal": await service._reasoning_goal(situation_owner, goal), "plan": plan.for_ai(),
        "local_clock": {"now": now.isoformat(), "timezone": "Europe/Rome", "local_date": now.date().isoformat()},
        "still_to_do": [step.for_ai() for step in plan.steps[1:]],
        "what_has_been_found": rows,
        "what_ora_can_do": [{"capability": "weather.read", "status": "available_real", "can_be_used_now": True}],
    }
    original = deepcopy(payload)
    assert len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) > 9000
    answer = {"decision": "wait", "wait_minutes": 25, "reasoning": "Checkpoint sintetico, non prova dell'esito fisico."}
    transported = fake_gemini(monkeypatch, lambda _system, _payload: answer)
    with gate.isolated_engine(db, mode="live") as probe:
        result = await choose(payload)
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert not probe.network.blocked and not probe.blocked_effects
    sent = transported[0]["payload"]
    assert result == answer and payload == original
    assert sent["what_has_been_found"] == original["what_has_been_found"]
    assert {row["evidence_id"] for row in sent["what_has_been_found"]} == {
        baseline.id, "evd_latest_weather_0", "evd_latest_weather_1", "evd_latest_weather_2",
    }
    assert sent["goal"] == original["goal"]
    assert sent["goal"]["source_context"][0]["started_at"] == state.started_at
    assert sent["local_clock"] == original["local_clock"]
    assert sent["still_to_do"] == original["still_to_do"]
