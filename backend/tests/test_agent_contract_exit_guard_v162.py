"""Safe internal contract comparisons must not invent penalty-free exits.

The small lexical guard is deliberately a one-way refusal, not an entitlement
or a general semantic verifier. A matching source clause is still only
user-reported unless independently verified.
"""
import json

import pytest

from agent.contract_claims import unsupported_contract_exit_claims
from agent.execution import StepExecutor
from test_preparation_source_quotes_v162 import OWNER, audit, install, seed


NOTE = (
    "Uso il piano mensile e intendo tenerlo dodici mesi: 15 euro al mese, "
    "180 euro per dodici mesi. Il piano annuale costa 120 euro anticipati. "
    "L'annuale non rimborsa la disdetta anticipata. Le condizioni del "
    "mensile su recesso, penali e rimborso non sono specificate."
)


def owned(claim=NOTE):
    return [{"id": "evd_owned", "claim": claim,
             "source_class": "internal_observation"}]


@pytest.mark.parametrize("claim", [
    "Il piano mensile permette di interrompere senza penalizzazioni.",
    "**1. Piano mensile**\n- Vincoli: nessuna penalizzazione finanziaria esplicita.",
    "Piano mensile: disdetta senza costi di recesso.",
    "Il mensile offre libertà di interruzione senza perdite.",
])
def test_unsupported_monthly_no_penalty_right_is_not_a_grounded_result(claim):
    verdict = unsupported_contract_exit_claims(claim, owned())
    assert verdict == ["monthly_no_penalty_not_in_source"]


def test_monthly_can_never_borrow_penalty_clause_from_annual():
    source = owned(
        "Il piano mensile costa 15 euro. Il piano annuale non prevede penali di recesso."
    )
    assert unsupported_contract_exit_claims(
        "Piano mensile: senza penali per disdetta anticipata.", source
    ) == ["monthly_no_penalty_not_in_source"]


def test_supported_monthly_penalty_clause_is_not_rejected_by_missing_source_guard():
    source = owned(
        "Il piano mensile può essere disdetto senza penali. "
        "L'annuale non prevede rimborso alla disdetta."
    )
    assert unsupported_contract_exit_claims(
        "Il piano mensile si può disdire senza penali.", source
    ) == []


def test_refund_right_cannot_be_deduced_from_unknown_monthly_terms():
    verdict = unsupported_contract_exit_claims(
        "Piano mensile: rimborso non garantito ma non vietato.", owned()
    )
    assert verdict == ["monthly_refund_possible_not_in_source"]


@pytest.mark.parametrize("safe", [
    "La nota dell'utente riporta 180 euro contro 120, differenza 60.",
    "Le penali per il piano mensile non sono specificate nella nota.",
    "Non è noto se il piano mensile sia senza penali; serve verifica.",
    "Il piano annuale non prevede rimborso in caso di disdetta anticipata.",
    "Entrambe le formule hanno spese iniziali nulle.",
])
def test_unknown_terms_and_actual_reported_facts_remain_allowed(safe):
    assert unsupported_contract_exit_claims(safe, owned()) == []


def test_risk_codes_do_not_retain_private_input_or_source_excerpt():
    private = "Piano mensile riservato al cliente fittizio, senza penalizzazioni."
    findings = unsupported_contract_exit_claims(private, owned(NOTE + " ref:private-sensitive"))
    assert findings
    assert "private" not in json.dumps(findings)
    assert "cliente" not in json.dumps(findings)
    assert all(len(item) < 70 for item in findings)


@pytest.mark.asyncio
async def test_preparation_refuses_invented_exit_clause_before_any_durable_draft(monkeypatch):
    h = await seed()
    checked = audit(h)
    checked["content"] += "\nIl piano mensile si può interrompere senza penali."
    seen = install(monkeypatch, h, checked)
    outcome = await StepExecutor(h.db).run(
        OWNER, h.goal, h.step, may_touch_the_world=False,
    )
    assert len(seen) == 2  # The unchanged model generation and audit calls.
    assert outcome.status == "unavailable"
    assert outcome.error_type == "preparation_unsupported_contract_term"
    assert h.goal.prepared_text == ""
    saved = await h.db.agent_goals.find_one(
        {"owner_id": OWNER, "id": h.goal.id},
    )
    assert not saved.get("prepared_text")
    feedback = await h.db.agent_journal.find_one(
        {"owner_id": OWNER, "goal_id": h.goal.id, "kind": "preparation_review_feedback"},
    )
    assert feedback is not None
    assert feedback["detail"]["feedback"]["origin"] == "preparation_audit"
    assert not await h.db.agent_action_attempts.count_documents({})
