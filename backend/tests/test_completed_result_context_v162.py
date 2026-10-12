"""A saved result and its real sources survive the next worker's context.

The 790/2813-character texts are the original synthetic e3a diagnostic outputs.
This reconstructs reader, preparation, persistence and SDK boundaries; it is
not a historical HTTP capture or a claim that the recorded drafts were sound.
Only fake HTTP replies supply judgements, and no external effect is allowed.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent import reasoning
from agent.evidence import for_verification
from agent.models import AgentBudget, AgentRun
from agent.service import AgentService, _user_clock_context
from scripts import autonomy_completion_eval_v162 as gate
from test_agent_action_context_v162 import reconstruct
from test_agent_preparation_dependency_v162 import fake_gemini
from test_pending_outcome_contract_v162 import synthetic_transport_only  # noqa: F401


OWNER = gate.OWNER
REPORT = Path(__file__).resolve().parents[2] / "docs/evidence/autonomy_v162_live_2026-10-12_e3a843c.json"


def recorded_text(scenario):
    report = json.loads(REPORT.read_text())
    case = next(row for row in report["cases"] if row["scenario"] == scenario)
    text = case["failure_state"]["goals"][0]["prepared_text"]
    assert len(text) == {"home_write_retry": 790, "completed_result": 2813}[scenario]
    return text


def expand_records(value):
    if isinstance(value, list):
        return value
    rows = []
    for index, values in enumerate(value["rows"]):
        absent = value.get("missing", {}).get(str(index), [])
        row = dict(value["common"])
        row.update({key: item for column, (key, item) in enumerate(zip(value["columns"], values))
                    if column not in absent})
        rows.append(row)
    return rows


async def prepared_case(scenario="completed_result", *, partial=False):
    h = await reconstruct(partial=partial)
    draft = recorded_text(scenario)
    with gate.isolated_engine(h.db):
        service = AgentService(h.db)
        prepare = h.plan.steps[1]
        replies = AsyncMock(side_effect=[
            {"content": draft, "evidence_ids": [h.source.id]},
            {"verified": True, "content": draft, "evidence_ids": [h.source.id]},
        ])
        with patch.object(reasoning, "_ask_model", replies):
            made = await service.executor.run(OWNER, h.goal, prepare, may_touch_the_world=False)
        assert made.status == "succeeded" and replies.await_count == 2
        prepare.status, prepare.note = "succeeded", made.observation
        await service.repo.save_plan(h.plan)
        # No in-process result or plan is passed on: use a new worker service.
        service = AgentService(h.db)
        goal = await service.repo.get_goal(OWNER, h.goal.id)
        plan = await service.repo.plan_for(OWNER, h.goal.id)
        assert goal.prepared_text == draft and goal.prepared_sources == [h.source.id]
        rows = for_verification(await service.evidence.for_goal(OWNER, goal.id),
                                required_refs=goal.prepared_sources)
        goal_context = await service._reasoning_goal(OWNER, goal)
        clock = await _user_clock_context(h.db, OWNER)
        action = {
            "goal": goal_context, "plan": plan.for_ai(), "local_clock": clock,
            "still_to_do": [step.for_ai() for step in plan.steps if step.status == "pending"],
            "what_has_been_found": rows, "what_ora_can_do": await service.capabilities.available(OWNER),
            "prepared_result": goal.prepared_text, "prepared_source_refs": list(goal.prepared_sources),
        }
        verification = {"goal": goal_context, "what_was_done": {
            "what_was_found": rows, "steps": [step.for_ai() for step in plan.steps],
            "what_was_prepared": [], "prepared_result": goal.prepared_text,
            "prepared_source_refs": list(goal.prepared_sources), "local_clock": clock,
            "what_the_services_said": [],
        }}
    return SimpleNamespace(db=h.db, service=service, goal=goal, plan=plan, source=h.source,
                           draft=draft, action=action, verification=verification)


async def judge(payload, mode):
    if mode == "verification":
        return await reasoning.verify_goal(payload["goal"], evidence=payload["what_was_done"])
    return await reasoning.choose_next_action(
        payload["goal"], plan=payload["plan"], candidates=payload["still_to_do"],
        evidence=payload["what_has_been_found"], capabilities=payload["what_ora_can_do"],
        clock_context=payload["local_clock"], prepared_result=payload["prepared_result"],
        prepared_source_refs=payload["prepared_source_refs"],
    )


def assert_material_intact(payload, original, *, mode):
    action = mode == "action"
    actual = payload if action else payload["what_was_done"]
    expected = original if action else original["what_was_done"]
    rows_key = "what_has_been_found" if action else "what_was_found"
    assert actual["prepared_result"] == expected["prepared_result"]
    assert actual["prepared_source_refs"] == expected["prepared_source_refs"]
    original_sources = [row for row in expected[rows_key] if not row.get("generated_artifact")]
    actual_sources = [row for row in actual[rows_key] if not row.get("generated_artifact")]
    assert actual_sources == original_sources
    assert actual["local_clock"] == expected["local_clock"]
    for key in ("objective", "desired_outcome", "success_criteria", "stop_conditions",
                "source_refs", "user_clarifications_not_authority"):
        assert payload["goal"][key] == original["goal"][key]
    # Sharing text may not merge its preview authority with execution proof.
    context = deepcopy(payload["goal"]["current_source_context"])
    for preview in context["sources"]:
        if "statement_in_evidence" in preview:
            evidence_id = preview.pop("statement_in_evidence")
            evidence = next(row for row in actual_sources if row["evidence_id"] == evidence_id)
            assert preview["ref"] in evidence["source_refs"]
            preview["statement"] = evidence["what_was_found"]
    assert context == original["goal"]["current_source_context"]
    if action:
        steps = expand_records(payload["plan"]["steps"])
        candidates = [next(step for step in steps if step["id"] == row["id"])
                      if row.get("details_in") == "plan.steps" else row
                      for row in payload["still_to_do"]]
        assert candidates == original["still_to_do"]
        assert expand_records(payload["what_ora_can_do"]) == original["what_ora_can_do"]
        steps = [next(row for row in candidates if row["id"] == step["id"])
                 if step.get("details_in") == "still_to_do" else step for step in steps]
        original_steps = original["plan"]["steps"]
    else:
        steps = expand_records(actual["steps"])
        original_steps = expected["steps"]
    assert len(steps) == len(original_steps)
    for step, prior in zip(steps, original_steps):
        assert step["note"] == prior["note"]
        for key, value in prior.items():
            if key in ("intent", "expected_result") and prior["status"] in ("succeeded", "skipped"):
                continue
            assert key in step and step[key] == value


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["home_write_retry", "completed_result"])
@pytest.mark.parametrize("mode", ["action", "verification"])
async def test_saved_e3a_result_reaches_real_sdk_after_reload(monkeypatch, scenario, mode):
    h = await prepared_case(scenario)
    original = deepcopy(getattr(h, mode))
    assert len(json.dumps(original, ensure_ascii=False, separators=(",", ":"))) > 9000
    step = h.plan.steps[2]
    answer = ({"decision": "execute", "step_id": step.id, "reasoning": "Scelta sintetica."}
              if mode == "action" else
              {"outcome": "uncertain", "what_is_missing": "Giudizio sintetico lasciato invariato."})

    def reply(system, payload):
        assert_material_intact(payload, original, mode=mode)
        assert "prepared_result" in system
        return answer

    transported = fake_gemini(monkeypatch, reply)
    before_goal = await h.db.agent_goals.find_one({"owner_id": OWNER, "id": h.goal.id})
    before_evidence = await h.db.agent_evidence.count_documents({"owner_id": OWNER, "goal_id": h.goal.id})
    with gate.isolated_engine(h.db, mode="live") as probe:
        if mode == "action":
            decision, chosen = await h.service._next(OWNER, h.goal, h.plan,
                AgentRun(owner_id=OWNER, goal_id=h.goal.id), AgentBudget(), language="it")
            assert decision == "execute" and chosen.id == step.id
        else:
            result = await reasoning.verify_goal(h.verification["goal"], evidence=h.verification["what_was_done"])
            assert result == answer
        assert len(transported) == probe.model_attempts == probe.model_http_requests == 1
        assert not probe.network.blocked and not probe.blocked_effects
    assert getattr(h, mode) == original
    assert await h.db.agent_goals.find_one({"owner_id": OWNER, "id": h.goal.id}) == before_goal
    assert await h.db.agent_evidence.count_documents({"owner_id": OWNER, "goal_id": h.goal.id}) == before_evidence


@pytest.mark.asyncio
async def test_completed_notes_and_candidate_cursor_effects_remain_reconstructible(monkeypatch):
    h = await prepared_case()
    payload = h.action
    payload["plan"]["steps"][0]["note"] = "Letta solo la fonte interna: nessuna conferma del fornitore."
    payload["plan"]["steps"][1]["note"] = "La bozza è salvata; non è stata inviata."
    for step in (payload["plan"]["steps"][2], payload["still_to_do"][0]):
        step["memory_offset"], step["memory_version"] = 600, "v2"
        step["effect_target"] = "target-1"
        step["what_kind_of_change"] = "modify"
    original = deepcopy(payload)
    answer = {"decision": "ask", "ask_kind": "knowledge", "asks": "Quale requisito conta?"}

    def reply(system, sent):
        assert_material_intact(sent, original, mode="action")
        assert isinstance(sent["plan"]["steps"], dict)
        assert "A short row has absent trailing columns" in system
        assert "Null remains null" in system
        return answer

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(h.db, mode="live"):
        assert await judge(payload, "action") == answer
    assert len(transported) == 1 and payload == original
    assert await h.db.agent_action_attempts.count_documents({}) == 0


def test_step_table_roundtrip_distinguishes_absence_null_boolean_and_number():
    common = {"input_refs": ["memory:synthetic"], "note": "Limite operativo da conservare. " * 5,
              "memory_version": "versione" * 10, "effect_target": "destinazione" * 10}
    rows = [
        dict(common, id="a", status="succeeded", memory_offset=None, external_effect=False, marker=True),
        dict(common, id="b", status="skipped", external_effect=False, marker=1),
        dict(common, id="c", status="pending", memory_offset=600, external_effect=None),
    ]
    original = deepcopy(rows)
    table = reasoning._record_table(rows)
    assert isinstance(table, dict) and table.get("missing")
    assert json.dumps(expand_records(table), sort_keys=True) == json.dumps(original, sort_keys=True)
    assert "marker" not in table["common"]
    assert rows == original


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["action", "verification"])
async def test_prepared_result_does_not_upgrade_a_real_partial_read(monkeypatch, mode):
    h = await prepared_case("home_write_retry", partial=True)
    payload = getattr(h, mode)
    original = deepcopy(payload)
    answer = ({"decision": "wait", "wait_minutes": 25} if mode == "action" else
              {"outcome": "uncertain", "what_is_missing": "Giudizio sintetico invariato."})

    def reply(_system, sent):
        assert_material_intact(sent, original, mode=mode)
        holder = sent if mode == "action" else sent["what_was_done"]
        rows = holder["what_has_been_found" if mode == "action" else "what_was_found"]
        source = next(row for row in rows if row["evidence_id"] == h.source.id)
        assert source["memory_reads"][0]["next_offset"] == 600
        assert source["memory_reads"][0]["version"] == h.source.provenance.memory_reads[0].version
        return answer

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(h.db, mode="live"):
        assert await judge(payload, mode) == answer
    assert len(transported) == 1 and payload == original


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["action", "verification"])
async def test_distinct_material_overflow_stays_unavailable_before_model(monkeypatch, caplog, mode):
    h = await prepared_case("home_write_retry")
    payload = getattr(h, mode)
    holder = payload if mode == "action" else payload["what_was_done"]
    rows = holder["what_has_been_found" if mode == "action" else "what_was_found"]
    for index in range(10):
        row = deepcopy(rows[0])
        row.update(evidence_id=f"evd_distinct_{index}",
                   what_was_found=f"Condizione distinta {index}: " + "Qualificazione materiale ulteriore. " * 18)
        rows.append(row)
    original = deepcopy(payload)
    model = AsyncMock(return_value={"decision": "ask", "outcome": "achieved"})
    monkeypatch.setattr(reasoning, "_ask_model", model)
    with caplog.at_level("INFO", logger="agent.reasoning"):
        assert await judge(payload, mode) is None
    assert model.await_count == 0 and payload == original
    assert "material_context_exceeds_budget" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["action", "verification"])
async def test_missing_saved_source_blocks_both_judgements_without_borrowing_generated_rows(monkeypatch, caplog, mode):
    h = await prepared_case("home_write_retry")
    payload = getattr(h, mode)
    holder = payload if mode == "action" else payload["what_was_done"]
    key = "what_has_been_found" if mode == "action" else "what_was_found"
    holder[key] = [row for row in holder[key] if row["evidence_id"] != h.source.id]
    assert holder[key] and all(row.get("generated_artifact") for row in holder[key])
    original = deepcopy(payload)
    model = AsyncMock()
    monkeypatch.setattr(reasoning, "_ask_model", model)
    with caplog.at_level("INFO", logger="agent.reasoning"):
        assert await judge(payload, mode) is None
    assert model.await_count == 0 and payload == original
    assert "prepared_source_missing" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["action", "verification"])
async def test_same_source_ref_does_not_merge_contradictory_text_or_different_metadata(monkeypatch, mode):
    h = await prepared_case("home_write_retry")
    payload = getattr(h, mode)
    holder = payload if mode == "action" else payload["what_was_done"]
    rows = holder["what_has_been_found" if mode == "action" else "what_was_found"]
    current = next(row for row in rows if row["evidence_id"] == h.source.id)
    contradictory = deepcopy(current)
    contradictory.update(evidence_id="evd_contradictory_source", what_was_found="Una lettura precedente indicava un importo diverso.")
    contradictory["memory_reads"][0]["version"] = "previous-version"
    rows.append(contradictory)
    original = deepcopy(payload)
    answer = {"decision": "replan"} if mode == "action" else {"outcome": "uncertain"}

    def reply(_system, sent):
        assert_material_intact(sent, original, mode=mode)
        return answer

    transported = fake_gemini(monkeypatch, reply)
    with gate.isolated_engine(h.db, mode="live"):
        assert await judge(payload, mode) == answer
    assert len(transported) == 1 and payload == original
