"""The real preparation path passes bounded, provenance-aware instructions.

Uses a synthetic source and injected model decisions. No provider call, account
or external effect is performed.
"""
import json

import pytest

from agent import reasoning
from agent.providers import prepare_locally
from test_agent_preparation_v4 import fixture, source_review


@pytest.mark.asyncio
async def test_short_source_draft_and_audit_keep_compact_attributed_comparison(monkeypatch):
    db, goal, evidence, step = await fixture()
    messages = []
    content = ("Secondo il documento fornito, il costo annuo dichiarato è di "
               "120 euro e non è previsto il rimborso. Nessuna conferma indipendente "
               "delle condizioni attuali è presente.")

    async def fake_model(system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        messages.append((system, payload))
        if "draft" in payload:
            return {"verified": True, "content": content,
                    "evidence_ids": [evidence.id],
                    "claim_review": source_review(evidence)}
        return {"content": content, "evidence_ids": [evidence.id]}

    monkeypatch.setattr(reasoning, "_ask_model", fake_model)
    result = await prepare_locally(db, "alice", goal, step)
    assert result.status == "succeeded"
    assert goal.prepared_text == content
    assert len(messages) == 2
    draft_prompt, draft_payload = messages[0]
    audit_prompt, audit_payload = messages[1]
    assert "aim for a complete draft under 1800 characters" in draft_prompt
    assert "does not allow omission of the useful calculation" in draft_prompt
    assert "comparison specifically requested from figures recorded by the user" in audit_prompt
    assert "unless the goal actually requires external verification" in audit_prompt
    assert draft_payload["evidence"][0]["claim"] == evidence.claim
    assert audit_payload["draft"] == content
