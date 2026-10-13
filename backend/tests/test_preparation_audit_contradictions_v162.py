"""Bounded, domain-neutral self-contradiction gate on positive model audits.

No LLM, network, personal account or real source is used. The positive gate
cannot prove entailment: it only refuses when the auditor *itself* admits its
positive verdict is unsound.
"""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from agent import preparation
from test_preparation_source_quotes_v162 import OWNER, TEXT, audit, install, seed


@pytest.mark.parametrize("support,counterexample,claim,content,expected", [
    ("derived", "The same source permits an alternative that defeats it.",
     "The price is fixed.", TEXT, ["counterexample_defeats_asserted_support"]),
    ("stated", "A compatible alternative exists.",
     "The source proves an obligation.", TEXT, ["counterexample_defeats_asserted_support"]),
    ("unsupported", "", "B may cancel with no penalty.",
     "B may cancel with no penalty.", ["unsupported_clause_kept_in_corrected_text"]),
    ("unsupported", "", "B may cancel with no penalty.",
     TEXT, []),
    ("conditional", "Without the missing requirement the claim may fail.",
     "Only if the stated requirement holds.", TEXT, []),
])
def test_self_contradiction_inference_is_narrow_and_source_neutral(
    support, counterexample, claim, content, expected
):
    row = {"support": support, "claim": claim,
           "compatible_counterexample": counterexample}
    review = {"verified": True, "content": content, "claim_review": [row]}
    assert preparation._positive_audit_contradictions(review) == expected
    assert preparation._positive_audit_contradictions({**review, "verified": False}) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["refuted_derived", "unsupported_kept"])
async def test_positive_audit_cannot_publish_its_own_admitted_contradiction(
    monkeypatch, case
):
    h = await seed()
    checked = audit(h)
    if case == "refuted_derived":
        checked["claim_review"][0].update(
            inference_or_gap="The chosen source premises leave a defeating alternative open.",
            compatible_counterexample="A distinct source-compatible alternative defeats the conclusion.",
        )
    else:
        checked["claim_review"][0].update(
            support="unsupported",
            claim="B può essere interrotto senza vincoli.",
            premises="Non è specificato quando B possa essere interrotto.",
            correction="Omettere la clausola che non risulta dalla fonte.",
            source_quotes=[],
        )
        checked["content"] = "B può essere interrotto senza vincoli."
    original = deepcopy(checked)
    old = "Risultato precedente, ancora conservato."
    h.goal.prepared_text = old
    h.goal.prepared_sources = [h.sources[0].id]
    await h.db.agent_goals.update_one(
        {"id": h.goal.id, "owner_id": OWNER},
        {"$set": {"prepared_text": old, "prepared_sources": h.goal.prepared_sources}},
    )
    calls = install(monkeypatch, h, checked)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    assert result.status == "unavailable"
    assert result.error_type == "preparation_review_self_contradiction"
    assert result.retryable is True
    assert len(calls) == 2 and checked == original
    saved = await h.db.agent_goals.find_one({"id": h.goal.id, "owner_id": OWNER})
    assert saved["prepared_text"] == h.goal.prepared_text == old
    assert not await h.db.agent_evidence.count_documents(
        {"provenance.provider": "generated_draft"}
    )


@pytest.mark.asyncio
async def test_audit_correcting_unsupported_clause_can_save_supported_result(monkeypatch):
    h = await seed()
    checked = audit(h)
    checked["claim_review"][0].update(
        support="unsupported",
        claim="B può essere interrotto senza vincoli.",
        correction="Rimuovere la clausola non documentata.",
        source_quotes=[],
    )
    checked["content"] = TEXT
    install(monkeypatch, h, checked)
    result = await preparation.prepare(h.db, OWNER, h.goal, h.step)
    assert result.status == "succeeded"
    assert h.goal.prepared_text == TEXT

