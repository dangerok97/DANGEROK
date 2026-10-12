"""Native output contracts preserve the existing grounded-preparation gates.

Synthetic source rows and injected model answers exercise the real preparation
and persistence path. No model, external account or network is used. These
checks establish shape/source-scope transport, not semantic entailment.
"""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator
from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import preparation, reasoning
from agent.models import ActionStep, AgentEvidence, AutonomousGoal, ResultProvenance


OWNER = "synthetic-preparation-schema-v162"
TEXT = "La nota salvata riporta sette unità; il dato è dichiarato dall'utente."


async def seed(*, sources=1):
    db = AsyncMongoMockClient().preparation_response_schema_v162
    goal = AutonomousGoal(
        owner_id=OWNER, status="active", objective="Preparare una sintesi della nota.",
        desired_outcome="Un testo attribuito alle fonti lette, con i loro limiti.",
    )
    await db.agent_goals.insert_one(goal.model_dump())
    for index in range(sources):
        evidence = AgentEvidence(
            owner_id=OWNER, goal_id=goal.id,
            claim=(f"Nota sintetica {index}: sette unità dichiarate. " + "Contesto della nota. " * 25)[:590],
            provenance=ResultProvenance(
                source_class="internal_observation", provider="synthetic_owned_reader",
                source_refs=[f"document:synthetic-note-{index}"],
                certainty_note="Dato dichiarato; nessuna conferma esterna.",
            ),
        )
        await db.agent_evidence.insert_one(evidence.model_dump())
    step = ActionStep(intent="Sintetizzare la fonte letta.", step_type="prepare", capability_needed="document.create")
    return db, goal, step


def reply(payload, *, content=TEXT, verified=True):
    refs = [payload["evidence"][-1]["id"]] if verified else []
    result = {"content": content if verified else "", "evidence_ids": refs}
    if "draft" in payload:
        review = [{"claim": "La nota dichiara sette unità.", "premises": "Dato riportato nella nota.",
                   "support": "stated", "correction": "", "evidence_ids": list(refs),
                   "source_quotes": [{"evidence_id": refs[0], "quote": "sette unità dichiarate."}]}] if verified else []
        result.update({"claim_review": review, "verified": verified,
                       "reason": "Sintesi attribuita alla fonte." if verified else "Manca una premessa necessaria."})
    return result


@pytest.mark.asyncio
async def test_both_preparation_calls_receive_typed_source_scoped_native_schema(monkeypatch):
    db, goal, step = await seed()
    seen = []

    async def model(system, user, *, response_schema=None):
        payload = json.loads(user)
        answer = reply(payload)
        seen.append((payload, response_schema, deepcopy(answer)))
        return answer

    monkeypatch.setattr(reasoning, "_ask_model", model)
    outcome = await preparation.prepare(db, OWNER, goal, step)
    assert outcome.status == "succeeded" and len(seen) == 2
    assert (await db.agent_goals.find_one({"id": goal.id, "owner_id": OWNER}))["prepared_text"] == TEXT
    for payload, schema, answer in seen:
        assert isinstance(schema, dict), "Preparation must forward its output contract to the provider"
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        assert validator.is_valid(answer)
        assert schema["type"] == "object" and schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        assert schema["properties"]["content"]["type"] == "string"
        assert schema["properties"]["evidence_ids"]["items"]["enum"] == [row["id"] for row in payload["evidence"]]
        assert not validator.is_valid({**answer, "content": {"text": TEXT}})
        assert not validator.is_valid({**answer, "evidence_ids": ["evd_foreign_or_invented"]})
        assert not validator.is_valid({**answer, "evidence_ids": "not-an-array"})
        assert not validator.is_valid({**answer, "unexpected_field": "must-not-be-accepted"})
    audit = seen[1][1]
    assert audit["properties"]["verified"] == {"type": "boolean"}
    assert not Draft202012Validator(audit).is_valid({**seen[1][2], "verified": "true"})
    check = audit["properties"]["claim_review"]["items"]
    assert set(check["required"]) == set(check["properties"])
    assert check["additionalProperties"] is False
    assert check["properties"]["support"]["enum"] == ["stated", "derived", "conditional", "unsupported"]


@pytest.mark.asyncio
async def test_audit_schema_uses_only_evidence_that_survived_its_own_context_bound(monkeypatch):
    db, goal, step = await seed(sources=12)
    seen = []
    content = "La nota riporta sette unità. " * 135
    assert 3500 < len(content) <= 4000

    async def model(system, user, *, response_schema=None):
        payload = json.loads(user)
        seen.append((payload, response_schema))
        return reply(payload, content=content)

    monkeypatch.setattr(reasoning, "_ask_model", model)
    outcome = await preparation.prepare(db, OWNER, goal, step)
    assert outcome.status == "succeeded" and len(seen) == 2
    before, after = seen
    assert len(before[0]["evidence"]) > len(after[0]["evidence"])
    assert after[0]["evidence_truncated"] is True
    for payload, schema in seen:
        assert isinstance(schema, dict)
        assert schema["properties"]["evidence_ids"]["items"]["enum"] == [row["id"] for row in payload["evidence"]]
    removed = {row["id"] for row in before[0]["evidence"]} - {row["id"] for row in after[0]["evidence"]}
    audit_validator = Draft202012Validator(after[1])
    assert all(not audit_validator.is_valid({**reply(after[0]), "evidence_ids": [ref]}) for ref in removed)


@pytest.mark.asyncio
async def test_native_schema_allows_a_negative_audit_and_it_cannot_save_a_result(monkeypatch):
    db, goal, step = await seed()
    calls = []

    async def model(system, user, *, response_schema=None):
        payload = json.loads(user)
        answer = reply(payload, verified="draft" not in payload)
        assert isinstance(response_schema, dict)
        assert Draft202012Validator(response_schema).is_valid(answer)
        calls.append(answer)
        return answer

    monkeypatch.setattr(reasoning, "_ask_model", model)
    outcome = await preparation.prepare(db, OWNER, goal, step)
    assert outcome.status == "unavailable" and outcome.error_type == "preparation_not_supported"
    assert len(calls) == 2 and calls[-1]["verified"] is False
    saved = await db.agent_goals.find_one({"id": goal.id, "owner_id": OWNER})
    assert not saved.get("prepared_text") and not saved.get("prepared_sources") and not outcome.claims


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["generation_object", "audit_object", "audit_false_string", "foreign_ref", "too_long"])
async def test_provider_ignoring_native_contract_still_hits_existing_local_guards(monkeypatch, violation):
    db, goal, step = await seed()
    calls = []

    async def model(system, user, *, response_schema=None):
        payload = json.loads(user)
        assert isinstance(response_schema, dict)
        answer = reply(payload)
        audit = "draft" in payload
        if violation == "generation_object" and not audit or violation == "audit_object" and audit:
            answer["content"] = {"text": TEXT}
        elif violation == "audit_false_string" and audit:
            answer["verified"] = "true"
        elif violation == "foreign_ref" and audit:
            answer["evidence_ids"] = ["evd_from_another_goal"]
        elif violation == "too_long" and not audit:
            answer["content"] = "è" * 4001
        calls.append((answer, deepcopy(answer)))
        return answer

    monkeypatch.setattr(reasoning, "_ask_model", model)
    outcome = await preparation.prepare(db, OWNER, goal, step)
    assert outcome.status == "unavailable" and not outcome.claims
    expected = ("preparation_ungrounded" if violation in ("generation_object", "too_long")
                else "preparation_not_supported" if violation == "audit_false_string" else "preparation_review_invalid")
    assert outcome.error_type == expected
    assert len(calls) == (1 if violation in ("generation_object", "too_long") else 2)
    assert all(original == snapshot for original, snapshot in calls)
    saved = await db.agent_goals.find_one({"id": goal.id, "owner_id": OWNER})
    assert not saved.get("prepared_text") and not saved.get("prepared_sources")


def test_schema_instances_do_not_share_source_refs_or_mutable_nested_state():
    from agent.preparation_schema import draft_schema, audit_schema

    source_ids = ["evd_first", "evd_second"]
    first = draft_schema(source_ids)
    audit = audit_schema(source_ids)
    source_ids.append("evd_changed_after_request")
    first["properties"]["evidence_ids"]["items"]["enum"].append("evd_mutated_by_adapter")
    later = draft_schema(["evd_third"])
    assert later["properties"]["evidence_ids"]["items"]["enum"] == ["evd_third"]
    assert audit["properties"]["evidence_ids"]["items"]["enum"] == ["evd_first", "evd_second"]
    audit["properties"]["claim_review"]["items"]["properties"]["evidence_ids"]["items"]["enum"].append("evd_nested")
    assert audit["properties"]["evidence_ids"]["items"]["enum"] == ["evd_first", "evd_second"]
