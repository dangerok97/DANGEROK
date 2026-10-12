"""Acceptance for the isolated, connected source-to-Home evaluator.

These are scripted decisions over real internal services. Passing them never
attests a real model, third-party facts, a process restart or device receipt.
"""
import json

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from scripts import autonomy_completion_eval_v162 as gate


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", gate.SCENARIOS)
async def test_connected_autonomy_contract(scenario):
    report = await gate.run_case(scenario)
    assert report["passed"] is True
    assert report["fixture_revision"] == "personal_outcome_v1"
    assert report["real_model_executed"] is False
    assert report["model_attempts"] == report["model_http_requests"] == 0
    assert report["live_provider_reads"] == 0
    assert report["external_effects"] == 0
    assert report["storage"] == "in_memory"
    assert report["process_restart_tested"] is False
    decisions = report["structured_decisions"]
    assert report["structured_decisions_omitted"] == 0
    assert any(row["stage"] == "decide_goal" for row in decisions)
    assert all(row["model_attempts_before"] == row["model_attempts_after"] == 0 for row in decisions)
    if scenario in gate.NO_GOAL_SCENARIOS:
        assert report["worker_ticks"] == []
        assert report["executed_capabilities"] == []
        assert report["result"]["state"] == "no_goal"
    elif scenario not in ("source_revoked", "memory_revoked"):
        assert len(report["worker_ticks"]) >= 2
        assert report["result"]["home_delivered"]
        assert report["result"]["replay_idempotent"]
        assert report["result"]["owner_isolation"]
        assert report["result"]["semantic_review"]["human_review_still_required"]


@pytest.mark.asyncio
async def test_canonical_governed_memory_reaches_the_real_worker_reader():
    db = AsyncMongoMockClient().v162_canonical
    with gate.isolated_engine(db) as probe:
        await gate.seed_case(db, "completed_result")
        memory = await db.memories.find_one({"user_id": gate.OWNER})
        assert memory["statement"] == gate.FIXTURE_NOTE
        assert memory["content"] == gate.FIXTURE_NOTE
        assert gate.FIXTURE_NOTE.endswith(gate.baseline.FACT)
        assert "summary" not in memory  # legacy fixtures must not hide drift
        goal_id = await gate.admit(db, "completed_result")
        await gate.first_read(db, goal_id, probe)
        evidence = await db.agent_evidence.find_one({
            "owner_id": gate.OWNER, "goal_id": goal_id,
            "provenance.capability": "information.read",
        })
        assert evidence and evidence["claim"] == gate.FIXTURE_NOTE
        assert memory["id"] in evidence["provenance"]["source_refs"]
        assert evidence["provenance"]["source_versions"].get(memory["id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["completed_result", "source_change_crash", "memory_corrected"])
async def test_fixture_does_not_invent_renewal_urgency_outside_the_canonical_note(scenario):
    db = AsyncMongoMockClient().v162_no_invented_deadline
    with gate.isolated_engine(db, scenario=scenario) as probe:
        await gate.seed_case(db, scenario)
        if scenario == "source_change_crash":
            await gate.discover_after_crash(db, probe)
        goal_id = await gate.admit(db, scenario)
        memory = await db.memories.find_one({"user_id": gate.OWNER})
        source = await db.opportunities.find_one({"owner_id": gate.OWNER})
        goal = await db.agent_goals.find_one({"owner_id": gate.OWNER, "id": goal_id})
        assert memory["statement"] == memory["content"] == gate.FIXTURE_NOTE
        assert all("rinnovo" not in text.lower() for text in (
            source["semantic_summary"], source["why_now"], goal["why_now"],
        ))
        assert "non è documentata una scadenza" in source["why_now"]
        if scenario == "memory_corrected":
            assert "La nota viene corretta o ritirata" not in goal["stop_conditions"]
            assert all("corretta" not in condition.lower() for condition in goal["stop_conditions"])
            assert any("ritirata" in condition for condition in goal["stop_conditions"])


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["completed_result", "already_resolved"])
async def test_personal_outcome_state_is_in_the_owned_admission_source(monkeypatch, scenario):
    inputs = []
    original = gate._decision_input

    def observe(stage, value, kwargs):
        if stage == "decide_goal":
            inputs.append(value)
        return original(stage, value, kwargs)

    monkeypatch.setattr(gate, "_decision_input", observe)
    db = AsyncMongoMockClient().v162_personal_outcome_source
    with gate.isolated_engine(db, scenario=scenario) as probe:
        await gate.seed_case(db, scenario)
        goal_id = await gate.admit(db, scenario)
        expected = gate.RESOLVED_FIXTURE_NOTE if scenario == "already_resolved" else gate.FIXTURE_NOTE
        memory = await db.memories.find_one({"user_id": gate.OWNER})
        assert memory["statement"] == memory["content"] == expected
        assert expected.endswith(gate.baseline.FACT) and len(expected) <= 600
        assert len(inputs) == 1 and len(inputs[0]["source_context"]) == 1
        preview = inputs[0]["source_context"][0]
        assert preview["ref"] == memory["id"] and preview["statement"] == expected
        assert not preview["excerpt_truncated"]
        assert probe.model_attempts == 0  # Scripted oracle, observed real admission payload.
        if scenario == "already_resolved":
            assert goal_id is None
            assert "già ricevuto" in preview["statement"] and "ho scelto il mensile" in preview["statement"]
            assert await db.agent_goals.count_documents({"owner_id": gate.OWNER}) == 0
            assert await db.ambient_wakes.count_documents({"owner_id": gate.OWNER}) == 0
        else:
            assert goal_id and "mi manca il confronto scritto" in preview["statement"]


@pytest.mark.asyncio
async def test_correction_preserves_the_unresolved_personal_outcome_and_changes_only_the_price():
    db = AsyncMongoMockClient().v162_personal_outcome_correction
    with gate.isolated_engine(db, scenario="memory_corrected") as probe:
        await gate.seed_case(db, "memory_corrected")
        goal_id = await gate.admit(db, "memory_corrected")
        await gate.first_read(db, goal_id, probe)
        changed = await gate.change_memory(db, goal_id, correction=True)
        memory = await db.memories.find_one({"user_id": gate.OWNER, "id": changed["current"]})
        assert memory["statement"] == memory["content"] == gate.FIXTURE_NOTE.replace("120 euro", "150 euro")
        assert memory["statement"].startswith(gate.FIXTURE_CONTEXT)
        assert "mi manca il confronto scritto" in memory["statement"]


@pytest.mark.asyncio
async def test_harness_cannot_repair_a_missing_durable_continuation():
    db = AsyncMongoMockClient().v162_lost_checkpoint
    with gate.isolated_engine(db) as probe:
        await gate.seed_case(db, "completed_result")
        goal_id = await gate.admit(db, "completed_result")
        await gate.first_read(db, goal_id, probe)
        await db.agent_goals.update_one({"id": goal_id}, {"$set": {"next_run_at": None}})
        with pytest.raises(gate.EvaluationFailure, match="DURABLE_CONTINUATION_MISSING"):
            await gate.fire_due(db, goal_id, probe)


@pytest.mark.asyncio
async def test_missing_home_handoff_does_not_count_as_completed_acceptance(monkeypatch):
    from agent.visibility import VisibilityService

    async def lose_handoff(*args, **kwargs):
        return None

    monkeypatch.setattr(VisibilityService, "show", lose_handoff)
    with pytest.raises(gate.EvaluationFailure, match="HOME_OUTBOX_NOT_DELIVERED"):
        await gate.run_case("completed_result")


@pytest.mark.asyncio
async def test_independent_result_gate_rejects_empty_substance_even_if_model_approves(monkeypatch):
    monkeypatch.setattr(gate.baseline, "DRAFT", "Ho preparato il confronto richiesto.")
    with pytest.raises(gate.EvaluationFailure, match="SEMANTIC_RESULT_REJECTED"):
        await gate.run_case("completed_result")


@pytest.mark.asyncio
@pytest.mark.parametrize("home_failed", [False, True])
async def test_memory_forgotten_after_completion_invalidates_visible_or_pending_home(home_failed):
    from delivery.service import DeliveryService

    db = AsyncMongoMockClient().v162_completed_memory_withdrawal
    scenario = "home_write_retry" if home_failed else "completed_result"
    with gate.isolated_engine(db, scenario=scenario) as probe:
        await gate.seed_case(db, scenario)
        goal_id = await gate.admit(db, scenario)
        await gate.first_read(db, goal_id, probe)
        await gate.fire_due(db, goal_id, probe)
        if home_failed:
            assert await db.agent_updates.count_documents({"home_pending": True}) == 1
        else:
            assert (await gate.verify_result(db, goal_id, probe))["home_delivered"]
        await gate.change_memory(db, goal_id)
        await gate.recover_home(db)
        assert await DeliveryService(db).ambient_line(gate.OWNER) is None
        assert await db.agent_updates.count_documents({"home_pending": True}) == 0
        if home_failed:
            assert await db.ambient_activity.count_documents({
                "cognitive_provenance.agent": "visibility", "cognitive_provenance.goal": goal_id,
            }) == 0


def test_model_cannot_claim_provider_verification_from_an_internal_note():
    invented = gate.baseline.DRAFT.replace("non verificata", "verificata").replace(
        "sono da verificare", "ho verificato")
    result = gate.review_comparison(invented)
    assert not result["passed"]
    assert "SOURCE_VERIFICATION_LIMIT_MISSING" in result["reasons"]


@pytest.mark.parametrize("qualification,accepted", [
    ("Le informazioni non sono confermate dal fornitore.", True),
    ("I dati non sono ancora stati verificati.", True),
    ("La nota non costituisce una verifica indipendente.", True),
    ("I dati non costituiscono una conferma diretta o verifica indipendente da parte del fornitore.", True),
    ("Le cifre non rappresentano una conferma indipendente del fornitore.", True),
    ("Le informazioni sono confermate dal fornitore.", False),
    ("La nota costituisce una conferma diretta e una verifica indipendente.", False),
    ("Non è necessario verificare: il fornitore ha confermato i dati.", False),
    ("Non ho modificato il contratto; ho verificato i dati con il fornitore.", False),
    ("Le cifre non rappresentano un problema: sono confermate dal fornitore.", False),
])
def test_source_limit_check_preserves_negation_in_equivalent_wording(qualification, accepted):
    # The real c38b draft used "non costituiscono una conferma diretta ...".
    # Preserve the criterion while accepting the same explicit qualification;
    # an affirmative verification claim or an unrelated negation must fail.
    text = gate.baseline.DRAFT.replace("non verificata", "registrata").replace(
        "sono da verificare", "sono documentate")
    result = gate.review_comparison(text + " " + qualification)
    assert result["passed"] is accepted
    assert ("SOURCE_VERIFICATION_LIMIT_MISSING" in result["reasons"]) is not accepted


@pytest.mark.parametrize("attribution,accepted", [
    ("Confronto basato sulle note salvate.", True),
    ("Valori ricavati dalle note interne.", True),
    ("Confronto basato sulle note dell'utente.", True),
    ("Le condizioni del fornitore sono note.", False),
    ("La notazione contabile è standard.", False),
    ("Confronto senza riferimenti di provenienza.", False),
])
def test_internal_source_attribution_accepts_plural_notes_without_matching_unrelated_words(attribution, accepted):
    # f188 used "note salvate". Its separate unsupported cancellation claim
    # remains a manual rejection; this only fixes attribution morphology.
    text = gate.baseline.DRAFT.replace(
        "Secondo la nota interna non verificata presso il fornitore, ", "",
    ).replace("uguali nella nota", "uguali")
    result = gate.review_comparison(attribution + " " + text)
    assert result["passed"] is accepted
    assert ("INTERNAL_SOURCE_NOT_ATTRIBUTED" in result["reasons"]) is not accepted


@pytest.mark.asyncio
async def test_live_requested_without_credentials_is_blocked_and_nonzero(monkeypatch, tmp_path, capsys):
    for key in gate.LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    entered = []

    async def forbidden_run(*args, **kwargs):
        entered.append(True)
        raise AssertionError("preflight must precede a model attempt")

    monkeypatch.setattr(gate, "run_case", forbidden_run)
    output = tmp_path / "blocked-live.json"
    code = await gate.main(mode="live", output=str(output))
    report = json.loads(output.read_text())
    assert code == 3
    assert report["status"] == "blocked" and report["passed"] is False
    assert report["real_model_executed"] is False and report["cases"] == []
    assert not entered
    assert "LIVE_MODEL_CREDENTIALS_UNAVAILABLE" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_failed_case_has_a_nonzero_verdict_and_sanitized_exception(monkeypatch, tmp_path, capsys):
    async def broken(*args, **kwargs):
        probe = kwargs["probe"]
        probe.model_calls.append({"provider": "synthetic", "model": "synthetic",
                                  "usage": {"prompt_tokens": 7, "completion_tokens": 3}})
        probe.model_attempts = probe.model_http_requests = 1
        raise RuntimeError("synthetic private error content must not enter the report")

    monkeypatch.setattr(gate, "run_case", broken)
    output = tmp_path / "failed.json"
    assert await gate.main(scenario="completed_result", output=str(output)) == 1
    report = json.loads(output.read_text())
    assert report["status"] == "failed" and not report["passed"]
    assert report["cases"][0]["reason"] == "RuntimeError"
    assert report["cases"][0]["model_http_requests"] == 1
    assert report["cases"][0]["model_calls"][0]["usage"]["completion_tokens"] == 3
    assert "private error" not in output.read_text() + capsys.readouterr().out


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["no_goal", "wait", "clarify", None])
async def test_nonadmission_decision_survives_failed_report_without_forcing_goal(
    monkeypatch, tmp_path, capsys, outcome,
):
    from agent import reasoning
    from agent.admission import MAX_ATTEMPTS

    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-diagnostic-placeholder")
    response = {"outcome": outcome, "reasoning": "La nota non contiene ancora le condizioni utili.",
                "question": "Quale risultato è necessario?"} if outcome else None
    inputs = []

    async def decision(situation, **kwargs):
        inputs.append(situation)
        return response

    monkeypatch.setattr(reasoning, "decide_goal", decision)
    output = tmp_path / "nonadmission.json"
    assert await gate.main(mode="live", scenario="completed_result", output=str(output)) == 1
    report = json.loads(output.read_text())
    case = report["cases"][0]
    assert not case["passed"] and not case["real_model_executed"]
    assert case["model_attempts"] == 0  # Structured stub; no real model claimed.
    # Technical unavailability follows the existing durable retry budget;
    # substantive no_goal/wait/clarify decisions are never retried into a goal.
    expected_attempts = MAX_ATTEMPTS if response is None else 1
    assert len(inputs) == len(case["structured_decisions"]) == expected_attempts
    observed = case["structured_decisions"][0]
    assert observed["stage"] == "decide_goal"
    assert observed["input"]["source_context_count"] == len(inputs[0]["source_context"])
    if response is None:
        assert observed["response_kind"] == "none"
        assert "outcome" not in observed
    else:
        assert case["reason"] == "ONE_ACTIVE_GOAL_REQUIRED"
        assert observed["outcome"] == response["outcome"]
        assert observed["reasoning"] == response["reasoning"]
    assert "structured_decisions" in capsys.readouterr().out


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", [False, True])
async def test_discovery_silence_or_unavailability_is_explained_without_inventing_opportunity(
    monkeypatch, tmp_path, unavailable,
):
    from opportunities import reasoning

    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-diagnostic-placeholder")
    response = None if unavailable else {
        "opportunities": [], "reason_for_silence": "Non vedo una differenza concreta da confrontare.",
    }
    inputs = []

    async def decision(snapshot, **kwargs):
        inputs.append(snapshot)
        return response

    monkeypatch.setattr(reasoning, "scan", decision)
    output = tmp_path / "discovery.json"
    assert await gate.main(mode="live", scenario="source_change_crash", output=str(output)) == 1
    case = json.loads(output.read_text())["cases"][0]
    assert not case["passed"] and case["reason"] == "SOURCE_DISCOVERY_DID_NOT_RECOVER"
    assert case["model_attempts"] == 0 and not case["real_model_executed"]
    assert len(case["structured_decisions"]) == 1
    observed = case["structured_decisions"][0]
    assert observed["stage"] == "opportunity_scan"
    assert observed["input"]["collection_counts"]["what_changed"] == 1
    after = inputs[0]["what_changed"][0]["from_to"]["after"]
    assert len(after) > 0 and observed["input"]["change_after_lengths"] == [len(after)]
    if unavailable:
        assert observed["response_kind"] == "none" and "reason_for_silence" not in observed
    else:
        assert observed["opportunities_count"] == 0
        assert observed["reason_for_silence"] == response["reason_for_silence"]
    assert gate.baseline.FACT not in output.read_text()


@pytest.mark.asyncio
async def test_decision_observation_is_bounded_redacted_and_preserves_return_identity(monkeypatch):
    from agent import reasoning

    credential = "synthetic-diagnostic-placeholder"
    monkeypatch.setenv("GEMINI_API_KEY", credential)
    monkeypatch.setattr(gate, "MAX_DECISION_OBSERVATIONS", 2)
    response = {"outcome": "no_goal", "reasoning": credential + " " + "x" * 600,
                "raw_provider_error": "DO_NOT_EXPORT_PROVIDER_BODY", "headers": {"secret": credential},
                "outcome_assessment": {
                    "desired_outcome": credential + " " + "y" * 600,
                    "outcome_state": "open", "remaining_internal_work": "A qualified internal result",
                    "supporting_refs": [credential + " " + "r" * 300] * 11,
                    "completion_refs": [], "raw_provider_body": "DO_NOT_EXPORT_ASSESSMENT_BODY",
                }}

    async def decision(*args, **kwargs):
        return response

    monkeypatch.setattr(reasoning, "decide_goal", decision)
    db = AsyncMongoMockClient().v162_decision_diagnostics
    with gate.isolated_engine(db, mode="live") as probe:
        for _ in range(5):
            assert await reasoning.decide_goal({"source_context": [], "raw_input": credential}) is response
        assert len(probe.structured_decisions) == 2
        assert probe.structured_decisions_omitted == 3
        assert [row["sequence"] for row in probe.structured_decisions] == [1, 5]
        assert response["reasoning"].startswith(credential)  # No rewriting the model's answer.
        observed = probe.structured_decisions[0]
        assert len(observed["reasoning"]) <= gate.DECISION_TEXT_LIMIT
        assert observed["truncated_fields"] == ["reasoning"]
        assessment = observed["outcome_assessment"]
        assert assessment["outcome_state"] == "open" and observed["outcome"] == "no_goal"
        assert len(assessment["desired_outcome"]) <= gate.ASSESSMENT_TEXT_LIMIT
        assert len(assessment["supporting_refs"]) == gate.MAX_ASSESSMENT_REFS
        assert assessment["supporting_refs_omitted"] == 3
        assert all(len(ref) <= 160 for ref in assessment["supporting_refs"])
        diagnostic = json.dumps(gate.model_observations(probe))
        assert credential not in diagnostic and "DO_NOT_EXPORT_PROVIDER_BODY" not in diagnostic
        assert "DO_NOT_EXPORT_ASSESSMENT_BODY" not in diagnostic
        assert "raw_provider_error" not in diagnostic and "raw_input" not in diagnostic
        assert probe.model_attempts == probe.model_http_requests == 0


@pytest.mark.asyncio
async def test_decision_exception_observation_keeps_original_error_without_its_message(monkeypatch):
    from agent import reasoning

    error = RuntimeError("DO_NOT_EXPORT_PROVIDER_FAILURE_DETAIL")

    async def decision(*args, **kwargs):
        raise error

    monkeypatch.setattr(reasoning, "decide_goal", decision)
    db = AsyncMongoMockClient().v162_decision_error
    with gate.isolated_engine(db, mode="live") as probe:
        with pytest.raises(RuntimeError) as caught:
            await reasoning.decide_goal({})
        assert caught.value is error
        observed = probe.structured_decisions[0]
        assert observed["response_kind"] == "raised" and observed["exception_type"] == "RuntimeError"
        assert str(error) not in json.dumps(gate.model_observations(probe))


def test_discovery_proposal_diagnostics_do_not_export_unbounded_arrays_or_unknown_fields():
    response = {"opportunities": [{"what": "x" * 900, "initiative": "prepare",
                                  "raw_provider_error": "DO_NOT_EXPORT_PROVIDER_BODY",
                                  "outcome_assessment": {"outcome_state": "open",
                                                         "completion_refs": [{"raw": "DO_NOT_EXPORT_NESTED_BODY"}],
                                                         "supporting_refs": ["memory:synthetic"]}}] * 9}
    observed = gate._decision_result("opportunity_scan", response)
    assert observed["opportunities_count"] == 9
    assert len(observed["opportunities"]) == gate.MAX_DIAGNOSTIC_PROPOSALS
    assert observed["opportunities_omitted"] == 9 - gate.MAX_DIAGNOSTIC_PROPOSALS
    assert len(observed["opportunities"][0]["what"]) == gate.DECISION_TEXT_LIMIT
    assert "DO_NOT_EXPORT_PROVIDER_BODY" not in json.dumps(observed)
    assert "DO_NOT_EXPORT_NESTED_BODY" not in json.dumps(observed)
    assert observed["opportunities"][0]["outcome_assessment"]["supporting_refs"] == ["memory:synthetic"]
    assert len(response["opportunities"]) == 9 and len(response["opportunities"][0]["what"]) == 900


@pytest.mark.asyncio
@pytest.mark.parametrize("stage,response", [
    ("make_plan", {"planning_outcome": "not_possible", "steps": [], "reasoning": "Manca una capacità utile."}),
    ("verify_goal", {"outcome": "not_achieved", "reasoning": "La bozza non soddisfa ancora i criteri.",
                     "what_is_missing": "Il limite della fonte."}),
    ("choose_next_action", {"decision": "replan", "reasoning": "Restano passaggi non eseguiti."}),
])
async def test_planning_and_verification_diagnostics_preserve_the_actual_decision(monkeypatch, stage, response):
    from agent import reasoning

    async def decision(*args, **kwargs):
        return response

    monkeypatch.setattr(reasoning, stage, decision)
    db = AsyncMongoMockClient().v162_later_decision
    plan = {"status": "active", "steps": [{"id": "synthetic-step", "step_type": "prepare",
             "capability_needed": "document.create", "status": "pending", "raw_source": "DO_NOT_EXPORT"}]}
    with gate.isolated_engine(db, mode="live") as probe:
        returned = await getattr(reasoning, stage)({"status": "active"}, plan=plan, evidence=[])
        assert returned is response
        observed = probe.structured_decisions[0]
        assert observed["stage"] == stage and observed["reasoning"] == response["reasoning"]
        assert observed["input"]["plan"]["steps"][0]["status"] == "pending"
        assert "DO_NOT_EXPORT" not in json.dumps(gate.model_observations(probe))
        assert probe.model_attempts == probe.model_http_requests == 0


@pytest.mark.parametrize("payload,expected", [
    ({}, {}),
    ({"revised_steps": None}, {"revised_steps_kind": "none"}),
    ({"revised_steps": []}, {"revised_steps_kind": "array", "revised_steps_count": 0,
                            "revised_steps": [], "revised_steps_omitted": 0}),
    ({"revised_steps": "DO_NOT_EXPORT"}, {"revised_steps_kind": "text"}),
    ({"revised_steps": {"raw": "DO_NOT_EXPORT"}}, {"revised_steps_kind": "object"}),
    ({"revised_steps": 7}, {"revised_steps_kind": "other"}),
])
def test_reconsider_revision_shape_does_not_invent_or_repair_steps(payload, expected):
    response = {"decision": "modify", **payload}
    original = json.dumps(response, sort_keys=True)
    assert gate._decision_result("reconsider", response) == {
        "response_kind": "object", "decision": "modify", **expected,
    }
    assert json.dumps(response, sort_keys=True) == original


def test_reconsider_revised_steps_and_replacements_are_bounded_redacted_and_typed(monkeypatch):
    credential = "synthetic-revised-step-credential"
    monkeypatch.setenv("GEMINI_API_KEY_2", credential)
    long_text = credential + "x" * 300
    fields = ("step_type", "type", "capability_needed", "intent", "expected_result")
    response = {
        "decision": "modify",
        "revised_steps": [
            {**dict.fromkeys(fields, long_text), "raw_prompt": "DO_NOT_EXPORT"},
            {"step_type": "prepare", "type": "inspect"},
            None, [], "DO_NOT_EXPORT",
            {"step_type": ["prepare"], "type": False, "capability_needed": {},
             "intent": 7, "expected_result": None},
            *[{"intent": "DO_NOT_EXPORT"}] * 3,
        ],
        "replace_step_ids": [long_text, {"raw": "DO_NOT_EXPORT"}, None, 7,
                             *["synthetic-step-" + str(i) for i in range(9)]],
    }
    original = json.dumps(response, sort_keys=True)
    observed = gate._decision_result("reconsider", response)
    assert observed["decision"] == "modify" and observed["revised_steps_kind"] == "array"
    assert observed["revised_steps_count"] == 9
    assert len(observed["revised_steps"]) == gate.MAX_DIAGNOSTIC_PLAN_STEPS == 6
    assert observed["revised_steps_omitted"] == 3
    assert all(len(observed["revised_steps"][0][key]) == 160 for key in fields)
    assert observed["revised_steps"][0]["truncated_fields"] == list(fields)
    assert observed["revised_steps"][1:] == [
        {"step_type": "prepare", "type": "inspect"}, {"response_kind": "none"},
        {"response_kind": "array"}, {"response_kind": "text"}, {},
    ]
    assert observed["replace_step_ids_kind"] == "array"
    assert observed["replace_step_ids_count"] == 13
    assert observed["replace_step_ids_omitted"] == 13 - gate.MAX_ASSESSMENT_REFS
    assert len(observed["replace_step_ids"]) == 5  # Non-string entries are never coerced.
    assert all(len(ref) <= 160 for ref in observed["replace_step_ids"])
    assert observed["replace_step_ids"][1:] == ["synthetic-step-" + str(i) for i in range(4)]
    diagnostic = json.dumps(observed)
    assert credential not in diagnostic and "DO_NOT_EXPORT" not in diagnostic
    assert json.dumps(response, sort_keys=True) == original
    for invalid in (None, "DO_NOT_EXPORT", {"raw": "DO_NOT_EXPORT"}):
        invalid_observed = gate._decision_result("reconsider", {"replace_step_ids": invalid})
        assert "replace_step_ids" not in invalid_observed
        assert invalid_observed["replace_step_ids_kind"] == gate._response_kind(invalid)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["owned", "unmarked", "owner", "goal_owner"])
async def test_reconsider_revision_trace_preserves_identity_and_the_synthetic_guard(monkeypatch, scope):
    from agent import reasoning
    from agent.models import AutonomousGoal
    from agent.service import AgentService

    response = {"decision": "modify", "revised_steps": [{"type": "prepare", "intent": "synthetic revision"}],
                "replace_step_ids": ["synthetic-old-step"]}
    original = json.dumps(response, sort_keys=True)
    calls = []

    async def original_reconsider(goal, **kwargs):
        calls.append((goal, kwargs))
        return response

    async def original_service(self, owner, goal):
        return await reasoning.reconsider(goal.for_ai(), plan={}, what_happened={}, capabilities=[])

    monkeypatch.setattr(reasoning, "reconsider", original_reconsider)
    monkeypatch.setattr(AgentService, "_reconsider", original_service)
    db = AsyncMongoMockClient().v162_revised_step_diagnostics
    if scope != "unmarked":
        await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    goal = AutonomousGoal(owner_id="foreign-owner" if scope == "goal_owner" else gate.OWNER,
                          status="active", objective="Synthetic comparison",
                          desired_outcome="An internal result with its source limits")
    await db.agent_goals.insert_one(goal.model_dump())
    owner = "foreign-owner" if scope == "owner" else gate.OWNER
    with gate.isolated_engine(db, mode="live") as probe:
        result = await AgentService(db)._reconsider(owner, goal)
    assert result is response and json.dumps(response, sort_keys=True) == original
    assert calls == [(goal.for_ai(), {"plan": {}, "what_happened": {}, "capabilities": []})]
    if scope == "owned":
        observed, = probe.structured_decisions
        assert observed["revised_steps"] == response["revised_steps"]
        assert observed["replace_step_ids"] == response["replace_step_ids"]
        assert observed["model_attempts_before"] == observed["model_attempts_after"] == 0
    else:
        assert probe.structured_decisions == []
    assert probe.model_attempts == probe.model_http_requests == probe.blocked_effects == probe.push_attempts == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("unfinished_status", ["pending", "waiting"])
async def test_failed_completion_report_preserves_pending_steps_and_source_counts(
    monkeypatch, tmp_path, unfinished_status,
):
    from agent.models import ActionStep

    credentials = ("synthetic-result-primary-credential", "synthetic-result-alias-credential")
    monkeypatch.setenv("GEMINI_API_KEY", credentials[0])
    monkeypatch.setenv("GEMINI_API_KEY_2", credentials[1])
    original_draft = gate.baseline.DRAFT
    draft = original_draft + "\nDettagli sintetici: " + " / ".join(credentials)
    monkeypatch.setattr(gate.baseline, "DRAFT", draft)
    original_run = gate.run_case
    captured = {}

    async def completion_with_pending_step(scenario, *, mode, probe):
        await original_run(scenario, mode=mode, probe=probe)
        db = probe.database
        goal = await db.agent_goals.find_one({"owner_id": gate.OWNER})
        pending = ActionStep(intent="Verifica superflua rimasta nel piano", step_type="verify",
                             status=unfinished_status, note="Non eseguito: stato da diagnosticare.")
        query = {"owner_id": gate.OWNER, "goal_id": goal["id"]}
        await db.agent_plans.update_one(query, {"$push": {"steps": pending.model_dump()}})
        captured.update({"db": db, "query": query})
        await gate.verify_result(db, goal["id"], probe, recover=False)

    monkeypatch.setattr(gate, "run_case", completion_with_pending_step)
    output = tmp_path / "unfinished-plan.json"
    assert await gate.main(scenario="completed_result", output=str(output)) == 1
    case = json.loads(output.read_text())["cases"][0]
    assert not case["passed"] and case["reason"] == "UNFINISHED_PLAN_STEPS"
    state = case["failure_state"]
    assert state["available"] and state["goals_count"] == 1
    goal = state["goals"][0]
    assert goal["status"] == "completed" and goal["prepared_text_characters"] == len(draft)
    assert original_draft in goal["prepared_text"]
    assert goal["prepared_text"].endswith("[credential redacted] / [credential redacted]")
    assert not goal["prepared_text_truncated"]
    assert all(credential not in output.read_text() for credential in credentials)
    assert goal["source_refs_count"] > 0 and goal["prepared_sources_count"] > 0
    assert goal["current_evidence_count"] > 0
    plan = goal["plans"][0]
    assert plan["status"] == "completed" and plan["step_status_counts"][unfinished_status] == 1
    assert plan["steps"][-1]["status"] == unfinished_status
    persisted = await captured["db"].agent_plans.find_one(captured["query"])
    assert persisted["steps"][-1]["status"] == unfinished_status  # Observation cannot repair the gate.
    persisted_goal = await captured["db"].agent_goals.find_one({"owner_id": gate.OWNER})
    assert persisted_goal["prepared_text"] == draft  # Redact only the exported copy.
    assert gate.baseline.FACT not in output.read_text()


@pytest.mark.asyncio
async def test_successful_result_text_is_redacted_without_changing_acceptance(monkeypatch):
    credentials = ("synthetic-success-primary-credential", "synthetic-success-alias-credential")
    monkeypatch.setenv("GEMINI_API_KEY", credentials[0])
    monkeypatch.setenv("GEMINI_API_KEY_2", credentials[1])
    original_draft = gate.baseline.DRAFT
    draft = original_draft + "\nDettagli sintetici: " + " / ".join(credentials)
    monkeypatch.setattr(gate.baseline, "DRAFT", draft)
    probe = gate.Probe()

    report = await gate.run_case("completed_result", probe=probe)

    assert report["passed"] and report["result"]["semantic_review"]["passed"]
    assert original_draft in report["result"]["prepared_text"]
    assert report["result"]["prepared_text"].endswith("[credential redacted] / [credential redacted]")
    assert len(report["result"]["prepared_text"]) <= 6000
    assert not report["result"]["prepared_text_truncated"]
    assert all(credential not in json.dumps(report) for credential in credentials)
    persisted = await probe.database.agent_goals.find_one({"owner_id": gate.OWNER})
    assert persisted["prepared_text"] == draft


@pytest.mark.asyncio
@pytest.mark.parametrize("redaction_expands", [False, True])
async def test_failed_result_text_is_bounded_and_only_exports_the_guarded_owner(monkeypatch, redaction_expands):
    credential = "fake-key" if redaction_expands else "synthetic-bounded-alias-credential"
    monkeypatch.setenv("GEMINI_API_KEY_2", credential)
    db = AsyncMongoMockClient().v162_bounded_prepared_diagnostic
    await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": gate.OWNER})
    draft = "Confronto sintetico: " + ((credential + " ") * 400 if redaction_expands
                                       else credential + " " + "x" * 6500)
    await db.agent_goals.insert_many([
        {"id": "synthetic-owned-goal", "owner_id": gate.OWNER, "status": "completed", "prepared_text": draft},
        {"id": "synthetic-foreign-goal", "owner_id": "another-synthetic-owner", "status": "completed",
         "prepared_text": "FOREIGN_PREPARED_TEXT_MUST_NOT_BE_EXPORTED"},
    ])

    state = await gate.failure_state(gate.Probe(database=db))

    assert state["available"] and state["goals_count"] == 1
    row = state["goals"][0]
    assert row["prepared_text_characters"] == len(draft)
    assert row["prepared_text_truncated"] and len(row["prepared_text"]) == 6000
    assert row["prepared_text"].startswith("Confronto sintetico: [credential redacted] ")
    assert credential not in json.dumps(state)
    assert "FOREIGN_PREPARED_TEXT_MUST_NOT_BE_EXPORTED" not in json.dumps(state)
    assert (await db.agent_goals.find_one({"id": "synthetic-owned-goal"}))["prepared_text"] == draft


@pytest.mark.asyncio
@pytest.mark.parametrize("guard_owner", [None, "another-synthetic-owner"])
async def test_failed_result_text_is_not_exported_without_the_evaluator_owner_guard(guard_owner):
    db = AsyncMongoMockClient().v162_untrusted_prepared_diagnostic
    if guard_owner is not None:
        await db.eval_guards.insert_one({"_id": gate.VERSION, "owner": guard_owner})
    await db.agent_goals.insert_one({
        "id": "synthetic-goal", "owner_id": gate.OWNER, "status": "completed",
        "prepared_text": "UNGUARDED_PREPARED_TEXT_MUST_NOT_BE_EXPORTED",
    })

    state = await gate.failure_state(gate.Probe(database=db))

    assert state == {"available": False, "reason": "SYNTHETIC_DIAGNOSTIC_GUARD_MISSING"}
    assert "UNGUARDED_PREPARED_TEXT_MUST_NOT_BE_EXPORTED" not in json.dumps(state)


@pytest.mark.asyncio
async def test_world_action_is_blocked_before_the_executor_can_act():
    from agent.execution import StepExecutor
    from agent.models import ActionStep, AutonomousGoal

    db = AsyncMongoMockClient().v162_effect_boundary
    with gate.isolated_engine(db) as probe:
        goal = AutonomousGoal(owner_id=gate.OWNER, objective="Synthetic boundary", desired_outcome="No effects")
        step = ActionStep(intent="Attempt forbidden action", step_type="execute", capability_needed="calendar.create")
        with pytest.raises(gate.EvaluationFailure, match="STEP_EFFECT_OR_OWNER_BOUNDARY"):
            await StepExecutor(db).run(gate.OWNER, goal, step, may_touch_the_world=True)
        assert probe.blocked_effects == 1
        assert await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_unscoped_external_http_is_blocked_before_transport():
    from scripts.phase1_read_provider_eval import EvaluationBoundaryError

    db = AsyncMongoMockClient().v162_network_boundary
    with gate.isolated_engine(db) as probe:
        async with httpx.AsyncClient(trust_env=False) as client:
            with pytest.raises(EvaluationBoundaryError, match="EVAL_HTTP_NOT_ALLOWLISTED"):
                await client.get("https://example.invalid/forbidden")
        assert probe.network.blocked == ["EVAL_HTTP_NOT_ALLOWLISTED"]
        assert probe.network.reads == []


@pytest.mark.asyncio
async def test_model_fallbacks_share_a_transport_budget_before_network_spending(monkeypatch):
    from llm.manager import ProviderManager

    transported = []

    def fake_transport(request):
        transported.append(request.url.host)
        return httpx.Response(503, json={"error": "synthetic transient failure"})

    async def fallback_chat(*args, **kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake_transport), trust_env=False) as client:
            for _ in range(3):
                await client.post("https://api.openai.com/v1/chat/completions", json={"synthetic": True})
        raise AssertionError("third transport attempt must not happen")

    monkeypatch.setattr(ProviderManager, "chat", fallback_chat)
    monkeypatch.setattr(gate, "MAX_MODEL_HTTP_REQUESTS", 2)
    db = AsyncMongoMockClient().v162_model_transport_budget
    with gate.isolated_engine(db, mode="live") as probe:
        with pytest.raises(gate.EvaluationFailure, match="MODEL_HTTP_BOUND_EXCEEDED"):
            await ProviderManager.chat(object())
        assert transported == ["api.openai.com", "api.openai.com"]
        assert probe.model_http_requests == 2 and probe.model_attempts == 1
        assert probe.network.blocked == ["MODEL_HTTP_BOUND_EXCEEDED"]
        assert probe.network.scope.get() == "blocked"


@pytest.mark.asyncio
async def test_successful_model_response_without_observed_http_cannot_pass(monkeypatch):
    from llm.base import LLMResult
    from llm.manager import ProviderManager

    async def unobserved_response(*args, **kwargs):
        return LLMResult(text="Synthetic cached response", provider="gemini",
                         model="synthetic-evaluation-model", usage={"total_tokens": 6})

    monkeypatch.setattr(ProviderManager, "chat", unobserved_response)
    db = AsyncMongoMockClient().v162_unobserved_model_transport
    with gate.isolated_engine(db, mode="live") as probe:
        with pytest.raises(gate.EvaluationFailure, match="^MODEL_HTTP_NOT_OBSERVED$"):
            await ProviderManager.chat(object())
        assert probe.model_attempts == 1 and probe.model_http_requests == 0
        assert probe.network.blocked == ["MODEL_HTTP_NOT_OBSERVED"]
        assert probe.network.scope.get() == "blocked"
        # Preserve the response evidence without accepting the transport claim.
        report = gate.model_observations(probe)
        assert report["model_calls"][0]["usage"]["total_tokens"] == 6
        assert report["global_socket_dns_sandbox"] is False


@pytest.mark.asyncio
async def test_unmarked_database_cannot_be_given_synthetic_clock_changes():
    db = AsyncMongoMockClient().v162_unmarked
    with pytest.raises(gate.EvaluationFailure, match="SYNTHETIC_CLOCK_GUARD_MISSING"):
        await gate.recover_home(db)


@pytest.mark.asyncio
async def test_existing_user_database_is_not_seeded():
    db = AsyncMongoMockClient().v162_existing
    await db.users.insert_one({"user_id": "another-fictional-owner"})
    with pytest.raises(gate.EvaluationFailure, match="EVALUATOR_DATABASE_NOT_EMPTY"):
        await gate.seed_case(db, "completed_result")
    assert await db.memories.count_documents({}) == 0
    assert await db.eval_guards.count_documents({}) == 0

@pytest.mark.asyncio
async def test_live_case_progress_log_bounds_failure_reason(monkeypatch, capsys):
    """Railway's per-line limit must not hide the reason for a failed case."""
    raw_reason = "HOME_RECOVERY_FAILURE:" + "!" * 300

    async def failed_case(_scenario, *, mode, probe):
        raise gate.EvaluationFailure(raw_reason)

    async def failure_snapshot(_probe):
        return {}

    monkeypatch.setattr(gate, "run_case", failed_case)
    monkeypatch.setattr(gate, "failure_state", failure_snapshot)
    exit_code = await gate.main(mode="scripted", scenario="home_write_retry")
    assert exit_code == 1

    case_line = next(line for line in capsys.readouterr().out.splitlines()
                     if line.startswith("ORA_AUTONOMY_COMPLETION_CASE "))
    record = json.loads(case_line.split(" ", 1)[1])
    assert record["scenario"] == "home_write_retry"
    assert record["passed"] is False
    assert record["failure_code"] == "HOME_RECOVERY_FAILURE:" + "_" * (160 - 22)
    assert len(record["failure_code"]) == 160
    assert raw_reason not in case_line
