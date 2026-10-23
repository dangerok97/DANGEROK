"""A refused estimate says which rule refused it.

Production, 9–23/10/2026: 16 `situation_outcome_rejected` against 2 assessed,
all with the same generic note. Without the rule the failures could only be
guessed at. The journal now records the rule and the proposal's shape.
"""
import ast
import asyncio
import inspect

from situations import outcomes


def test_validator_has_no_silent_rejection_left():
    tree = ast.parse(inspect.getsource(outcomes.validate_assessment))
    bare = [n for n in ast.walk(tree)
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) and n.value.value is None]
    assert bare == []
    codes = [n.args[1].value for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_reject"]
    assert len(codes) == len(set(codes)) >= 19
    assert "estimate_without_baseline" in codes and "no_fresh_evidence_this_run" in codes


class Goal:
    owner_id = "owner"
    source_kind = "situation_followup"
    source_refs = ["situation:sit_x"]
    source_situation = {"situation_id": "sit_x", "situation_revision": "1"}


def test_reason_is_reported_and_result_stays_unknown():
    reasons = []
    out = asyncio.run(outcomes.validate_assessment(None, "other", Goal(), {}, evidence=[], reasons=reasons))
    assert out is None and reasons == ["no_binding"]
    # Callers that do not ask keep the old contract.
    assert asyncio.run(outcomes.validate_assessment(None, "other", Goal(), {}, evidence=[])) is None


def test_journal_records_rule_and_shape_never_words():
    from agent import service
    src = inspect.getsource(service.AgentService._record_situation_outcome)
    assert '"rejected_by"' in src and '"proposed"' in src
    assert 'raw.get("headline")' not in src and 'raw.get("action_summary")' not in src
