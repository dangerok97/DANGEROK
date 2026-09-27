"""Regression coverage for answers, knowledge and durable review admission."""
from datetime import datetime, timezone
import sys
import types
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture(autouse=True)
def isolated_document_package(monkeypatch):
    # Import the real version helpers without booting unrelated HTTP routers
    # and a network Mongo client. All persistence here uses in-memory Mongo.
    if "documents" not in sys.modules:
        package = types.ModuleType("documents")
        package.__path__ = [str(Path(__file__).resolve().parents[1] / "documents")]
        monkeypatch.setitem(sys.modules, "documents", package)


def test_percentage_obeys_the_same_choice_conditions_as_questions():
    from life_profile.areas import area
    from life_profile.objectives import objectives_for_area, resolve, applicable
    facts = {"casa.situazione": "affitto", "casa.owned": False}
    live = applicable(resolve(objectives_for_area(area("casa")), facts=facts), facts)
    refs = {obj.ref for obj in live}
    assert "casa.affitto_canone" in refs
    assert "casa.mutuo" not in refs
    assert "casa.mutuo_rata" not in refs


@pytest.mark.parametrize("value", ["non_so", "Non lo so", "non ricordo"])
def test_unknown_answer_does_not_count_as_knowledge(value):
    from life_profile.objectives import KnowledgeObjective, resolve
    obj = KnowledgeObjective(ref="casa.utenze", area_id="casa", domain="casa", label="Utenze")
    assert resolve([obj], facts={obj.ref: value})[0].state == "unknown"


@pytest.mark.asyncio
async def test_revised_answer_is_persisted_and_reopens_the_correct_branch(monkeypatch):
    from life_profile.setup import GuidedSetupService
    from life_setup.repository import LifeSetupRepository
    from opportunities.discovery import OpportunityDiscovery
    monkeypatch.setattr(OpportunityDiscovery, "note", _no_wake_note)
    db = AsyncMongoMockClient().db
    svc = GuidedSetupService(db)
    await svc.answer("owner", objective_id="casa.situazione", option_ids=["affitto"])
    await svc.answer("owner", objective_id="casa.situazione", option_ids=["proprieta"])
    facts = await svc._facts("owner")
    assert facts["casa.situazione"] == "proprieta"
    assert facts["casa.owned"] is True
    session = await LifeSetupRepository(db).latest_session("owner")
    assert "casa.mutuo" not in session.meta["not_applicable_keys"]
    assert "casa.mutuo" in {x["ref"] for x in (await svc.profile.area_detail("owner", "casa"))["area"]["open_objectives"]}


@pytest.mark.asyncio
async def test_failed_write_does_not_advance_answer_state(monkeypatch):
    from life_profile.setup import GuidedSetupService
    from life_setup.profile_service import LifeProfileService
    from life_setup.repository import LifeSetupRepository
    async def fail(*args, **kwargs):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(LifeProfileService, "upsert_fact", fail)
    db = AsyncMongoMockClient().db
    with pytest.raises(RuntimeError):
        await GuidedSetupService(db).answer("owner", objective_id="casa.citta", value="Roma")
    session = await LifeSetupRepository(db).latest_session("owner")
    assert "casa.citta" not in session.meta.get("guided_answered", [])


async def _no_wake_note(self, owner_id, **kwargs):
    kwargs["wake"] = False
    return await _ORIGINAL_NOTE(self, owner_id, **kwargs)

from opportunities.discovery import OpportunityDiscovery
_ORIGINAL_NOTE = OpportunityDiscovery.note


@pytest.mark.asyncio
async def test_answer_enters_durable_review_and_snapshot_without_duplicates(monkeypatch):
    from life_setup.profile_service import LifeProfileService
    from opportunities.changes import ChangeLog, fingerprint
    from opportunities.snapshot import _life_profile, evidence_refs
    monkeypatch.setattr(OpportunityDiscovery, "note", _no_wake_note)
    db = AsyncMongoMockClient().db
    svc = LifeProfileService(db)
    for _ in range(2):
        await svc.upsert_fact("owner", domain="studio", key="studio.active", value=False,
                              source="user_confirmed", confirmed=True)
    await svc.upsert_fact("other", domain="casa", key="casa.citta", value="PrivateTown",
                          source="user_confirmed", confirmed=True)
    await svc.upsert_fact("owner", domain="casa", key="casa.citta", value="Guess",
                          source="inferred", status="suggested")
    pending = await ChangeLog(db).pending("owner")
    assert len(pending) == 1
    assert pending[0].entity_ref == "life_profile:studio.active"
    snapshot = await _life_profile(db, "owner", datetime.now(timezone.utc))
    assert [x["key"] for x in snapshot] == ["studio.active"]
    assert snapshot[0]["value"] == "False"
    assert evidence_refs({"life_profile": snapshot}) == {"life_profile:studio.active": "profile_fact"}
    assert fingerprint({"life_profile": snapshot}) != fingerprint({"life_profile": []})


@pytest.mark.asyncio
async def test_market_signal_is_admitted_and_changes_snapshot_fingerprint():
    from opportunities.changes import ChangeLog, fingerprint
    db = AsyncMongoMockClient().db
    result = await ChangeLog(db).record("owner", source="market_watch", kind="potential_saving_found",
                                      entity_ref="market_watch:electricity:test", after="price-v2")
    assert result.admitted
    assert fingerprint({"market_offers": [{"saving": 100}]}) != fingerprint({"market_offers": [{"saving": 150}]})


def test_same_offer_price_drop_is_reviewed_but_same_price_or_worse_is_not():
    from energy_offers.service import _improved_offers
    def offer(saving):
        return {"code": "same", "comparison_basis": "seller_component_estimate", "potential_saving_year": saving}
    assert _improved_offers([offer(150)], [offer(100)]) == {"same": 150}
    assert _improved_offers([offer(100)], [offer(100)]) == {}
    assert _improved_offers([offer(80)], [offer(100)]) == {}
    assert _improved_offers([offer(0)], []) == {}


def test_large_context_keeps_valid_json_and_each_source_without_mutating_input():
    import json
    from opportunities.reasoning import _dump
    payload = {"life_right_now": {
        "documents": [{"ref": f"document:{i}", "excerpt": "x" * 1200} for i in range(6)],
        "life_profile": [{"ref": f"life_profile:key{i}", "value": "y" * 240} for i in range(80)],
        "market_offers": [{"ref": "market_offer:test", "potential_saving_year": 150}],
    }}
    result = _dump(payload)
    assert len(result) <= 9000
    data = json.loads(result)["life_right_now"]
    assert all(data[key] for key in payload["life_right_now"])
    assert data["market_offers"][0]["potential_saving_year"] == 150
    assert len(payload["life_right_now"]["life_profile"]) == 80
