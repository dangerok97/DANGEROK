"""Real stored facts, identity, privacy and progress — all persistence is in memory."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError

from account_identity import IdentityIn, owner_full_name
from life_profile.knowledge_map import knowledge_map
from life_setup.models import LifeProfile, DomainProfile, ProfileObject


@pytest.fixture
def db():
    return AsyncMongoMockClient().knowledge_map_test


async def facts(db, user="a", **domains):
    profile = LifeProfile(user_id=user, domains={d: DomainProfile(domain=d, objects={
        k: ProfileObject(key=k, **v) for k, v in objects.items()
    }) for d, objects in domains.items()})
    await db.life_profiles.replace_one({"user_id": user}, profile.model_dump(), upsert=True)


@pytest.mark.asyncio
async def test_empty_profile_has_zero_stars_and_identity_adds_two_real_points(db):
    empty = await knowledge_map(db, "a")
    assert empty["count"] == 0 and empty["percent"] == 0
    await db.users.insert_one({"user_id": "a", **IdentityIn(first_name="Giulia", last_name="D’Angelo").updates()})
    full = await knowledge_map(db, "a")
    assert {s["statement"] for s in full["stars"]} == {"Giulia", "D’Angelo"}
    assert full["count"] == 2 and full["percent"] == 0
    assert full == await knowledge_map(db, "a"), "pure read must not mutate data/revisions"


@pytest.mark.asyncio
async def test_boolean_false_is_knowledge_and_skip_is_not(db):
    await facts(db, auto={"auto.possiede": {"value": False, "source": "user_said"}})
    await db.life_setup_sessions.insert_one({"id": "s1", "user_id": "a", "status": "skipped", "meta": {"first_run_finished": True}})
    result = await knowledge_map(db, "a")
    assert result["count"] == 1
    assert result["stars"][0]["area"] == "places"
    assert result["stars"][0]["status"] == "known"
    assert "No" in result["stars"][0]["statement"] or "non" in result["stars"][0]["statement"].lower()
    assert all(not b["complete"] for b in result["branches"] if b["star_count"] == 0)


@pytest.mark.asyncio
async def test_rejection_forgetting_correction_and_owner_isolation(db):
    await facts(db, casa={"casa.citta": {"value": "Torino", "confirmed": True},
        "casa.ipotesi": {"value": "ignored", "status": "suggested"},
        "casa.scarto": {"value": "ignored", "status": "rejected"}})
    await facts(db, user="b", casa={"casa.citta": {"value": "Private B"}})
    await db.memories.insert_many([
        {"user_id": "a", "id": "m1", "content": "Preferisco risposte brevi", "status": "active"},
        {"user_id": "a", "id": "m2", "content": "old", "status": "superseded"},
        {"user_id": "a", "id": "m3", "content": "forgotten", "status": "forgotten"},
        {"user_id": "b", "id": "m4", "content": "Private B", "status": "active"},
    ])
    before = await knowledge_map(db, "a")
    assert before["count"] == 2 and "Private B" not in str(before)
    city_id = next(s["id"] for s in before["stars"] if s["area"] == "home")
    await facts(db, casa={"casa.citta": {"value": "Bologna", "status": "corrected", "confirmed": True}})
    corrected = await knowledge_map(db, "a")
    assert next(s["id"] for s in corrected["stars"] if s["area"] == "home") == city_id
    assert corrected["count"] == 2 and corrected["revision"] != before["revision"]
    await db.memories.update_one({"id": "m1"}, {"$set": {"status": "forgotten"}})
    assert (await knowledge_map(db, "a"))["count"] == 1


@pytest.mark.asyncio
async def test_aliases_are_one_point_and_inference_stays_tentative(db):
    await facts(db, casa={"casa.citta": {"value": "Torino", "confirmed": True}}, mlc={
        "mlc.life_places.home": {"value": "Torino", "source": "inferred"}}, salute={
        "salute.preferenza": {"value": "Camminare", "source": "inferred", "confidence": .8}})
    result = await knowledge_map(db, "a")
    assert result["count"] == 2
    assert sum(s["status"] == "likely" for s in result["stars"]) == 1


@pytest.mark.asyncio
async def test_completed_branch_uses_vita_arithmetic_and_grows_after_saved_answers(db):
    from life_profile.areas import area
    from life_profile.objectives import objectives_for_area
    from life_profile.service import LifeProfileService
    before = await knowledge_map(db, "a")
    await facts(db, salute={o.ref: {"value": "Camminare ogni giorno", "confirmed": True}
                           for o in objectives_for_area(area("salute"))})
    after = await knowledge_map(db, "a")
    expected = await LifeProfileService(db).completeness("a")
    assert after["percent"] == expected.percent and after["percent"] > before["percent"]
    branch = next(b for b in after["branches"] if b["area_id"] == "salute")
    assert branch["complete"] and branch["percent"] == 100 and branch["star_count"] > 0
    assert all(s["area"] == "memory" for s in after["stars"])


@pytest.mark.asyncio
async def test_minimum_context_facts_follow_their_vita_branch(db):
    await facts(db, mlc={"mlc.life_places.home": {"value": "Torino"},
                        "mlc.current_situation.work": {"value": "Insegnante"}})
    result = await knowledge_map(db, "a")
    assert {s["area"] for s in result["stars"]} == {"home", "calendar"}


@pytest.mark.asyncio
async def test_name_update_is_owned_and_registration_does_not_drop_surname(db, monkeypatch):
    import deps
    from routers import auth
    from life_profile import router as life_router
    monkeypatch.setattr(deps, "db", db)
    monkeypatch.setattr(auth, "db", db)
    monkeypatch.setattr(life_router, "db", db)
    monkeypatch.setattr(auth, "prepare_user_decisions", AsyncMock())
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(life_router.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        invalid = await client.post("/auth/register", json={"email": "map@example.com", "password": "synthetic-only", "first_name": "Test", "last_name": " "})
        assert invalid.status_code == 422
        created = await client.post("/auth/register", json={"email": "map@example.com", "password": "synthetic-only", "first_name": "Giulia", "last_name": "De Luca"})
        assert created.status_code == 200
        user = created.json()["user"]
        assert user["name"] == "Giulia De Luca" and user["identity_confirmed"]
        headers = {"Authorization": "Bearer " + created.json()["token"]}
        assert (await client.get("/life-profile/knowledge-map")).status_code == 401
        projection = await client.get("/life-profile/knowledge-map", headers=headers)
        assert projection.status_code == 200 and projection.json()["count"] == 2
        assert projection.headers["cache-control"] == "private, no-store"
        edited = await client.put("/auth/identity", headers=headers, json={"first_name": "Giulia", "last_name": "D’Angelo", "tutorial_seen": True, "user_id": "victim"})
        assert edited.json()["knowledge_tutorial_version"] == 1
        assert (await db.users.find_one({"user_id": user["user_id"]}))["last_name"] == "D’Angelo"
        assert await db.users.find_one({"user_id": "victim"}) is None


def test_names_preserve_accents_and_cannot_embed_markup_or_instructions():
    name = IdentityIn(first_name="  Anna   Maria ", last_name="D’Angelo")
    assert name.first_name == "Anna Maria"
    assert owner_full_name(name.updates()) == "Anna Maria D’Angelo"
    assert owner_full_name({"name": "Legacy Full Name", "first_name": "Legacy"}) == "Legacy Full Name"
    for bad in ("", " ", "<script>", "123", "Nome\x00"):
        with pytest.raises(ValidationError):
            IdentityIn(first_name="Giulia", last_name=bad)


@pytest.mark.asyncio
async def test_dossier_and_introduction_deliver_the_entire_owner_name(db, monkeypatch):
    from telephone import briefing
    from telephone.dossier import prepare_while_it_rings
    from telephone.introduction import Introduction, IntroductionLedger
    await db.users.insert_one({"user_id": "a", **IdentityIn(first_name="Giulia", last_name="De Luca").updates()})
    monkeypatch.setattr(briefing, "what_ora_brings", AsyncMock(return_value={}))
    call = SimpleNamespace(owner_id="a", id="call-test", calling_whom="Clinica Test", session_ref="test", mandate=SimpleNamespace(why_calling="Chiedere un orario", may_agree_to=[], must_bring_back=[]))
    dossier = await prepare_while_it_rings(db, call)
    assert dossier.on_behalf_of == "Giulia De Luca"
    assert "Giulia De Luca" in dossier.opening_line
    intro = Introduction(assistant_for=dossier.on_behalf_of, reason_summary="sapere l’orario", reason_keywords=["orario"])
    ledger = IntroductionLedger(intro)
    ledger.we_said("Sono l'assistente di Giulia. Chiamo per sapere l'orario.")
    assert not ledger.is_settled(), "a missing surname is an incomplete introduction"
    ledger.we_said(" Sono l'assistente di Giulia De Luca.")
    assert ledger.is_settled()
