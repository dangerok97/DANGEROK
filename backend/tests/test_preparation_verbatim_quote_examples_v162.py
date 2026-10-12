"""Optional audit copying aids stay bounded and sourced to exact claim rows.

A copying hint does not certify a semantic inference, change citation rules,
or include any discarded/foreign evidence or metadata.
"""
from agent import preparation
from agent.execution import StepExecutor
from test_preparation_source_quotes_v162 import OWNER, audit, install, seed


def test_verbatim_examples_are_literal_bounded_substrings_only():
    rows = [
        {"id": "evd_owned_a", "claim":
            "Il costo mensile è 15 euro; dodici mesi danno 180 euro. "
            "Il costo annuale è 120 euro. Nessun prezzo è verificato online.",
         "limits": "TEST_STRING_ONLY_IN_METADATA"},
        {"id": "evd_owned_b", "claim": "Blocco molto lungo " * 90},
        {"id": "evd_unusable", "claim": None},
    ]
    hints = preparation._literal_quote_examples(rows)
    assert hints and {r["evidence_id"] for r in hints} <= {"evd_owned_a", "evd_owned_b"}
    assert sum(len(x) for row in hints for x in row["examples"]) <= 720
    for row in hints:
        original = next(x["claim"] for x in rows if x["id"] == row["evidence_id"])
        assert 1 <= len(row["examples"]) <= 4
        assert len(row["examples"]) == len(set(row["examples"]))
        assert all(4 <= len(example) <= 240 and example in original
                   for example in row["examples"])
        assert all("TEST_STRING_ONLY_IN_METADATA" not in x for x in row["examples"])
    assert any("Il costo annuale" in x for x in hints[0]["examples"])


def test_empty_or_nontext_claims_never_generate_quotes():
    assert preparation._literal_quote_examples([
        {"id": "evd_1", "claim": ""},
        {"id": "evd_2", "claim": None},
        {"id": "evd_3", "claim": False},
    ]) == []


async def _run_sourced_prepare(monkeypatch):
    h = await seed()
    seen = install(monkeypatch, h, audit(h))
    result = await StepExecutor(h.db).run(
        OWNER, h.goal, h.step, may_touch_the_world=False,
    )
    return h, seen, result


import pytest


@pytest.mark.asyncio
async def test_audit_receives_exact_quote_hints_without_weaker_validation(monkeypatch):
    h, seen, result = await _run_sourced_prepare(monkeypatch)
    assert result.status == "succeeded" and len(seen) == 2
    audit_payload = seen[-1][0]
    choices = audit_payload["verbatim_quote_examples"]
    asserted = {row["id"]: row["claim"] for row in audit_payload["evidence"]}
    assert choices
    for item in choices:
        assert item["evidence_id"] in asserted
        assert all(quote in asserted[item["evidence_id"]] for quote in item["examples"])
    # The model's actual chosen quotes continue to be validated against the
    # exact audit rows (including evidence ownership); hints do not bypass it.
    assert audit_payload["evidence"] == seen[0][0]["evidence"]
    assert h.goal.prepared_sources == [source.id for source in h.sources]
