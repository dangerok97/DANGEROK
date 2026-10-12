"""Compact, privacy-safe per-case Railway verdicts for the autonomous engine.

Full reports remain written as artifacts. A provider or worker failure cannot
hide the current checkpoint behind Railway's oversized-line truncation.
"""
import json

from scripts import autonomy_completion_eval_v162 as gate


def test_failed_case_reports_only_machine_state_and_not_source_text():
    probe = gate.Probe(model_attempts=9, model_http_requests=12)
    probe.result_checks = {
        "semantic": {"status": "failed", "review": {"reason": "PRIVATE_COMPARISON_TEXT"}},
        "home": {"status": "passed", "raw_activity": "PRIVATE_HOME_TEXT"},
    }
    case = {
        "scenario": "memory_corrected", "mode": "live", "passed": False,
        "reason": "COMPLETION_NEEDS_NEW_DECISION",
        "failure_state": {"goals": [{
            "status": "active", "requires_user_input": True,
            "requires_user_authority": False, "has_next_run_at": False,
            "planning_unavailable": False, "prepared_text_characters": 271,
            "prepared_text": "PRIVATE_PREPARED_SOURCE",
            "rationale": "PRIVATE_RATIONALE",
        }]},
    }
    result = gate._case_progress_record(case, probe)
    assert result["scenario"] == "memory_corrected"
    assert result["failure_code"] == "COMPLETION_NEEDS_NEW_DECISION"
    assert result["goal_status"] == "active"
    assert result["requires_user_input"] is True
    assert result["requires_user_authority"] is False
    assert result["has_next_run_at"] is False
    assert result["prepared_text_characters"] == 271
    assert result["result_checks"]["home"] == "passed"
    assert result["result_checks"]["semantic"] == "failed"
    assert result["result_checks"]["replay"] == "unknown"
    serialized = json.dumps(result, ensure_ascii=False)
    assert len(serialized) < 1100
    assert "PRIVATE_" not in serialized


def test_success_logs_do_not_claim_an_unobserved_delivery():
    case = {"scenario": "completed_result", "mode": "live", "passed": True}
    result = gate._case_progress_record(case, gate.Probe())
    assert result["failure_code"] is None
    assert result["goal_status"] is None
    assert result["result_checks"] is None
    assert result["requires_user_input"] is None
    assert result["passed"] is True


def test_unknown_goal_state_and_untrusted_check_status_are_not_emitted():
    probe = gate.Probe()
    probe.result_checks = {"home": {"status": "PRIVATE_UNEXPECTED"}}
    case = {"scenario": "home_write_retry", "mode": "scripted", "passed": False,
            "reason": "FAILED_HOME_HANDOFF",
            "failure_state": {"goals": [{"status": "PRIVATE_STATUS",
                "prepared_text_characters": 999999}]}}
    record = gate._case_progress_record(case, probe)
    assert record["goal_status"] is None
    assert record["prepared_text_characters"] is None
    assert record["result_checks"]["home"] == "unknown"
    assert "PRIVATE_" not in json.dumps(record)
