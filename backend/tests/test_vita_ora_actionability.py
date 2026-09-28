"""VITA answers must be readable as task evidence in all ten areas."""
from __future__ import annotations

import pytest

from conversation_engine.ai_core.context_sources import ContextSourceRegistry, rank_evidence
from conversation_engine.ai_core.models import ContextNeed
from conversation_engine.ai_core.tools.registry import ToolRegistry
from life_memory.assemble import assemble_life_memory
from life_memory.statements import statement_for_profile_fact
from life_profile.areas import all_areas
from life_profile.guided import for_area
from life_setup.models import DomainProfile, LifeProfile, ProfileObject


def _answer(area):
    obj = next(o for o in for_area(area.id) if o.options)
    value = [obj.options[0].id] if obj.control == "multi" else obj.options[0].id
    return obj.id, value, obj.options[0].label


@pytest.mark.parametrize(
    "objective",
    [obj for area in all_areas() for obj in for_area(area.id) if obj.options],
    ids=lambda obj: obj.id,
)
def test_every_guided_choice_can_be_read_as_the_users_answer(objective):
    for option in objective.options:
        value = [option.id] if objective.control == "multi" else option.id
        statement = statement_for_profile_fact(
            domain=objective.id.split(".")[0], key=objective.id, value=value,
        )
        assert statement and option.label in statement, (objective.id, option.id)
    if objective.control == "multi" and len(objective.options) > 1:
        value = [option.id for option in objective.options[:2]]
        statement = statement_for_profile_fact(
            domain=objective.id.split(".")[0], key=objective.id, value=value,
        )
        assert objective.options[1].label in statement


@pytest.mark.parametrize(
    "objective",
    [obj for area in all_areas() for obj in for_area(area.id)
     if not obj.options and obj.control != "document_upload"],
    ids=lambda obj: obj.id,
)
def test_non_choice_answers_have_readable_evidence_or_explicit_sensitive_exclusion(objective):
    samples = {"location": "Roma", "text": "Impiegato", "number": 2,
               "currency": 1200, "date": "2026-11-03"}
    statement = statement_for_profile_fact(
        domain=objective.id.split(".")[0], key=objective.id,
        value=samples[objective.control],
    )
    if objective.id == "casa.mutuo_rata":
        assert statement is None
    else:
        assert statement and (
            ":" in statement or statement in ("Vivi a Roma.", "Lavori come Impiegato.")
        )


@pytest.mark.parametrize("area", all_areas(), ids=lambda a: a.id)
def test_guided_answer_from_each_area_is_human_task_evidence(area):
    key, value, label = _answer(area)
    statement = statement_for_profile_fact(domain=key.split(".")[0], key=key, value=value)
    assert statement and label in statement, (area.id, key, value)
    profile = LifeProfile(user_id="synthetic", domains={key.split(".")[0]: DomainProfile(
        domain=key.split(".")[0], objects={key: ProfileObject(
            key=key, value=value, source="user_confirmed", status="confirmed", confirmed=True,
        )},
    )})
    candidates, evidence, _ = assemble_life_memory(profile=profile.public())
    assert any(label in c.statement for c in candidates), area.id
    assert any(key in e.id for e in evidence), area.id


class _Profiles:
    def __init__(self, doc):
        self.doc = doc

    async def find_one(self, query, projection=None):
        return self.doc if query.get("user_id") == self.doc["user_id"] else None


class _DB:
    def __init__(self, profile):
        self.life_profiles = _Profiles(profile.public())


@pytest.mark.asyncio
async def test_profile_snapshot_capability_returns_real_vita_fields_not_only_account_index():
    key = "studio.tipo"
    profile = LifeProfile(user_id="synthetic", domains={"studio": DomainProfile(
        domain="studio", objects={key: ProfileObject(
            key=key, value="universita", source="user_confirmed", status="confirmed", confirmed=True,
        )},
    )})
    result = await ToolRegistry(_DB(profile))._get_profile_snapshot({}, {"user_id": "synthetic"})
    assert result.status == "ok"
    assert any(f["ref"].endswith(":" + key) for f in result.payload["facts"])


@pytest.mark.asyncio
@pytest.mark.parametrize("area", all_areas(), ids=lambda a: a.id)
async def test_area_can_be_retrieved_from_full_life_for_a_relevant_task(area):
    domains = {}
    for a in all_areas():
        key, value, _ = _answer(a)
        domain = key.split(".")[0]
        domains.setdefault(domain, DomainProfile(domain=domain)).objects[key] = ProfileObject(
            key=key, value=value, source="user_confirmed", status="confirmed", confirmed=True,
        )
    # Previously the first 24 inserted facts won, so later VITA areas were
    # invisible even when a task explicitly asked about them.
    for i in range(40):
        key = f"casa.note_{i}"
        domains["casa"].objects[key] = ProfileObject(
            key=key, value=f"Annotazione {i}", source="user_confirmed",
            status="confirmed", confirmed=True,
        )
    profile = LifeProfile(user_id="synthetic", domains=domains)
    key, _, _ = _answer(area)
    need = ContextNeed(query=f"{area.id} {key.split('.')[-1]}", purpose="preparare un compito con i dati VITA")
    facts = await ContextSourceRegistry(_DB(profile))._profile("synthetic", need, None)
    selected, _ = rank_evidence(facts, need, anchor="", max_items=6, max_chars=2400)
    assert any(f.ref.endswith(f":{key}") for f in selected), area.id
    assert all("IBAN" not in f.statement for f in selected)


def test_sensitive_identifiers_are_not_sent_to_task_context():
    assert statement_for_profile_fact(domain="finanze", key="finanze.iban", value="IT00TEST") is None
    assert statement_for_profile_fact(domain="auto", key="auto.targa", value="ZZ000ZZ") is None
    assert statement_for_profile_fact(domain="casa", key="casa.mutuo_rata", value=620) is None
